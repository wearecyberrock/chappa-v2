"""Chappa V2 — Standalone Local-First Cybersecurity Agent Server.

Runs standalone on 127.0.0.1:7480 (or proxied under Assimilis at /chappa/*).
Uses zero external Python dependencies so it works out of the box in any
Python 3.10+ runtime or packaged .exe/.dmg, while supporting hot-upgradable
modules/artifacts in ~/.chappa/modules/ without rebuilding the binary.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

STATE_DIR = Path(os.environ.get("CHAPPA_STATE_DIR") or (Path.home() / ".chappa")).expanduser()
MODULES_DIR = STATE_DIR / "modules"
DB_PATH = STATE_DIR / "chappa.db"

VALID_STATES = ("IDLE", "RECON", "ALERT", "CONTAINED")
_DB_LOCK = threading.Lock()


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MODULES_DIR.mkdir(parents=True, exist_ok=True)


def _db() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _DB_LOCK:
        conn = _db()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_state (
                    k TEXT PRIMARY KEY,
                    v TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'info',
                    summary TEXT NOT NULL,
                    data_json TEXT NOT NULL DEFAULT '{}',
                    lat REAL,
                    lon REAL,
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'open',
                    mitre TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'vigil',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS modules (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    version TEXT NOT NULL,
                    description TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    updated_at REAL NOT NULL
                );
                """
            )
            defaults = {
                "mask_state": "IDLE",
                "active_target": "",
                "fps_cadence": "12",
                "active_model": os.environ.get("CHAPPA_DEFAULT_MODEL", "hermes-auto"),
            }
            for k, v in defaults.items():
                conn.execute("INSERT OR IGNORE INTO runtime_state(k, v) VALUES (?, ?)", (k, v))
            conn.commit()
        finally:
            conn.close()


def _get_kv(conn: sqlite3.Connection, key: str, default: str = "") -> str:
    row = conn.execute("SELECT v FROM runtime_state WHERE k = ?", (key,)).fetchone()
    return str(row["v"]) if row else default


def _set_kv(conn: sqlite3.Connection, key: str, val: str) -> None:
    conn.execute(
        "INSERT INTO runtime_state(k, v) VALUES (?, ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v",
        (key, str(val)),
    )


def list_hot_modules() -> list[dict[str, Any]]:
    _ensure_dirs()
    mods: list[dict[str, Any]] = []
    for p in sorted(MODULES_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("id"):
                mods.append(data)
        except Exception:
            continue
    return mods


def install_hot_module(payload: dict[str, Any]) -> dict[str, Any]:
    _ensure_dirs()
    mod_id = str(payload.get("id") or "").strip().lower()
    mod_id = "".join(c for c in mod_id if c.isalnum() or c in ("-", "_"))
    if not mod_id:
        raise ValueError("Missing valid module id")
    rec = {
        "id": mod_id,
        "name": str(payload.get("name") or mod_id)[:80],
        "kind": str(payload.get("kind") or "tool")[:32],
        "version": str(payload.get("version") or "1.0.0")[:24],
        "description": str(payload.get("description") or "")[:300],
        "entrypoint": str(payload.get("entrypoint") or "")[:200],
        "enabled": bool(payload.get("enabled", True)),
        "updated_at": time.time(),
    }
    (MODULES_DIR / f"{mod_id}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    with _DB_LOCK:
        conn = _db()
        try:
            conn.execute(
                """
                INSERT INTO modules(id, name, kind, version, description, enabled, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  name=excluded.name, kind=excluded.kind, version=excluded.version,
                  description=excluded.description, enabled=excluded.enabled, updated_at=excluded.updated_at
                """,
                (rec["id"], rec["name"], rec["kind"], rec["version"], rec["description"], 1 if rec["enabled"] else 0, rec["updated_at"]),
            )
            conn.commit()
        finally:
            conn.close()
    return rec


def get_status() -> dict[str, Any]:
    init_db()
    with _DB_LOCK:
        conn = _db()
        try:
            mask_state = _get_kv(conn, "mask_state", "IDLE")
            active_target = _get_kv(conn, "active_target", "")
            fps_cadence = int(_get_kv(conn, "fps_cadence", "12") or "12")
            active_model = _get_kv(conn, "active_model", "hermes-auto")
            findings_count = conn.execute("SELECT COUNT(*) FROM findings").fetchone()[0]
            open_alerts = conn.execute("SELECT COUNT(*) FROM alerts WHERE status = 'open'").fetchone()[0]
            recent_findings = [
                dict(r) for r in conn.execute("SELECT * FROM findings ORDER BY id DESC LIMIT 12").fetchall()
            ]
            recent_alerts = [
                dict(r) for r in conn.execute("SELECT * FROM alerts ORDER BY id DESC LIMIT 12").fetchall()
            ]
        finally:
            conn.close()

    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip()
    return {
        "ok": True,
        "agent": "chappa-v2",
        "name": "Chappa V2",
        "version": "2.0.0-slice1",
        "mask_state": mask_state,
        "active_target": active_target,
        "fps_cadence": fps_cadence,
        "active_model": active_model,
        "findings_count": findings_count,
        "open_alerts": open_alerts,
        "recent_findings": recent_findings,
        "recent_alerts": recent_alerts,
        "hot_modules": list_hot_modules(),
        "modules_dir": str(MODULES_DIR),
        "assimilis_connected": bool(assimilis_url),
        "engines": {
            "mask": {"ready": True, "style": "agentsar-spiderverse"},
            "hackingtool": {"ready": False, "slice": 2, "note": "Local runner + approval gate scheduled in Slice 2"},
            "godseye": {"ready": False, "slice": 3, "note": "Static 3D globe feed scheduled in Slice 3"},
            "vigil": {"ready": False, "slice": 4, "note": "In-process AI SOC triage scheduled in Slice 4"},
        },
    }


def _hermes_bridge_reply(task: str, target: str) -> str:
    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
    if assimilis_url:
        try:
            req = urllib.request.Request(
                f"{assimilis_url}/api/world/models/complete",
                data=json.dumps({
                    "prompt": (
                        "You are Chappa V2, an autonomous local-first cybersecurity agent built on Hermes "
                        "(combining HackingTool v2, God's Eye View 3D Globe, and Vigil AI SOC). "
                        f"Target: {target or 'none'}. User command: {task}\n"
                        "Give a concise, actionable 2-4 line tactical response."
                    )
                }).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                txt = str(data.get("text") or data.get("reply") or data.get("content") or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
    return (
        f"[Chappa V2 · Slice 1] Task queued: {task}"
        + (f" (target: {target})" if target else "")
        + ". 3D Hacker Mask telemetry updated; HackingTool/Globe/Vigil execution hooks come online in Slices 2–4."
    )


def handle_command(payload: dict[str, Any]) -> dict[str, Any]:
    task = str(payload.get("task") or payload.get("prompt") or "").strip()
    target = str(payload.get("target") or "").strip()
    if not task:
        return {"ok": False, "error": "Empty command"}

    low = task.lower()
    next_state = "RECON" if any(w in low for w in ("scan", "recon", "probe", "audit", "whois", "dns", "nmap")) else (
        "ALERT" if any(w in low for w in ("alert", "threat", "cve", "breach", "exploit", "intrusion")) else (
            "CONTAINED" if any(w in low for w in ("contain", "block", "isolate", "patch", "resolve")) else "IDLE"
        )
    )
    now = time.time()
    with _DB_LOCK:
        conn = _db()
        try:
            _set_kv(conn, "mask_state", next_state)
            if target:
                _set_kv(conn, "active_target", target)
            conn.execute(
                "INSERT INTO findings(target, tool, severity, summary, data_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (target or "local", "chappa-command", "info" if next_state != "ALERT" else "high", task[:240], json.dumps({"source": payload.get("source", "ui")}), now),
            )
            if next_state == "ALERT":
                conn.execute(
                    "INSERT INTO alerts(title, severity, status, mitre, source, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (task[:140], "high", "open", "T1595", "chappa-v2", now),
                )
            conn.commit()
        finally:
            conn.close()

    reply = _hermes_bridge_reply(task, target)
    return {"ok": True, "mask_state": next_state, "target": target, "reply": reply, "status": get_status()}


MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}


class ChappaHandler(BaseHTTPRequestHandler):
    server_version = "ChappaV2/2.0"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0 or length > 1024 * 1024:
            return {}
        raw = self.rfile.read(length)
        try:
            obj = json.loads(raw.decode("utf-8"))
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}

    def _serve_file(self, rel_path: str) -> None:
        clean = rel_path.lstrip("/").split("?")[0] or "index.html"
        target = (STATIC_DIR / clean).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND, "Not found")
            return
        data = target.read_bytes()
        ctype = MIME_TYPES.get(target.suffix.lower(), "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file("index.html")
        if path == "/embed":
            return self._serve_file("embed.html")
        if path == "/api/chappa/status":
            return self._send_json(get_status())
        if path == "/api/chappa/modules":
            return self._send_json({"ok": True, "modules": list_hot_modules(), "modules_dir": str(MODULES_DIR)})
        if path.startswith("/static/"):
            return self._serve_file(path[len("/static/"):])
        return self._serve_file(path)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        body = self._read_json()
        if path == "/api/chappa/state":
            with _DB_LOCK:
                conn = _db()
                try:
                    ms = str(body.get("mask_state") or "").upper()
                    if ms in VALID_STATES:
                        _set_kv(conn, "mask_state", ms)
                    if "active_target" in body:
                        _set_kv(conn, "active_target", str(body.get("active_target") or "")[:200])
                    if "fps_cadence" in body:
                        cad = "12" if str(body.get("fps_cadence")) == "12" else "60"
                        _set_kv(conn, "fps_cadence", cad)
                    if "active_model" in body:
                        _set_kv(conn, "active_model", str(body.get("active_model") or "hermes-auto")[:120])
                    conn.commit()
                finally:
                    conn.close()
            return self._send_json(get_status())
        if path == "/api/chappa/command":
            return self._send_json(handle_command(body))
        if path == "/api/chappa/modules/install":
            try:
                rec = install_hot_module(body)
                return self._send_json({"ok": True, "module": rec})
            except ValueError as exc:
                return self._send_json({"ok": False, "error": str(exc)}, status=400)
        self._send_json({"ok": False, "error": "Unknown endpoint"}, status=404)


def main() -> None:
    init_db()
    host = os.environ.get("CHAPPA_HOST", "127.0.0.1")
    port = int(os.environ.get("CHAPPA_PORT", "7480"))
    srv = ThreadingHTTPServer((host, port), ChappaHandler)
    print(f"[chappa-v2] listening on http://{host}:{port} (state: {STATE_DIR})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
