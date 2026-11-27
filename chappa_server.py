"""Chappa V2 — Standalone Local-First Cybersecurity Core Agent (Hermes + Vigil AI SOC + God's Eye View).

Runs standalone on 127.0.0.1:7480 or proxied behind Assimilis at /chappa-v2/*.
Zero Docker / zero external Python dependencies: local SQLite store, live SSE
event bus, Vigil AI SOC triage & external Vigil bridge, God's Eye View 3D globe
feed & bridge, read-only defensive posture telemetry, Hermes/Assimilis model &
chat bridge, and hot-upgradable ~/.chappa/modules/ artifacts.
"""
from __future__ import annotations

import json
import os
import queue
import socket
import sqlite3
import ssl
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

# Local module: the unified red/blue tool plane. Reads the compiled
# tools_catalog.json and runs catalog commands without a shell.
import chappa_tools

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"

STATE_DIR = Path(os.environ.get("CHAPPA_STATE_DIR") or (Path.home() / ".chappa")).expanduser()
MODULES_DIR = STATE_DIR / "modules"
DB_PATH = STATE_DIR / "chappa.db"

VALID_STATES = ("IDLE", "RECON", "ALERT", "CONTAINED")
_DB_LOCK = threading.Lock()
_SSE_LOCK = threading.Lock()
_SSE_SUBS: list[queue.Queue[str]] = []


def _ensure_dirs() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    MODULES_DIR.mkdir(parents=True, exist_ok=True)


def _db() -> sqlite3.Connection:
    _ensure_dirs()
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _broadcast(event: str, payload: dict[str, Any]) -> None:
    msg = f"event: {event}\ndata: {json.dumps(payload)}\n\n"
    with _SSE_LOCK:
        dead: list[queue.Queue[str]] = []
        for q in _SSE_SUBS:
            try:
                q.put_nowait(msg)
            except queue.Full:
                dead.append(q)
        for q in dead:
            if q in _SSE_SUBS:
                _SSE_SUBS.remove(q)


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
                CREATE TABLE IF NOT EXISTS vigil_cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'medium',
                    status TEXT NOT NULL DEFAULT 'open',
                    mitre TEXT NOT NULL DEFAULT 'T1071',
                    verdict TEXT NOT NULL DEFAULT '',
                    remediation TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'vigil',
                    lat REAL,
                    lon REAL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS globe_pins (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    label TEXT NOT NULL,
                    ip TEXT NOT NULL DEFAULT '',
                    asn TEXT NOT NULL DEFAULT '',
                    severity TEXT NOT NULL DEFAULT 'info',
                    lat REAL NOT NULL,
                    lon REAL NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
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
                CREATE TABLE IF NOT EXISTS tool_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tool_id TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    team TEXT NOT NULL DEFAULT '',
                    argv TEXT NOT NULL DEFAULT '',
                    exit_code INTEGER,
                    duration_ms INTEGER,
                    output TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                """
            )
            defaults = {
                "mask_state": "IDLE",
                "active_target": "",
                "fps_cadence": "60",
                "active_model": os.environ.get("CHAPPA_DEFAULT_MODEL", "hermes-auto"),
                "globe_focus": json.dumps({"lat": 18.0179, "lon": -76.8099, "label": "KINGSTON HQ"}),
            }
            for k, v in defaults.items():
                conn.execute("INSERT OR IGNORE INTO runtime_state(k, v) VALUES (?, ?)", (k, v))

            # Seed initial telemetry reference pin so God's Eye Globe is immediately alive
            pin_cnt = conn.execute("SELECT COUNT(*) FROM globe_pins").fetchone()[0]
            if pin_cnt == 0:
                now = time.time()
                for lbl, ip, asn, sev, lat, lon, notes in [
                    ("KINGSTON HQ", "127.0.0.1", "LOCAL-NODE", "info", 18.0179, -76.8099, "Chappa V2 Local Command Node"),
                    ("CLOUDFLARE EDGE", "1.1.1.1", "AS13335", "low", 37.7749, -122.4194, "DNS Resolver Telemetry Anchor"),
                    ("FRANKFURT IX", "193.0.14.129", "AS25152", "info", 50.1109, 8.6821, "EU Backbone Telemetry Anchor"),
                ]:
                    conn.execute(
                        "INSERT INTO globe_pins(label, ip, asn, severity, lat, lon, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (lbl, ip, asn, sev, lat, lon, notes, now),
                    )
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


def _probe_http(url: str, timeout: float = 0.6) -> bool:
    if not url:
        return False
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


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
    mod_id = "".join(c for c in str(payload.get("id") or "").strip().lower() if c.isalnum() or c in ("-", "_"))
    if not mod_id:
        raise ValueError("Missing valid module id")
    rec = {
        "id": mod_id,
        "name": str(payload.get("name") or mod_id)[:80],
        "kind": str(payload.get("kind") or "playbook")[:32],
        "version": str(payload.get("version") or "1.0.0")[:24],
        "description": str(payload.get("description") or "")[:300],
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
    _broadcast("module", rec)
    return rec


def fetch_assimilis_models() -> list[dict[str, Any]]:
    base = [{"id": "hermes-auto", "label": "Hermes Auto (Antigravity + Local)", "provider": "hermes", "type": "text"}]
    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
    if assimilis_url:
        try:
            with urllib.request.urlopen(f"{assimilis_url}/api/models/all", timeout=2.5) as r:
                data = json.loads(r.read().decode("utf-8"))
                models = data.get("models") if isinstance(data, dict) else None
                if isinstance(models, list) and models:
                    text_models = [
                        m for m in models
                        if isinstance(m, dict) and str(m.get("type") or m.get("category") or "text").lower() in ("text", "code", "chat", "reasoning", "")
                    ]
                    return base + (text_models or models)[:50]
        except Exception:
            pass
    return base + [
        {"id": "@antigravity:gemini-2.5-pro", "label": "Antigravity · Gemini 2.5 Pro", "provider": "antigravity", "type": "text"},
        {"id": "ollama:qwen2.5:14b", "label": "Local Ollama · Qwen 2.5 14B", "provider": "ollama", "type": "text"},
    ]


def hermes_complete(prompt: str, *, model: str = "") -> str:
    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
    if assimilis_url:
        try:
            body: dict[str, Any] = {"prompt": prompt}
            if model and model != "hermes-auto":
                body["model"] = model
            req = urllib.request.Request(
                f"{assimilis_url}/api/world/models/complete",
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=14) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                txt = str(data.get("text") or data.get("reply") or data.get("content") or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
    return ""


def get_status() -> dict[str, Any]:
    init_db()
    with _DB_LOCK:
        conn = _db()
        try:
            mask_state = _get_kv(conn, "mask_state", "IDLE")
            active_target = _get_kv(conn, "active_target", "")
            fps_cadence = int(_get_kv(conn, "fps_cadence", "60") or "60")
            active_model = _get_kv(conn, "active_model", "hermes-auto")
            focus_raw = _get_kv(conn, "globe_focus", "{}")
            cases = [dict(r) for r in conn.execute("SELECT * FROM vigil_cases ORDER BY id DESC LIMIT 20").fetchall()]
            open_alerts = conn.execute("SELECT COUNT(*) FROM vigil_cases WHERE status IN ('open', 'investigating')").fetchone()[0]
            pins = [dict(r) for r in conn.execute("SELECT * FROM globe_pins ORDER BY id DESC LIMIT 30").fetchall()]
            chats = [dict(r) for r in conn.execute("SELECT * FROM chat_messages ORDER BY id DESC LIMIT 30").fetchall()]
            chats.reverse()
        finally:
            conn.close()

    try:
        globe_focus = json.loads(focus_raw)
    except Exception:
        globe_focus = {"lat": 18.0179, "lon": -76.8099, "label": "KINGSTON HQ"}

    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip()
    vigil_url = os.environ.get("VIGIL_URL", "http://127.0.0.1:8000").strip()
    godseye_url = os.environ.get("GODSEYE_URL", "http://127.0.0.1:3001").strip()
    custom_obj = (MODULES_DIR / "custom_mask.obj").is_file()

    return {
        "ok": True,
        "agent": "chappa-v2",
        "name": "Chappa V2",
        "version": "2.1.0",
        "mask_state": mask_state,
        "active_target": active_target,
        "fps_cadence": fps_cadence,
        "active_model": active_model,
        "open_alerts": open_alerts,
        "cases_count": len(cases),
        "pins_count": len(pins),
        "cases": cases,
        "pins": pins,
        "globe_focus": globe_focus,
        "chat_history": chats,
        "hot_modules": list_hot_modules(),
        "modules_dir": str(MODULES_DIR),
        "custom_mask_loaded": custom_obj,
        "bridges": {
            "assimilis": {"connected": bool(assimilis_url), "url": assimilis_url},
            "vigil": {"mode": "external+local" if _probe_http(vigil_url + "/health", 0.2) else "in-process-sqlite", "url": vigil_url},
            "godseye": {"external_live": _probe_http(godseye_url, 0.2), "url": godseye_url},
        },
    }


def vigil_create_or_triage(payload: dict[str, Any], *, run_triage: bool = True) -> dict[str, Any]:
    title = str(payload.get("title") or payload.get("alert") or payload.get("summary") or "").strip()
    target = str(payload.get("target") or payload.get("ioc") or "").strip()
    severity = str(payload.get("severity") or "medium").lower()
    if severity not in ("critical", "high", "medium", "low", "info"):
        severity = "medium"
    if not title:
        title = f"Defensive triage: {target or 'SOC Event'}"

    mitre = str(payload.get("mitre") or "").strip()
    low = f"{title} {target}".lower()
    if not mitre:
        if any(k in low for k in ("tls", "ssl", "cert", "header", "hsts", "csp")):
            mitre = "T1557 / Defensive Hardening"
        elif any(k in low for k in ("dns", "domain", "phish", "c2", "beacon")):
            mitre = "T1071 · Application Layer Protocol"
        elif any(k in low for k in ("login", "brute", "auth", "cred", "ssh")):
            mitre = "T1110 · Brute Force"
        else:
            mitre = "T1595 · Active / Telemetry Review"

    verdict = str(payload.get("verdict") or "")
    remediation = str(payload.get("remediation") or "")
    if run_triage and not verdict:
        ai_txt = hermes_complete(
            "You are Vigil AI SOC inside Chappa V2 (defensive security operations). "
            f"Triage this alert concisely in 2 short sentences (Verdict + Remediation).\n"
            f"Title: {title}\nTarget/IOC: {target or 'n/a'}\nSeverity: {severity}\nMITRE: {mitre}"
        )
        verdict = ai_txt or (
            f"Classified as {severity.upper()} defensive telemetry ({mitre}). "
            f"Correlated IOC '{target or 'local'}' logged to Chappa SQLite SOC queue."
        )
    if not remediation:
        remediation = "1) Verify asset ownership & logs  2) Enforce TLS/CSP/firewall rules  3) Mark Contained once verified."

    lat = payload.get("lat")
    lon = payload.get("lon")
    now = time.time()
    next_mask = "ALERT" if severity in ("critical", "high") else "RECON"

    with _DB_LOCK:
        conn = _db()
        try:
            cur = conn.execute(
                """
                INSERT INTO vigil_cases(title, target, severity, status, mitre, verdict, remediation, source, lat, lon, created_at, updated_at)
                VALUES (?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (title[:160], target[:180], severity, mitre[:80], verdict[:600], remediation[:400], str(payload.get("source") or "vigil"), lat, lon, now, now),
            )
            case_id = cur.lastrowid
            _set_kv(conn, "mask_state", next_mask)
            if target:
                _set_kv(conn, "active_target", target[:180])
            if lat is not None and lon is not None:
                conn.execute(
                    "INSERT INTO globe_pins(label, ip, asn, severity, lat, lon, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (title[:48], target[:64], str(payload.get("asn") or "SOC-PIN"), severity, float(lat), float(lon), verdict[:180], now),
                )
                _set_kv(conn, "globe_focus", json.dumps({"lat": float(lat), "lon": float(lon), "label": title[:40]}))
            conn.commit()
            case_row = dict(conn.execute("SELECT * FROM vigil_cases WHERE id = ?", (case_id,)).fetchone())
        finally:
            conn.close()

    _broadcast("vigil_case", case_row)
    return {"ok": True, "case": case_row, "mask_state": next_mask}


def update_case_status(case_id: int, next_status: str) -> dict[str, Any]:
    if next_status not in ("open", "investigating", "contained", "closed"):
        return {"ok": False, "error": "Invalid status"}
    now = time.time()
    with _DB_LOCK:
        conn = _db()
        try:
            conn.execute("UPDATE vigil_cases SET status = ?, updated_at = ? WHERE id = ?", (next_status, now, case_id))
            open_high = conn.execute(
                "SELECT COUNT(*) FROM vigil_cases WHERE status IN ('open','investigating') AND severity IN ('critical','high')"
            ).fetchone()[0]
            if next_status in ("contained", "closed") and open_high == 0:
                _set_kv(conn, "mask_state", "CONTAINED")
            conn.commit()
            row = conn.execute("SELECT * FROM vigil_cases WHERE id = ?", (case_id,)).fetchone()
        finally:
            conn.close()
    if not row:
        return {"ok": False, "error": "Case not found"}
    rec = dict(row)
    _broadcast("vigil_case", rec)
    return {"ok": True, "case": rec, "status": get_status()}


def defensive_posture_check(host: str) -> dict[str, Any]:
    """Read-only defensive posture audit: DNS resolution, TLS cert expiry, and HTTP security headers."""
    clean = str(host or "").strip().lower()
    clean = clean.replace("https://", "").replace("http://", "").split("/")[0].split(":")[0].strip()
    if not clean or any(c in clean for c in (" ", ";", "|", "&", "`", "$")):
        return {"ok": False, "error": "Provide a valid hostname (e.g. example.com)"}

    report: dict[str, Any] = {"host": clean, "ips": [], "tls": {}, "headers": {}, "missing_headers": [], "score": 100}
    try:
        infos = socket.getaddrinfo(clean, 443, type=socket.SOCK_STREAM)
        report["ips"] = sorted({i[4][0] for i in infos})[:6]
    except Exception as exc:
        report["dns_error"] = str(exc)

    # TLS certificate check (passive read-only handshake)
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((clean, 443), timeout=4.0) as sock:
            with ctx.wrap_socket(sock, server_hostname=clean) as ssock:
                cert = ssock.getpeercert() or {}
                report["tls"] = {
                    "version": ssock.version(),
                    "notAfter": cert.get("notAfter", ""),
                    "issuer": dict(x[0] for x in cert.get("issuer", ())) if cert.get("issuer") else {},
                }
    except Exception as exc:
        report["tls"] = {"error": str(exc)}
        report["score"] -= 25

    # HTTP security headers inspection (HEAD/GET)
    req_headers = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options"]
    try:
        req = urllib.request.Request(f"https://{clean}/", method="HEAD", headers={"User-Agent": "ChappaV2-DefensiveAudit/2.1"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            hdrs = {k.lower(): v for k, v in resp.headers.items()}
            for h in req_headers:
                if h in hdrs:
                    report["headers"][h] = hdrs[h][:160]
                else:
                    report["missing_headers"].append(h)
                    report["score"] -= 10
    except Exception as exc:
        report["http_error"] = str(exc)

    report["score"] = max(0, report["score"])
    sev = "high" if report["score"] < 60 else ("medium" if report["missing_headers"] else "info")
    summary = (
        f"Defensive audit of {clean}: score {report['score']}/100 · "
        f"IPs {', '.join(report['ips']) or 'unresolved'} · "
        f"missing headers: {', '.join(report['missing_headers']) or 'none'}"
    )
    # Deterministic globe coordinate hash fallback when offline (or real geo when available)
    hval = sum(ord(c) for c in clean)
    lat = round(((hval * 17) % 100) - 45.0, 3)
    lon = round(((hval * 31) % 280) - 140.0, 3)

    triage = vigil_create_or_triage(
        {
            "title": f"Posture Check · {clean}",
            "target": report["ips"][0] if report["ips"] else clean,
            "severity": sev,
            "mitre": "Defensive Posture / TLS & Headers",
            "verdict": summary,
            "lat": lat,
            "lon": lon,
            "asn": report["ips"][0] if report["ips"] else "DNS",
            "source": "defensive-check",
        },
        run_triage=False,
    )
    return {"ok": True, "report": report, "case": triage["case"], "status": get_status()}


def handle_chat(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("message") or payload.get("task") or payload.get("prompt") or "").strip()
    model = str(payload.get("model") or "").strip()
    target = str(payload.get("target") or "").strip()
    if not text:
        return {"ok": False, "error": "Empty message"}

    now = time.time()
    with _DB_LOCK:
        conn = _db()
        try:
            if not model:
                model = _get_kv(conn, "active_model", "hermes-auto")
            else:
                _set_kv(conn, "active_model", model[:120])
            conn.execute("INSERT INTO chat_messages(role, content, model, created_at) VALUES ('user', ?, ?, ?)", (text[:4000], model, now))
            conn.commit()
        finally:
            conn.close()

    low = text.lower()
    action_note = ""
    if any(w in low for w in ("contain", "lock", "resolve")):
        with _DB_LOCK:
            conn = _db()
            try:
                _set_kv(conn, "mask_state", "CONTAINED")
                conn.commit()
            finally:
                conn.close()
        action_note = "\n[Mask State → CONTAINED]"
    elif any(w in low for w in ("posture", "audit header", "check tls", "check dns")) and (target or "." in text):
        host = target or next((tok.strip(".,;:()\"'") for tok in text.split() if "." in tok and not tok.startswith("http")), "")
        if host:
            chk = defensive_posture_check(host)
            if chk.get("ok"):
                action_note = f"\n[Defensive Audit Logged → Vigil Case #{chk['case']['id']}] {chk['case']['verdict']}"
    elif any(w in low for w in ("triage", "alert", "incident", "threat", "cve", "ioc")):
        tr = vigil_create_or_triage({"title": text[:120], "target": target, "severity": "high" if any(k in low for k in ("critical", "breach", "cve", "alert")) else "medium", "source": "hermes-chat"})
        action_note = f"\n[Vigil SOC Case #{tr['case']['id']} · {tr['case']['mitre']}]"

    cur_status = get_status()
    ai_reply = hermes_complete(
        "You are Chappa V2, a standalone local-first defensive Cybersecurity Agent built on Hermes, "
        "combining Vigil AI SOC and God's Eye View 3D Globe. Keep answers sharp, tactical, and concise.\n"
        f"Current State: {cur_status['mask_state']} | Open Vigil Cases: {cur_status['open_alerts']} | Active Target: {cur_status['active_target'] or 'none'}\n"
        f"User: {text}",
        model=model,
    )
    reply = (ai_reply or f"[Chappa V2 · Hermes Core] Processed '{text}'. Vigil SOC ({cur_status['open_alerts']} open) & God's Eye View ({cur_status['pins_count']} pins) synced.") + action_note

    with _DB_LOCK:
        conn = _db()
        try:
            conn.execute("INSERT INTO chat_messages(role, content, model, created_at) VALUES ('assistant', ?, ?, ?)", (reply[:6000], model, time.time()))
            conn.commit()
        finally:
            conn.close()

    _broadcast("chat_reply", {"reply": reply, "model": model})
    return {"ok": True, "reply": reply, "model": model, "mask_state": get_status()["mask_state"], "status": get_status()}


MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".obj": "text/plain; charset=utf-8",
}


class ChappaHandler(BaseHTTPRequestHandler):
    server_version = "ChappaV2/2.1"

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
        if length <= 0 or length > 2 * 1024 * 1024:
            return {}
        try:
            obj = json.loads(self.rfile.read(length).decode("utf-8"))
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
        self.send_response(200)
        self.send_header("Content-Type", MIME_TYPES.get(target.suffix.lower(), "application/octet-stream"))
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
        if path == "/api/chappa/models":
            return self._send_json({"ok": True, "models": fetch_assimilis_models()})
        if path == "/api/chappa/chat":
            return self._send_json({"ok": True, "messages": get_status()["chat_history"]})
        if path == "/api/chappa/vigil/cases":
            return self._send_json({"ok": True, "cases": get_status()["cases"]})
        if path == "/api/chappa/globe/feed":
            st = get_status()
            return self._send_json({"ok": True, "pins": st["pins"], "focus": st["globe_focus"], "godseye_bridge": st["bridges"]["godseye"]})
        if path == "/api/chappa/modules":
            return self._send_json({"ok": True, "modules": list_hot_modules(), "modules_dir": str(MODULES_DIR)})
        if path == "/api/chappa/tools":
            qs = parse_qs(urlparse(self.path).query)
            one = lambda name, default="": (qs.get(name) or [default])[0]
            try:
                limit = int(one("limit", "500"))
                offset = int(one("offset", "0"))
            except ValueError:
                limit, offset = 500, 0
            res = chappa_tools.list_tools(
                team=one("team") or None,
                category=one("category") or None,
                phase=one("phase") or None,
                q=one("q") or None,
                limit=limit,
                offset=offset,
            )
            st = get_status()
            res["state"] = st["mask_state"]
            res["active_target"] = st["active_target"]
            res["allow_red"] = os.environ.get("CHAPPA_ALLOW_RED", "0").strip().lower() in {"1", "true", "yes", "on"}
            res["stats"] = chappa_tools.stats()
            return self._send_json(res)
        if path == "/api/chappa/tools/runs":
            qs = parse_qs(urlparse(self.path).query)
            try:
                limit = max(1, min(int((qs.get("limit") or ["20"])[0]), 200))
            except ValueError:
                limit = 20
            with _DB_LOCK:
                conn = _db()
                try:
                    rows = conn.execute(
                        "SELECT id, tool_id, title, team, argv, exit_code, duration_ms, output, created_at "
                        "FROM tool_runs ORDER BY id DESC LIMIT ?",
                        (limit,),
                    ).fetchall()
                finally:
                    conn.close()
            return self._send_json({"ok": True, "runs": [dict(r) for r in rows]})
        if path == "/api/chappa/custom-mask.obj":
            p = MODULES_DIR / "custom_mask.obj"
            if not p.is_file():
                self.send_response(HTTPStatus.NO_CONTENT)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            data = p.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/chappa/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q: queue.Queue[str] = queue.Queue(maxsize=32)
            with _SSE_LOCK:
                _SSE_SUBS.append(q)
            try:
                self.wfile.write(f"event: status\ndata: {json.dumps(get_status())}\n\n".encode("utf-8"))
                self.wfile.flush()
                for _ in range(120):
                    try:
                        chunk = q.get(timeout=15.0)
                        self.wfile.write(chunk.encode("utf-8"))
                        self.wfile.flush()
                    except queue.Empty:
                        self.wfile.write(b": heartbeat\n\n")
                        self.wfile.flush()
            except Exception:
                pass
            finally:
                with _SSE_LOCK:
                    if q in _SSE_SUBS:
                        _SSE_SUBS.remove(q)
            return
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
                        _set_kv(conn, "fps_cadence", "12" if str(body.get("fps_cadence")) == "12" else "60")
                    if "active_model" in body:
                        _set_kv(conn, "active_model", str(body.get("active_model") or "hermes-auto")[:120])
                    conn.commit()
                finally:
                    conn.close()
            st = get_status()
            _broadcast("status", st)
            return self._send_json(st)

        if path == "/api/chappa/tools/run":
            st = get_status()
            tool_id = str(body.get("id") or body.get("tool_id") or "")
            tool = chappa_tools.get_tool(tool_id) or {}
            try:
                timeout_s = int(body.get("timeout_s") or chappa_tools.DEFAULT_TIMEOUT_S)
            except (TypeError, ValueError):
                timeout_s = chappa_tools.DEFAULT_TIMEOUT_S
            result = chappa_tools.run_tool(
                tool_id,
                command=body.get("command"),
                timeout_s=timeout_s,
                dry_run=bool(body.get("dry_run")),
                state=st["mask_state"],
                active_target=st["active_target"],
                allow_red=body.get("allow_red") if "allow_red" in body else None,
            )
            # Only real executions are audited; a refused request leaves a
            # record of the attempt instead of polluting the run history.
            if not result.get("dry_run"):
                output = (result.get("stdout") or "") + (("\n" + result["stderr"]) if result.get("stderr") else "")
                if result.get("error"):
                    # A refused or failed attempt is still evidence: keep the
                    # reason next to the argv instead of an empty output cell.
                    output = f"[error] {result['error']}\n" + output
                with _DB_LOCK:
                    conn = _db()
                    try:
                        conn.execute(
                            "INSERT INTO tool_runs(tool_id, title, team, argv, exit_code, duration_ms, output, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                            (
                                tool_id,
                                tool.get("title", "")[:120],
                                tool.get("team", "")[:16],
                                " ".join(result.get("argv") or [])[:400],
                                result.get("exit_code"),
                                result.get("duration_ms"),
                                output[:4000],
                                time.time(),
                            ),
                        )
                        conn.commit()
                    finally:
                        conn.close()
            _broadcast(
                "tool_run",
                {
                    "tool_id": tool_id,
                    "title": tool.get("title", ""),
                    "team": tool.get("team", ""),
                    "ok": bool(result.get("ok")),
                    "error": result.get("error", ""),
                    "argv": result.get("argv", []),
                    "exit_code": result.get("exit_code"),
                },
            )
            return self._send_json(result)

        if path in ("/api/chappa/chat", "/api/chappa/command"):
            return self._send_json(handle_chat(body))

        if path == "/api/chappa/voice/speak":
            text = " ".join(str(body.get("text") or "").split())[:1200]
            if not text:
                return self._send_json({"ok": False, "error": "text is required"}, status=400)
            assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
            if not assimilis_url:
                return self._send_json({"ok": False, "error": "Assimilis Voice Studio bridge not connected", "fallback": "browser"}, status=200)
            payload = {
                "op": "speak",
                "text": text,
                "engine": str(body.get("engine") or "auto"),
                "persona": str(body.get("persona") or "jarvis"),
                "prefer_fish": body.get("prefer_fish", True) is not False,
            }
            if body.get("voice"):
                payload["voice"] = str(body.get("voice"))
            if body.get("fish_voice"):
                payload["fish_voice"] = str(body.get("fish_voice"))
            try:
                hdrs = {"Content-Type": "application/json"}
                cookie = self.headers.get("Cookie")
                if cookie:
                    hdrs["Cookie"] = cookie
                req = urllib.request.Request(
                    f"{assimilis_url}/api/world/voice",
                    data=json.dumps(payload).encode("utf-8"),
                    headers=hdrs,
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=22) as resp:
                    data = json.loads(resp.read().decode("utf-8", errors="replace"))
                    return self._send_json(data, status=resp.status)
            except Exception as exc:
                return self._send_json({"ok": False, "error": str(exc), "fallback": "browser"}, status=200)

        if path in ("/api/chappa/vigil/cases", "/api/chappa/vigil/triage", "/api/chappa/telemetry/ingest"):
            return self._send_json(vigil_create_or_triage(body, run_triage=(path != "/api/chappa/vigil/cases")))

        if path.startswith("/api/chappa/vigil/cases/") and path.endswith("/status"):
            parts = path.strip("/").split("/")
            try:
                cid = int(parts[4])
            except Exception:
                return self._send_json({"ok": False, "error": "Invalid case id"}, status=400)
            return self._send_json(update_case_status(cid, str(body.get("status") or "")))

        if path == "/api/chappa/telemetry/check":
            return self._send_json(defensive_posture_check(str(body.get("host") or body.get("target") or "")))

        if path == "/api/chappa/globe/focus":
            focus = {
                "lat": float(body.get("lat", 18.0179)),
                "lon": float(body.get("lon", -76.8099)),
                "label": str(body.get("label") or "TARGET")[:48],
            }
            with _DB_LOCK:
                conn = _db()
                try:
                    _set_kv(conn, "globe_focus", json.dumps(focus))
                    conn.commit()
                finally:
                    conn.close()
            _broadcast("globe_focus", focus)
            return self._send_json({"ok": True, "focus": focus})

        if path == "/api/chappa/globe/pin":
            now = time.time()
            with _DB_LOCK:
                conn = _db()
                try:
                    conn.execute(
                        "INSERT INTO globe_pins(label, ip, asn, severity, lat, lon, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(body.get("label") or "PIN")[:48],
                            str(body.get("ip") or "")[:64],
                            str(body.get("asn") or "INTEL")[:32],
                            str(body.get("severity") or "info")[:16],
                            float(body.get("lat", 0.0)),
                            float(body.get("lon", 0.0)),
                            str(body.get("notes") or "")[:200],
                            now,
                        ),
                    )
                    conn.commit()
                finally:
                    conn.close()
            st = get_status()
            _broadcast("globe_pins", {"pins": st["pins"]})
            return self._send_json({"ok": True, "pins": st["pins"]})

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
