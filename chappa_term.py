"""PTY-backed terminal sessions for the Chappa UI.

This is a *real* terminal: it spawns a program attached to a Windows pseudo
console (ConPTY via ``pywinpty``), so full-screen TUIs, colour, and interactive
prompts all behave as they do in Windows Terminal. Without pywinpty it degrades
to plain pipes, which is fine for line-oriented CLIs but cannot render a TUI.

Safety model, since a terminal is by definition arbitrary command execution:

* Disabled unless ``CHAPPA_ALLOW_SHELL=1``. The server refuses to start a
  session otherwise; there is no quieter bypass.
* Only the launch profiles below are offered, plus an explicitly enabled
  ``custom`` profile that takes a command line instead of argv.
* Sessions are process-local and die with the server; nothing is detached.
* The caller (server) audits every start and every submitted line.

The server is a single-user localhost tool, so this is a capability the
operator switches on deliberately, not a privilege boundary.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
from typing import Any

try:  # optional: real PTY
    from winpty import PtyProcess  # type: ignore
except Exception:  # pragma: no cover - exercised only when the dep is absent
    PtyProcess = None

MAX_BUFFER = 120_000  # characters retained per session (scrolling history)
MAX_READ = 64_000     # characters returned by a single read (bounds JSON size)
READ_CHUNK = 4096
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b\][^\x07]*\x07|\x1b[()][A-Za-z0-9]")

SESSIONS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def enabled() -> bool:
    return os.environ.get("CHAPPA_ALLOW_SHELL", "0").strip().lower() in {"1", "true", "yes", "on"}


def _resolve(command: str) -> list[str] | None:
    """Resolve one argv token to a concrete executable, if present."""
    found = shutil.which(command)
    return [found] if found else None


def _hackingtool_command() -> list[str] | None:
    direct = _resolve("hackingtool")
    if direct:
        return direct
    # pip may install the console script outside PATH (user scheme), so look in
    # the user scripts directory before giving up on it.
    try:
        import sysconfig

        scripts = sysconfig.get_path("scripts", scheme="nt_user") or ""
        exe = os.path.join(scripts, "hackingtool.exe")
        if scripts and os.path.isfile(exe):
            return [exe]
    except Exception:
        pass
    try:
        import importlib.util

        if importlib.util.find_spec("hackingtool") is not None:
            return [sys.executable, "-m", "hackingtool"]
    except Exception:
        pass
    return None


def profiles() -> dict[str, Any]:
    """What the UI may launch, and whether this deployment allows it at all."""
    shells = {}
    for name, cmd in (
        ("pwsh", "powershell.exe"),
        ("cmd", "cmd.exe"),
        ("bash", "bash.exe"),
        ("wsl", "wsl.exe"),
    ):
        resolved = _resolve(cmd)
        if resolved:
            shells[name] = resolved
    hack = _hackingtool_command()
    if hack:
        shells["hackingtool"] = hack
    return {
        "enabled": enabled(),
        "pty": PtyProcess is not None,
        "profiles": sorted(shells.keys()),
        "commands": shells,
        "note": "PTY sessions" if PtyProcess else "pipe fallback (no pywinpty): line CLIs only",
    }


def start(kind: str, custom: str | None = None, cols: int = 120, rows: int = 32) -> dict[str, Any]:
    if not enabled():
        return {"ok": False, "error": "terminal is disabled — restart chappa with CHAPPA_ALLOW_SHELL=1 to enable it"}

    # One session at a time: PTY readers are the heaviest thing this server does,
    # and a second interactive session was enough to starve the HTTP threads.
    for other in list(SESSIONS.values()):
        if other.get("alive"):
            try:
                other["stop"]()
            except Exception:
                pass
            other["alive"] = False

    if kind == "custom":
        if not (custom or "").strip():
            return {"ok": False, "error": "custom profile needs a command"}
        argv = [custom.strip()]
    elif kind == "hackingtool":
        argv = _hackingtool_command() or []
        if not argv:
            return {
                "ok": False,
                "error": "hackingtool is not installed for this interpreter",
                "hint": "py -m pip install -e hackingtool_v2  (or pass the 'custom' profile with a command)",
            }
    else:
        cmd = {"pwsh": "powershell.exe", "cmd": "cmd.exe", "bash": "bash.exe", "wsl": "wsl.exe"}.get(kind)
        if not cmd:
            return {"ok": False, "error": f"unknown profile: {kind}", "hint": "try pwsh, cmd, hackingtool or custom"}
        argv = _resolve(cmd) or []
        if not argv:
            return {"ok": False, "error": f"{cmd} not found on this host"}

    sid = uuid.uuid4().hex[:12]
    try:
        if PtyProcess is not None:
            # ConPTY takes a command line; quote each argv token.
            cmdline = " ".join(f'"{a}"' if " " in a else a for a in argv)
            proc = PtyProcess.spawn(cmdline, dimensions=(max(5, rows), max(20, cols)))
            write = lambda data: proc.write(data)  # noqa: E731
            read = lambda: proc.read(READ_CHUNK)  # noqa: E731
            alive = lambda: proc.isalive()  # noqa: E731
            stop = lambda: proc.terminate()  # noqa: E731
        else:
            proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                shell=False,
            )
            write = lambda data: (proc.stdin.write(data.encode("utf-8", "replace")), proc.stdin.flush())  # noqa: E731
            read = lambda: proc.stdout.read(READ_CHUNK) or ""  # noqa: E731
            alive = lambda: proc.poll() is None  # noqa: E731
            stop = lambda: proc.terminate()  # noqa: E731
    except Exception as exc:  # pragma: no cover - platform specific
        return {"ok": False, "error": f"failed to start {kind}: {exc}"}

    session = {
        "id": sid,
        "kind": kind,
        "argv": argv,
        "buf": "",
        "base": 0,          # absolute offset of buf[0]
        "alive": True,
        "started_at": time.time(),
        "proc": proc,
        "write": write,
        "stop": stop,
    }

    def pump() -> None:
        while session["alive"]:
            try:
                chunk = read()
            except EOFError:
                break
            except Exception:
                break
            if not chunk:
                if not alive():
                    break
                continue
            text = chunk if isinstance(chunk, str) else chunk.decode("utf-8", "replace")
            with _LOCK:
                session["buf"] += text
                overflow = len(session["buf"]) - MAX_BUFFER
                if overflow > 0:
                    session["buf"] = session["buf"][overflow:]
                    session["base"] += overflow
            # A chatty TUI would otherwise spin this loop hot and starve the
            # HTTP threads (the whole server became unresponsive without this).
            time.sleep(0.01)
        with _LOCK:
            session["alive"] = False
            session["buf"] += "\n[session ended]\n"

    threading.Thread(target=pump, name=f"term-{sid}", daemon=True).start()
    with _LOCK:
        SESSIONS[sid] = session
    return {"ok": True, "session": sid, "kind": kind, "argv": argv, "pty": PtyProcess is not None}


def write(sid: str, data: str) -> dict[str, Any]:
    session = SESSIONS.get(sid)
    if not session:
        return {"ok": False, "error": "unknown session"}
    if not session["alive"]:
        return {"ok": False, "error": "session has ended"}
    try:
        session["write"](data)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def read(sid: str, cursor: int = 0) -> dict[str, Any]:
    session = SESSIONS.get(sid)
    if not session:
        return {"ok": False, "error": "unknown session"}
    with _LOCK:
        base = session["base"]
        start = max(int(cursor or 0) - base, 0)
        data = session["buf"][start:]
        if len(data) > MAX_READ:  # keep the newest output, bound the payload
            data = data[-MAX_READ:]
        end = base + len(session["buf"])
        alive = session["alive"]
    return {"ok": True, "data": data, "cursor": end, "alive": alive, "base": base}


def stop(sid: str) -> dict[str, Any]:
    session = SESSIONS.get(sid)
    if not session:
        return {"ok": False, "error": "unknown session"}
    try:
        session["stop"]()
    except Exception:
        pass
    session["alive"] = False
    return {"ok": True, "session": sid}


def list_sessions() -> list[dict[str, Any]]:
    with _LOCK:
        return [
            {"id": s["id"], "kind": s["kind"], "alive": s["alive"], "argv": s["argv"], "started_at": s["started_at"]}
            for s in SESSIONS.values()
        ]


def strip_ansi(text: str) -> str:
    return _ANSI.sub("", text)
