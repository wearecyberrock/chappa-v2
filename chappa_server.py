"""Chappa V2 — Standalone Local-First Cybersecurity Core Agent.

Unifies:
  - Modified Hermes WebUI Core + Red Matrix floating 3D 1/0 Hacker Mask + Fish/Voice Studio glowing eyes
  - Real Full Vigil AI SOC (apps/vigil: FastAPI + PostgreSQL + React SOC + Workflows + /mcp) at /vigil/
  - Real Full God's Eye View (apps/gods-eye-view: 3D Cesium Globe + Live Providers + /mcp) at /godseye/
  - Real Hermes Engine (Assimilis unified model router / standalone ~/.hermes/.env + live tool calling)
  - Read-only defensive posture telemetry (DNS, TLS cert, HTTP security headers) + hot modules
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
from urllib.parse import urlparse

import hermes_bridge
import reverse_proxy
import vigil_client
from runtime_manager import GODSEYE_URL, MANAGER, STATE_DIR, VIGIL_URL

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "static"
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
                    vigil_case_id TEXT NOT NULL DEFAULT '',
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
                """
            )
            # Migrate existing DBs that lack vigil_case_id
            cols = {r[1] for r in conn.execute("PRAGMA table_info(vigil_cases)").fetchall()}
            if "vigil_case_id" not in cols:
                conn.execute("ALTER TABLE vigil_cases ADD COLUMN vigil_case_id TEXT NOT NULL DEFAULT ''")

            defaults = {
                "mask_state": "IDLE",
                "active_target": "",
                "fps_cadence": "60",
                "active_model": os.environ.get("CHAPPA_DEFAULT_MODEL", "hermes-auto"),
                "globe_focus": json.dumps({"lat": 18.0179, "lon": -76.8099, "alt": 850000, "label": "KINGSTON HQ"}),
            }
            for k, v in defaults.items():
                conn.execute("INSERT OR IGNORE INTO runtime_state(k, v) VALUES (?, ?)", (k, v))

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
            local_cases = [dict(r) for r in conn.execute("SELECT * FROM vigil_cases ORDER BY id DESC LIMIT 20").fetchall()]
            local_open = conn.execute("SELECT COUNT(*) FROM vigil_cases WHERE status IN ('open', 'investigating')").fetchone()[0]
            pins = [dict(r) for r in conn.execute("SELECT * FROM globe_pins ORDER BY id DESC LIMIT 30").fetchall()]
            chats = [dict(r) for r in conn.execute("SELECT * FROM chat_messages ORDER BY id DESC LIMIT 30").fetchall()]
            chats.reverse()
        finally:
            conn.close()

    try:
        globe_focus = json.loads(focus_raw)
    except Exception:
        globe_focus = {"lat": 18.0179, "lon": -76.8099, "alt": 850000, "label": "KINGSTON HQ"}

    services = MANAGER.status()
    vigil_live = bool((services.get("vigil") or {}).get("live"))
    godseye_live = bool((services.get("godseye") or {}).get("live"))

    cases: list[dict[str, Any]] = local_cases
    findings_count = 0
    workflows: list[dict[str, Any]] = []
    open_alerts = int(local_open)
    vigil_total_cases = len(local_cases)

    if vigil_live:
        vc = vigil_client.list_cases(limit=25)
        vf = vigil_client.list_findings(limit=25)
        vw = vigil_client.list_workflows()
        if vc.get("ok"):
            cases = [vigil_client.normalize_case_for_hud(c) for c in (vc.get("cases") or [])]
            vigil_total_cases = int(vc.get("total", len(cases)))
            open_alerts = sum(1 for c in cases if str(c.get("status", "")).lower() not in ("closed", "resolved", "dismissed"))
        if vf.get("ok"):
            findings_count = int(vf.get("total", len(vf.get("findings") or [])))
        if vw.get("ok"):
            workflows = [
                {
                    "id": w.get("id") or w.get("name"),
                    "name": w.get("name") or w.get("id"),
                    "description": str(w.get("description") or "")[:180],
                }
                for w in (vw.get("workflows") or [])[:20]
            ]

    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip()
    hermes_st = hermes_bridge.engine_status()
    custom_obj = (MODULES_DIR / "custom_mask.obj").is_file()

    return {
        "ok": True,
        "agent": "chappa-v2",
        "name": "Chappa V2",
        "version": "2.2.0",
        "mask_state": mask_state,
        "active_target": active_target,
        "fps_cadence": fps_cadence,
        "active_model": active_model,
        "open_alerts": open_alerts,
        "cases_count": vigil_total_cases,
        "findings_count": findings_count,
        "workflows_count": len(workflows),
        "workflows": workflows,
        "pins_count": len(pins),
        "cases": cases,
        "pins": pins,
        "globe_focus": globe_focus,
        "chat_history": chats,
        "hot_modules": list_hot_modules(),
        "modules_dir": str(MODULES_DIR),
        "custom_mask_loaded": custom_obj,
        "services": services,
        "bridges": {
            "assimilis": {"connected": bool(assimilis_url), "url": assimilis_url},
            "hermes": hermes_st,
            "vigil": {
                "live": vigil_live,
                "mode": "full-vigil-soc" if vigil_live else ("booting" if services["vigil"]["booting"] else "offline-cache"),
                "url": VIGIL_URL,
                "mount": "vigil/",
            },
            "godseye": {
                "live": godseye_live,
                "external_live": godseye_live,
                "mode": "full-cesium-globe" if godseye_live else ("booting" if services["godseye"]["booting"] else "offline"),
                "url": GODSEYE_URL,
                "mount": "godseye/?embed=1",
            },
        },
    }


def _set_mask_state_internal(state: str, active_target: str | None = None) -> str:
    ms = state.upper() if state else "IDLE"
    if ms not in VALID_STATES:
        ms = "IDLE"
    with _DB_LOCK:
        conn = _db()
        try:
            _set_kv(conn, "mask_state", ms)
            if active_target is not None:
                _set_kv(conn, "active_target", active_target[:200])
            conn.commit()
        finally:
            conn.close()
    return ms


def vigil_create_or_triage(payload: dict[str, Any], *, run_triage: bool = True) -> dict[str, Any]:
    """Create a real finding & case in Full Vigil AI SOC (with SQLite fallback if Vigil is offline)."""
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
            mitre = "T1557"
        elif any(k in low for k in ("dns", "domain", "phish", "c2", "beacon")):
            mitre = "T1071"
        elif any(k in low for k in ("login", "brute", "auth", "cred", "ssh")):
            mitre = "T1110"
        else:
            mitre = "T1595"

    verdict = str(payload.get("verdict") or payload.get("description") or "").strip()
    remediation = str(payload.get("remediation") or "").strip()
    if run_triage and not verdict:
        ok_llm, ai_txt, _prov = hermes_bridge.complete(
            [{"role": "user", "content": (
                f"Triage this defensive security alert concisely in 2 short sentences (Verdict + Remediation).\n"
                f"Title: {title}\nTarget/IOC: {target or 'n/a'}\nSeverity: {severity}\nMITRE: {mitre}"
            )}],
            system_prompt="You are Vigil AI SOC inside Chappa V2 (defensive security operations). Be sharp and concise.",
        )
        verdict = ai_txt if ok_llm and ai_txt else (
            f"Classified as {severity.upper()} defensive telemetry ({mitre}). "
            f"Correlated IOC '{target or 'local'}' ingested into Full Vigil AI SOC."
        )
    if not remediation:
        remediation = "1) Verify asset ownership & logs  2) Enforce TLS/CSP/firewall rules  3) Close case in Vigil once contained."

    lat = payload.get("lat")
    lon = payload.get("lon")
    now = time.time()
    next_mask = "ALERT" if severity in ("critical", "high") else "RECON"

    # Primary path: write directly into REAL Full Vigil AI SOC (PostgreSQL + FastAPI)
    vigil_finding_id = ""
    vigil_case_obj: dict[str, Any] | None = None
    vigil_case_id = ""
    vigil_live = bool(MANAGER.status()["vigil"]["live"])
    if vigil_live:
        ing = vigil_client.ingest_finding(
            title=title,
            target=target,
            severity=severity,
            mitre=mitre,
            description=f"{verdict}\n\nRemediation: {remediation}",
            source=str(payload.get("source") or "chappa-v2"),
            lat=float(lat) if lat is not None else None,
            lon=float(lon) if lon is not None else None,
            raw_data={"title": title, "target": target, "severity": severity, "mitre": mitre, "verdict": verdict},
        )
        if ing.get("ok"):
            vigil_finding_id = str(ing.get("finding_id") or "")
        prio = severity if severity in ("critical", "high", "medium", "low") else "low"
        created = vigil_client.create_case(
            title=title,
            description=f"Target/IOC: {target or 'n/a'}\nMITRE: {mitre}\n\n{verdict}\n\nRemediation: {remediation}",
            finding_ids=[vigil_finding_id] if vigil_finding_id else [],
            priority=prio,
            status="open",
        )
        if created.get("ok") and isinstance(created.get("case"), dict):
            vigil_case_obj = created["case"]
            vigil_case_id = str(vigil_case_obj.get("case_id") or "")

    with _DB_LOCK:
        conn = _db()
        try:
            cur = conn.execute(
                """
                INSERT INTO vigil_cases(vigil_case_id, title, target, severity, status, mitre, verdict, remediation, source, lat, lon, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    vigil_case_id,
                    title[:160],
                    target[:180],
                    severity,
                    mitre[:80],
                    verdict[:600],
                    remediation[:400],
                    "vigil-full" if vigil_case_id else str(payload.get("source") or "vigil"),
                    lat,
                    lon,
                    now,
                    now,
                ),
            )
            local_id = cur.lastrowid
            _set_kv(conn, "mask_state", next_mask)
            if target:
                _set_kv(conn, "active_target", target[:180])
            if lat is not None and lon is not None:
                conn.execute(
                    "INSERT INTO globe_pins(label, ip, asn, severity, lat, lon, notes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (title[:48], target[:64], str(payload.get("asn") or "SOC-PIN"), severity, float(lat), float(lon), verdict[:180], now),
                )
                focus_obj = {"lat": float(lat), "lon": float(lon), "alt": 850000, "label": title[:40]}
                _set_kv(conn, "globe_focus", json.dumps(focus_obj))
            conn.commit()
            local_row = dict(conn.execute("SELECT * FROM vigil_cases WHERE id = ?", (local_id,)).fetchone())
        finally:
            conn.close()

    out_case = vigil_client.normalize_case_for_hud(vigil_case_obj) if vigil_case_obj else local_row
    out_case["finding_id"] = vigil_finding_id
    out_case["lat"] = lat
    out_case["lon"] = lon
    _broadcast("vigil_case", out_case)
    if lat is not None and lon is not None:
        _broadcast("globe_focus", {"lat": float(lat), "lon": float(lon), "alt": 850000, "label": title[:40]})
    return {
        "ok": True,
        "case": out_case,
        "vigil_backend": "full-vigil-soc" if vigil_case_id else "local-cache",
        "finding_id": vigil_finding_id,
        "mask_state": next_mask,
    }


def update_case_status(case_id: str, next_status: str, notes: str | None = None) -> dict[str, Any]:
    if next_status not in ("open", "investigating", "in_progress", "contained", "closed", "resolved"):
        return {"ok": False, "error": "Invalid status"}

    vigil_updated = False
    if MANAGER.status()["vigil"]["live"]:
        res = vigil_client.update_case_status(str(case_id), next_status, notes=notes)
        vigil_updated = bool(res.get("ok"))

    now = time.time()
    with _DB_LOCK:
        conn = _db()
        try:
            if str(case_id).isdigit():
                conn.execute("UPDATE vigil_cases SET status = ?, updated_at = ? WHERE id = ?", (next_status, now, int(case_id)))
            else:
                conn.execute("UPDATE vigil_cases SET status = ?, updated_at = ? WHERE vigil_case_id = ?", (next_status, now, str(case_id)))
            if next_status in ("contained", "closed", "resolved"):
                _set_kv(conn, "mask_state", "CONTAINED")
            conn.commit()
        finally:
            conn.close()

    st = get_status()
    _broadcast("status", st)
    return {"ok": True, "case_id": case_id, "status_set": next_status, "vigil_synced": vigil_updated, "status": st}


def focus_globe(lat: float, lon: float, label: str = "TARGET", alt: float = 850000.0) -> dict[str, Any]:
    focus = {
        "lat": float(lat),
        "lon": float(lon),
        "alt": float(alt),
        "label": str(label or "TARGET")[:48],
    }
    with _DB_LOCK:
        conn = _db()
        try:
            _set_kv(conn, "globe_focus", json.dumps(focus))
            conn.commit()
        finally:
            conn.close()
    _broadcast("globe_focus", focus)
    return {"ok": True, "focus": focus}


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

    req_headers = ["strict-transport-security", "content-security-policy", "x-frame-options", "x-content-type-options"]
    try:
        req = urllib.request.Request(f"https://{clean}/", method="HEAD", headers={"User-Agent": "ChappaV2-DefensiveAudit/2.2"})
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
    hval = sum(ord(c) for c in clean)
    lat = round(((hval * 17) % 100) - 45.0, 3)
    lon = round(((hval * 31) % 280) - 140.0, 3)

    triage = vigil_create_or_triage(
        {
            "title": f"Posture Check · {clean}",
            "target": report["ips"][0] if report["ips"] else clean,
            "severity": sev,
            "mitre": "T1557",
            "verdict": summary,
            "lat": lat,
            "lon": lon,
            "asn": report["ips"][0] if report["ips"] else "DNS",
            "source": "defensive-check",
        },
        run_triage=False,
    )
    return {"ok": True, "report": report, "case": triage["case"], "vigil_backend": triage["vigil_backend"], "status": get_status()}


def _execute_hermes_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    if name == "vigil_triage":
        return vigil_create_or_triage(args, run_triage=False)
    if name == "vigil_update_case":
        return update_case_status(str(args.get("case_id") or ""), str(args.get("status") or "in_progress"), notes=args.get("notes"))
    if name == "vigil_list_workflows":
        return vigil_client.list_workflows()
    if name == "godseye_fly_to":
        return focus_globe(
            float(args.get("lat", 18.0179)),
            float(args.get("lon", -76.8099)),
            str(args.get("label") or "TARGET"),
            float(args.get("alt", 850000)),
        )
    if name == "defensive_posture_check":
        return defensive_posture_check(str(args.get("host") or args.get("target") or ""))
    if name == "set_mask_state":
        ms = _set_mask_state_internal(str(args.get("state") or "IDLE"))
        _broadcast("status", get_status())
        return {"ok": True, "mask_state": ms}
    return {"ok": False, "error": f"Unknown tool: {name}"}


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
            history = [dict(r) for r in conn.execute("SELECT role, content FROM chat_messages ORDER BY id DESC LIMIT 14").fetchall()]
            history.reverse()
        finally:
            conn.close()

    status_before = get_status()
    agent_res = hermes_bridge.run_agent_turn(
        user_text=text if not target else f"{text} (target: {target})",
        history=history,
        status_snapshot=status_before,
        tool_executor=_execute_hermes_tool,
        model=model,
    )

    tools_used = list(agent_res.get("tools") or [])
    provider = str(agent_res.get("provider") or "")

    if agent_res.get("ok") and agent_res.get("reply"):
        reply = str(agent_res["reply"])
        if tools_used:
            tool_summary = ", ".join(t["tool"] for t in tools_used)
            reply = f"{reply}\n[Hermes Tools Executed: {tool_summary}]"
    else:
        # Even without an active LLM API key, still run explicit defensive/Vigil/God's Eye commands honestly
        low = text.lower()
        action_notes: list[str] = []
        if any(w in low for w in ("contain", "lock", "resolve")):
            _set_mask_state_internal("CONTAINED")
            action_notes.append("Mask state set to CONTAINED.")
        elif any(w in low for w in ("posture", "audit", "check tls", "check dns", "inspect")) and (target or "." in text):
            host = target or next((tok.strip(".,;:()\"'") for tok in text.split() if "." in tok and not tok.startswith("http")), "")
            if host:
                chk = defensive_posture_check(host)
                if chk.get("ok"):
                    action_notes.append(f"Defensive audit logged to {chk['vigil_backend']} (Case {chk['case'].get('id')}): {chk['case'].get('verdict')}")
        elif any(w in low for w in ("triage", "alert", "incident", "threat", "cve", "ioc")):
            sev = "high" if any(k in low for k in ("critical", "high", "breach", "cve", "alert")) else "medium"
            tr = vigil_create_or_triage({"title": text[:120], "target": target, "severity": sev, "source": "hermes-chat"}, run_triage=False)
            action_notes.append(f"Created real Vigil case {tr['case'].get('id')} ({tr['vigil_backend']}).")

        st_now = get_status()
        err_hint = agent_res.get("error") or "No LLM provider configured"
        if action_notes:
            reply = "\n".join(action_notes) + f"\n(Hermes LLM note: {err_hint} — connect a model in Assimilis or ~/.hermes/.env for full conversational reasoning.)"
        else:
            reply = (
                f"[Chappa V2 · Hermes Engine] Full Vigil AI SOC ({st_now['bridges']['vigil']['mode']}, "
                f"{st_now['open_alerts']} open cases, {st_now['workflows_count']} playbooks) & "
                f"Full God's Eye View ({st_now['bridges']['godseye']['mode']}) are wired.\n"
                f"LLM provider unavailable ({err_hint}). Select an active model in Assimilis or set a key in ~/.hermes/.env."
            )

    with _DB_LOCK:
        conn = _db()
        try:
            conn.execute("INSERT INTO chat_messages(role, content, model, created_at) VALUES ('assistant', ?, ?, ?)", (reply[:6000], provider or model, time.time()))
            conn.commit()
        finally:
            conn.close()

    st_after = get_status()
    _broadcast("chat_reply", {"reply": reply, "model": provider or model, "tools": tools_used})
    return {
        "ok": True,
        "reply": reply,
        "model": provider or model,
        "tools": tools_used,
        "mask_state": st_after["mask_state"],
        "status": st_after,
    }


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
    server_version = "ChappaV2/2.2"

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_json(self, data: Any, status: int = 200) -> None:
        raw = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
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
        if self.command != "HEAD":
            self.wfile.write(data)

    def _maybe_proxy_upstream(self, method: str) -> bool:
        path = urlparse(self.path).path
        if path == "/vigil" or path.startswith("/vigil/"):
            reverse_proxy.proxy_vigil(self, method)
            return True
        if path == "/godseye" or path.startswith("/godseye/"):
            reverse_proxy.proxy_godseye(self, method)
            return True
        return False

    def do_OPTIONS(self) -> None:
        if self._maybe_proxy_upstream("OPTIONS"):
            return
        self.send_response(204)
        self.send_header("Allow", "GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def do_HEAD(self) -> None:
        if self._maybe_proxy_upstream("HEAD"):
            return
        self.do_GET()

    def do_PUT(self) -> None:
        if self._maybe_proxy_upstream("PUT"):
            return
        self._send_json({"ok": False, "error": "Unsupported PUT path"}, status=404)

    def do_PATCH(self) -> None:
        if self._maybe_proxy_upstream("PATCH"):
            return
        self._send_json({"ok": False, "error": "Unsupported PATCH path"}, status=404)

    def do_DELETE(self) -> None:
        if self._maybe_proxy_upstream("DELETE"):
            return
        self._send_json({"ok": False, "error": "Unsupported DELETE path"}, status=404)

    def do_GET(self) -> None:
        if self._maybe_proxy_upstream("GET"):
            return
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._serve_file("index.html")
        if path == "/embed":
            return self._serve_file("embed.html")
        if path == "/api/chappa/status":
            return self._send_json(get_status())
        if path == "/api/chappa/services":
            return self._send_json({"ok": True, "services": MANAGER.status()})
        if path == "/api/chappa/models":
            return self._send_json({"ok": True, "models": hermes_bridge.fetch_models()})
        if path == "/api/chappa/chat":
            return self._send_json({"ok": True, "messages": get_status()["chat_history"]})
        if path == "/api/chappa/vigil/cases":
            return self._send_json({"ok": True, "cases": get_status()["cases"]})
        if path == "/api/chappa/vigil/findings":
            return self._send_json(vigil_client.list_findings(limit=50))
        if path == "/api/chappa/vigil/workflows":
            return self._send_json(vigil_client.list_workflows())
        if path == "/api/chappa/globe/feed":
            st = get_status()
            return self._send_json({"ok": True, "pins": st["pins"], "focus": st["globe_focus"], "godseye_bridge": st["bridges"]["godseye"]})
        if path == "/api/chappa/modules":
            return self._send_json({"ok": True, "modules": list_hot_modules(), "modules_dir": str(MODULES_DIR)})
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
            if self.command != "HEAD":
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
        if self._maybe_proxy_upstream("POST"):
            return
        path = urlparse(self.path).path
        body = self._read_json()

        if path == "/api/chappa/services/control":
            svc = str(body.get("service") or "all").strip().lower()
            act = str(body.get("action") or "start").strip().lower()
            if act == "stop":
                st = MANAGER.stop_service(svc)
            elif act == "restart":
                MANAGER.stop_service(svc)
                st = MANAGER.start_service(svc)
            else:
                st = MANAGER.start_service(svc)
            _broadcast("status", get_status())
            return self._send_json({"ok": True, "services": st})

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
            cid = parts[4] if len(parts) > 4 else ""
            if not cid:
                return self._send_json({"ok": False, "error": "Invalid case id"}, status=400)
            return self._send_json(update_case_status(cid, str(body.get("status") or ""), notes=body.get("notes")))

        if path == "/api/chappa/telemetry/check":
            return self._send_json(defensive_posture_check(str(body.get("host") or body.get("target") or "")))

        if path == "/api/chappa/globe/focus":
            return self._send_json(
                focus_globe(
                    float(body.get("lat", 18.0179)),
                    float(body.get("lon", -76.8099)),
                    str(body.get("label") or "TARGET"),
                    float(body.get("alt", 850000)),
                )
            )

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
    MANAGER.start_all_async(on_change=lambda _svc: _broadcast("status", get_status()))
    host = os.environ.get("CHAPPA_HOST", "127.0.0.1")
    port = int(os.environ.get("CHAPPA_PORT", "7480"))
    srv = ThreadingHTTPServer((host, port), ChappaHandler)
    print(f"[chappa-v2] listening on http://{host}:{port} (state: {STATE_DIR}) | Vigil -> /vigil/ | God's Eye -> /godseye/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.shutdown_children()
        srv.server_close()


if __name__ == "__main__":
    main()
