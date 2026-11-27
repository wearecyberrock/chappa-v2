"""chappa_tools — the unified red/blue tool plane for Chappa V2.

Chappa's server is deliberately dependency-free (one file, bare Python), so it
does not import hackingtool: it reads the compiled catalog produced by
``scripts/build_tool_catalog.py`` and executes tools as subprocesses.

Design rules, in order of importance:

1. **No shell, ever.** A command is parsed into argv and executed with
   ``shell=False``. Nothing the model or the UI sends is interpolated into a
   command string.
2. **The catalog is the allowlist.** A run request may only use a binary that
   the chosen catalog entry already names. You cannot ask this module to run an
   arbitrary program by inventing a tool id.
3. **Blue is always available; red needs an engagement.** Defensive tooling is
   safe to run during any state. Offensive tooling requires a recorded target
   and an explicit authorization flag, mirroring how Vigil tracks a case.
4. **Everything is audited.** Every accepted run returns an argv + timing record
   for the caller to persist and broadcast.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

CATALOG_PATH = Path(__file__).resolve().parent / "tools_catalog.json"

# Output is truncated before it is handed back to the UI/model: a redirect loop
# or a directory scan must not be able to eat the whole event bus.
MAX_OUTPUT_BYTES = 64 * 1024
DEFAULT_TIMEOUT_S = 120
MAX_TIMEOUT_S = 900

# Environment variables that never reach a tool subprocess.
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH", re.I)

# A catalog command containing any of these is either a placeholder template
# (`nmap <target>`) or relies on shell semantics (pipes, redirects, chaining).
# Placeholders are parameter slots and get substituted; shell syntax is refused
# outright, because running it through a shell would reintroduce exactly the
# injection surface this module exists to remove.
_SHELL_META = re.compile(r"[|&;<>`$]|\$\(")
PLACEHOLDER_RE = re.compile(r"<([A-Za-z][A-Za-z0-9_\-]{0,31})>")

# Parameter values are the only operator-supplied text that reaches a subprocess,
# so they are restricted to characters that cannot change the command shape.
_PARAM_VALUE = re.compile(r"^[A-Za-z0-9._:/@%=+\\-]{1,200}$")

_cache: dict[str, Any] = {"mtime": None, "data": None}


def _catalog() -> dict[str, Any]:
    """Load the compiled catalog, reloading when the file changes."""
    if not CATALOG_PATH.is_file():
        return {"schema": 0, "stats": {}, "categories": [], "tools": [], "error": "catalog not built"}
    mtime = CATALOG_PATH.stat().st_mtime
    if _cache["mtime"] != mtime or _cache["data"] is None:
        try:
            _cache["data"] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            _cache["mtime"] = mtime
        except (OSError, json.JSONDecodeError) as exc:
            return {"schema": 0, "stats": {}, "categories": [], "tools": [], "error": str(exc)}
    return _cache["data"]


def stats() -> dict[str, Any]:
    data = _catalog()
    return {
        "ok": "error" not in data,
        "built_at": data.get("generated_at"),
        "source": data.get("source", {}),
        "counts": data.get("stats", {}),
        "error": data.get("error"),
    }


def _matches(tool: dict[str, Any], needle: str) -> bool:
    if not needle:
        return True
    n = needle.lower()
    haystack = " ".join(
        [tool.get("title", ""), tool.get("description", ""), tool.get("category", ""), " ".join(tool.get("tags") or [])]
    ).lower()
    return n in haystack


def list_tools(
    team: str | None = None,
    category: str | None = None,
    phase: str | None = None,
    q: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict[str, Any]:
    """Filtered catalog view for the API and the UI."""
    data = _catalog()
    tools = data.get("tools") or []
    team = (team or "").strip().lower()
    if team and team != "all":
        tools = [t for t in tools if t.get("team") in (team, "both")]
    if category:
        cat = category.strip().lower()
        tools = [t for t in tools if (t.get("category_id") == cat) or (t.get("category", "").lower() == cat)]
    if phase:
        tools = [t for t in tools if t.get("phase") == phase]
    if q:
        tools = [t for t in tools if _matches(t, q)]
    total = len(tools)
    limit = max(1, min(int(limit or 500), 2000))
    offset = max(0, int(offset or 0))
    page = [dict(t, installed=tool_installed(t)) for t in tools[offset : offset + limit]]
    return {
        "ok": "error" not in data,
        "total": total,
        "offset": offset,
        "limit": limit,
        "categories": data.get("categories", []),
        "tools": page,
        "error": data.get("error"),
    }


def get_tool(tool_id: str) -> dict[str, Any] | None:
    for tool in _catalog().get("tools") or []:
        if tool.get("id") == tool_id:
            return tool
    return None


def _allowed_binaries(tool: dict[str, Any]) -> set[str]:
    """First tokens of every command the catalog entry declares for this tool."""
    names: set[str] = set()
    for cmd in list(tool.get("run") or []) + [u[1] for u in (tool.get("usage") or []) if len(u) == 2]:
        try:
            parts = shlex.split(str(cmd), posix=True)
        except ValueError:
            continue
        # Skip wrappers so `sudo nmap ...` still authorizes `nmap`.
        while parts and parts[0] in {"sudo", "env", "time", "nohup"}:
            parts = parts[1:]
        if parts:
            token = parts[0]
            names.add(Path(token.replace("\\", "/")).name.lower())
    return names


def check_policy(tool: dict[str, Any], state: str, active_target: str, allow_red: bool) -> tuple[bool, str]:
    """Decide whether this tool may run right now.

    Blue/defensive work is always permitted. Red-team work needs the operator's
    switch plus *some* target — either already recorded as the engagement target
    or supplied with this run. The state is not a gate: starting a red-team run
    from IDLE simply moves the mask to RECON (that is what RECON means), so the
    operator is not made to click a state button first.
    """
    team = tool.get("team", "red")
    if team == "blue":
        return True, "defensive tooling is always available"
    if not allow_red:
        return False, "red-team execution is disabled (restart chappa with CHAPPA_ALLOW_RED=1 to enable it)"
    if not active_target:
        return (
            False,
            "no engagement target yet — type one in the ENGAGEMENT TARGET box (Tools pane) "
            "or pass it with the run, e.g. target=127.0.0.1",
        )
    return True, "authorized engagement"


# Parameter names that carry the thing being acted on. Filling one of these is
# how an operator names the engagement target inline instead of pre-recording it.
_TARGET_PARAM_KEYS = ("target", "host", "hostname", "ip", "domain", "url", "email")


def _supplied_target(params: dict[str, Any] | None) -> str:
    for key in _TARGET_PARAM_KEYS:
        value = (params or {}).get(key)
        if value:
            return str(value).strip()
    return ""


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


_which_cache: dict[str, bool] = {}


def tool_installed(tool: dict[str, Any]) -> bool | None:
    """Whether any binary this entry declares exists on this host.

    ``None`` means the entry declares no command at all (reference/install-only),
    which is different from "installed or not".
    """
    names = _allowed_binaries(tool)
    if not names:
        return None
    key = "|".join(sorted(names))
    if key not in _which_cache:
        _which_cache[key] = any(shutil.which(name) for name in names)
    return _which_cache[key]


def _engage_state(tool: dict[str, Any], state: str) -> dict[str, Any]:
    """A red-team run from IDLE starts the engagement.

    Returning the move rather than performing it keeps this module free of state
    storage; the caller persists it and broadcasts the mask change.
    """
    if tool.get("team") in ("red", "both") and state == "IDLE":
        return {"state_change": "RECON", "state_reason": "red-team run started the engagement"}
    return {}


def run_tool(
    tool_id: str,
    command: str | None = None,
    params: dict[str, Any] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    dry_run: bool = False,
    state: str = "IDLE",
    active_target: str = "",
    allow_red: bool | None = None,
) -> dict[str, Any]:
    """Validate, authorize, and execute one catalog command; never uses a shell.

    ``command`` may name any command the entry already declares (a `run` command
    or a `usage` example). Omitting it selects the entry's first runnable
    command. The binary of the chosen command must be in the entry's own
    command set, which is what makes the catalog an allowlist.

    ``params`` fills the entry's declared ``<slots>``. Slot names come from the
    catalog, values are charset-restricted, and for red-team entries the final
    argv must still contain the recorded engagement target.
    """
    tool = get_tool(tool_id)
    if tool is None:
        return {"ok": False, "error": f"unknown tool id: {tool_id}"}

    if allow_red is None:
        allow_red = os.environ.get("CHAPPA_ALLOW_RED", "0").strip().lower() in {"1", "true", "yes", "on"}

    # The engagement target may be recorded ahead of time or supplied with the
    # run itself. Supplying it inline adopts it as the engagement target, so a
    # single tool click is enough to start working.
    supplied = _supplied_target(params)
    effective_target = active_target or supplied
    if active_target and supplied and active_target.lower() != supplied.lower():
        return {
            "ok": False,
            "error": f"target mismatch: the recorded engagement target is '{active_target}' "
            f"but this run targets '{supplied}'",
            "hint": "clear or change the engagement target first if the engagement really moved",
        }

    ok, reason = check_policy(tool, state, effective_target, allow_red)
    if not ok:
        return {"ok": False, "error": reason, "policy": {"team": tool.get("team"), "state": state}}

    declared = [c for c in (tool.get("run") or [])]
    usage_cmds = [u[1] for u in (tool.get("usage") or []) if len(u) == 2]
    candidates = declared + usage_cmds
    wanted = {str(k) for k, v in (params or {}).items() if v}
    if command:
        chosen = command
    elif wanted:
        # Prefer a command whose slots are exactly covered by what the caller
        # filled, so `params={target: ...}` selects the parameterized variant.
        chosen = next(
            (
                c
                for c in candidates
                if PLACEHOLDER_RE.findall(c) and set(PLACEHOLDER_RE.findall(c)) <= wanted
            ),
            candidates[0] if candidates else "",
        )
    else:
        chosen = candidates[0] if candidates else ""
    if not chosen:
        return {
            "ok": False,
            "error": "this entry has no runnable command (installable or reference-only)",
            "kind": tool.get("kind"),
            "url": tool.get("url"),
        }
    if chosen not in declared + usage_cmds:
        return {"ok": False, "error": "command is not declared by this catalog entry"}

    # ── parameter substitution ───────────────────────────────────────────────
    # Slots come from the catalog itself (`<target>`), never from the caller:
    # an unknown parameter name cannot invent a new slot.
    slots = PLACEHOLDER_RE.findall(chosen)
    provided = {str(k): str(v) for k, v in (params or {}).items()}
    if slots:
        missing = [name for name in slots if not provided.get(name)]
        if missing:
            return {
                "ok": False,
                "error": f"missing parameters: {', '.join(missing)}",
                "params_required": slots,
                "command": chosen,
            }
        for name in slots:
            value = provided[name]
            if not _PARAM_VALUE.match(value):
                return {
                    "ok": False,
                    "error": f"parameter '{name}' contains characters that are not allowed "
                    "(letters, digits, . _ : / @ % = + - only, max 200)",
                    "params_required": slots,
                }
        filled = chosen
        for name in slots:
            filled = filled.replace(f"<{name}>", provided[name])
        if _SHELL_META.search(filled) or any(c in filled for c in "\r\n\t"):
            return {"ok": False, "error": "substituted command contains shell syntax", "argv_preview": filled}
    else:
        filled = chosen
        if _SHELL_META.search(filled):
            return {
                "ok": False,
                "error": "this command uses shell syntax (pipe/redirect/chaining); "
                "chappa will not run it through a shell",
                "command": chosen,
                "hint": "add a concrete argv entry for this tool, or run the documented command yourself",
            }

    # Red-team scope: whatever the operator recorded as the engagement target
    # must appear in the argv, so a stray parameter cannot retarget the run.
    # Pure introspection (`--help`, `--version`) touches no target and is
    # allowed — otherwise a red-team tool could not even be inspected.
    introspection = any(
        arg in {"--help", "-h", "-help", "--version", "-v", "-V", "help", "version"}
        for arg in filled.split()[1:]
    )
    if tool.get("team") in ("red", "both") and active_target and not introspection:
        if active_target.lower() not in " ".join(filled.split()).lower():
            return {
                "ok": False,
                "error": f"target scope: the command must contain the recorded target '{active_target}'",
                "argv_preview": filled,
                "hint": "pass the target as a parameter (key=value) or record it as the active target",
            }

    try:
        argv = shlex.split(filled, posix=True)
    except ValueError as exc:
        return {"ok": False, "error": f"unparseable command: {exc}"}

    allowed = _allowed_binaries(tool)
    if not argv:
        return {"ok": False, "error": "empty command"}
    # The allowlist is built from command text with wrappers stripped, so the
    # runtime check must strip the same wrappers or `sudo nmap ...` would be
    # validated as the binary `sudo` (which no entry ever declares).
    unwrapped = list(argv)
    while unwrapped and Path(unwrapped[0].replace("\\", "/")).name.lower() in {"sudo", "env", "time", "nohup"}:
        unwrapped = unwrapped[1:]
    if not unwrapped:
        return {"ok": False, "error": "command contains only a wrapper, no tool"}
    binary = Path(unwrapped[0].replace("\\", "/")).name.lower()
    if binary not in allowed:
        return {"ok": False, "error": f"binary '{binary}' is not declared by this entry"}

    resolved = shutil.which(unwrapped[0])
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "argv": argv,
            "resolved": resolved,
            "installed": resolved is not None,
            "install_hint": "" if resolved else (tool.get("url") or ""),
            "tool": tool_id,
            "team": tool.get("team"),
            "target": effective_target,
            **_engage_state(tool, state),
        }

    if resolved is None:
        return {
            "ok": False,
            "error": f"'{unwrapped[0]}' is not installed on this host",
            "install_hint": tool.get("url") or "",
            "argv": argv,
            "target": effective_target,
        }

    timeout_s = max(1, min(int(timeout_s or DEFAULT_TIMEOUT_S), MAX_TIMEOUT_S))
    started = time.time()
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            timeout=timeout_s,
            env=_clean_env(),
            cwd=str(Path.home()),
        )
        stdout = proc.stdout[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        stderr = proc.stderr[:MAX_OUTPUT_BYTES].decode("utf-8", "replace")
        return {
            "ok": proc.returncode == 0,
            "argv": argv,
            "exit_code": proc.returncode,
            "duration_ms": int((time.time() - started) * 1000),
            "stdout": stdout,
            "stderr": stderr,
            "truncated": len(proc.stdout) > MAX_OUTPUT_BYTES or len(proc.stderr) > MAX_OUTPUT_BYTES,
            "tool": tool_id,
            "team": tool.get("team"),
            "target": effective_target,
            **_engage_state(tool, state),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "argv": argv,
            "error": f"timed out after {timeout_s}s",
            "stdout": (exc.stdout or b"")[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"),
            "stderr": (exc.stderr or b"")[:MAX_OUTPUT_BYTES].decode("utf-8", "replace"),
            "duration_ms": int((time.time() - started) * 1000),
            "tool": tool_id,
        }
    except OSError as exc:
        return {"ok": False, "argv": argv, "error": str(exc), "tool": tool_id}
