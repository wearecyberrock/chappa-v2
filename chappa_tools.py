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
# Both are refused rather than guessed at: running them through a shell would
# reintroduce exactly the injection surface this module exists to remove.
_SHELL_META = re.compile(r"[|&;<>`$]|\$\(")

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
    page = tools[offset : offset + limit]
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

    Blue/defensive and dual-use reporting work is always permitted. Red-team
    action requires (a) a recorded target, (b) the operator's red-team switch,
    and (c) a non-idle state, so a stray click cannot start an engagement.
    """
    team = tool.get("team", "red")
    if team == "blue":
        return True, "defensive tooling is always available"
    if not allow_red:
        return False, "red-team execution is disabled (CHAPPA_ALLOW_RED is off)"
    if not active_target:
        return False, "no active target recorded — set one on the state endpoint first"
    if state == "IDLE":
        return False, f"state is IDLE — move to RECON/ALERT/CONTAINED before running red-team tools"
    return True, "authorized engagement"


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


def run_tool(
    tool_id: str,
    command: str | None = None,
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
    """
    tool = get_tool(tool_id)
    if tool is None:
        return {"ok": False, "error": f"unknown tool id: {tool_id}"}

    if allow_red is None:
        allow_red = os.environ.get("CHAPPA_ALLOW_RED", "0").strip().lower() in {"1", "true", "yes", "on"}
    ok, reason = check_policy(tool, state, active_target, allow_red)
    if not ok:
        return {"ok": False, "error": reason, "policy": {"team": tool.get("team"), "state": state}}

    declared = [c for c in (tool.get("run") or [])]
    usage_cmds = [u[1] for u in (tool.get("usage") or []) if len(u) == 2]
    chosen = command or (declared[0] if declared else (usage_cmds[0] if usage_cmds else ""))
    if not chosen:
        return {
            "ok": False,
            "error": "this entry has no runnable command (installable or reference-only)",
            "kind": tool.get("kind"),
            "url": tool.get("url"),
        }
    if chosen not in declared + usage_cmds:
        return {"ok": False, "error": "command is not declared by this catalog entry"}
    if _SHELL_META.search(chosen):
        return {
            "ok": False,
            "error": "this command is a template or uses shell syntax (pipe/redirect/placeholder); "
            "chappa will not run it through a shell",
            "command": chosen,
            "hint": "add a concrete argv entry for this tool, or run the documented command yourself",
        }

    try:
        argv = shlex.split(chosen, posix=True)
    except ValueError as exc:
        return {"ok": False, "error": f"unparseable command: {exc}"}

    allowed = _allowed_binaries(tool)
    if not argv:
        return {"ok": False, "error": "empty command"}
    binary = Path(argv[0].replace("\\", "/")).name.lower()
    if binary not in allowed:
        return {"ok": False, "error": f"binary '{binary}' is not declared by this entry"}

    resolved = shutil.which(argv[0])
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
        }

    if resolved is None:
        return {
            "ok": False,
            "error": f"'{argv[0]}' is not installed on this host",
            "install_hint": tool.get("url") or "",
            "argv": argv,
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
