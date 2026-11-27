"""Real Full Vigil AI SOC REST API Client (apps/vigil on 127.0.0.1:16987).

Talks directly to Full Vigil's FastAPI + PostgreSQL backend:
  - GET  /api/health
  - GET  /api/v1/cases
  - POST /api/v1/cases
  - PATCH /api/v1/cases/{case_id}
  - GET  /api/v1/findings
  - GET  /api/v1/workflows
  - POST /api/ingest/ingest-string
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from typing import Any

from runtime_manager import VIGIL_URL


def _req_json(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 4.0) -> tuple[bool, Any]:
    url = f"{VIGIL_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return True, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(exc)
        return False, {"error": f"HTTP {exc.code}: {err_body[:300]}", "status": exc.code}
    except Exception as exc:
        return False, {"error": str(exc)}


def _req_form(path: str, fields: dict[str, str], timeout: float = 6.0) -> tuple[bool, Any]:
    url = f"{VIGIL_URL}{path}"
    encoded = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return True, json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = str(exc)
        return False, {"error": f"HTTP {exc.code}: {err_body[:300]}", "status": exc.code}
    except Exception as exc:
        return False, {"error": str(exc)}


def health() -> dict[str, Any]:
    ok, data = _req_json("GET", "/api/health", timeout=1.2)
    if ok and isinstance(data, dict):
        return {"live": True, **data}
    return {"live": False, "error": (data or {}).get("error", "unreachable") if isinstance(data, dict) else "unreachable"}


def list_cases(limit: int = 25, closed: bool | None = None) -> dict[str, Any]:
    qs = f"?limit={max(1, min(limit, 100))}"
    if closed is not None:
        qs += f"&closed={'true' if closed else 'false'}"
    ok, data = _req_json("GET", f"/api/v1/cases{qs}", timeout=2.5)
    if not ok or not isinstance(data, dict):
        return {"ok": False, "cases": [], "total": 0, "error": (data or {}).get("error", "unavailable")}
    cases = data.get("cases") or []
    return {
        "ok": True,
        "cases": cases,
        "total": int(data.get("total", len(cases))),
        "strip": data.get("strip") or {},
    }


def list_findings(limit: int = 25) -> dict[str, Any]:
    ok, data = _req_json("GET", f"/api/v1/findings?limit={max(1, min(limit, 100))}", timeout=2.5)
    if not ok or not isinstance(data, dict):
        return {"ok": False, "findings": [], "total": 0, "error": (data or {}).get("error", "unavailable")}
    findings = data.get("findings") or []
    return {
        "ok": True,
        "findings": findings,
        "total": int(data.get("total", len(findings))),
    }


def list_workflows() -> dict[str, Any]:
    ok, data = _req_json("GET", "/api/v1/workflows", timeout=2.5)
    if not ok or not isinstance(data, dict):
        return {"ok": False, "workflows": [], "error": (data or {}).get("error", "unavailable")}
    return {"ok": True, "workflows": data.get("workflows") or []}


def ingest_finding(
    *,
    title: str,
    target: str = "",
    severity: str = "medium",
    mitre: str = "T1595",
    description: str = "",
    source: str = "chappa-v2",
    lat: float | None = None,
    lon: float | None = None,
    raw_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Ingest a real finding record into Full Vigil PostgreSQL."""
    sev = severity.lower() if severity else "medium"
    if sev not in ("critical", "high", "medium", "low", "info"):
        sev = "medium"
    finding_id = f"chappa-{uuid.uuid4().hex[:12]}"
    mitre_code = (mitre.split()[0] if mitre else "T1595").strip("·,- ")
    entity_context: dict[str, Any] = {"target": target or "local", "origin": "chappa-v2"}
    if target:
        if any(c.isdigit() for c in target) and "." in target and not any(c.isalpha() for c in target):
            entity_context["src_ip"] = target
        else:
            entity_context["hostname"] = target
    if lat is not None and lon is not None:
        entity_context["geo"] = {"lat": float(lat), "lon": float(lon)}

    payload = {
        "findings": [
            {
                "id": finding_id,
                "title": title[:200],
                "description": (description or f"Chappa V2 defensive telemetry on {target or 'local'}")[:2000],
                "severity": sev,
                "source": source[:48],
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "mitre_techniques": {mitre_code: 0.9},
                "iocs": entity_context,
                "raw_data": raw_data or {
                    "title": title,
                    "target": target,
                    "severity": sev,
                    "mitre": mitre,
                    "summary": description,
                },
            }
        ]
    }
    ok, res = _req_form(
        "/api/ingest/ingest-string",
        {
            "data": json.dumps(payload),
            "format": "json",
            "data_type": "finding",
        },
        timeout=6.0,
    )
    if not ok:
        return {"ok": False, "finding_id": finding_id, "error": res.get("error", "ingest failed") if isinstance(res, dict) else str(res)}
    return {"ok": True, "finding_id": finding_id, "stats": res}


def create_case(
    *,
    title: str,
    description: str = "",
    finding_ids: list[str] | None = None,
    priority: str = "medium",
    status: str = "open",
) -> dict[str, Any]:
    prio = priority.lower() if priority else "medium"
    if prio not in ("critical", "high", "medium", "low"):
        prio = "medium"
    ok, res = _req_json(
        "POST",
        "/api/v1/cases",
        {
            "title": title[:200],
            "description": description[:4000],
            "finding_ids": list(finding_ids or []),
            "priority": prio,
            "status": status,
        },
        timeout=6.0,
    )
    if not ok or not isinstance(res, dict):
        return {"ok": False, "error": res.get("error", "create_case failed") if isinstance(res, dict) else str(res)}
    return {"ok": True, "case": res}


def update_case_status(case_id: str, next_status: str, notes: str | None = None) -> dict[str, Any]:
    mapped = {
        "open": "open",
        "investigating": "in_progress",
        "in_progress": "in_progress",
        "contained": "in_progress",
        "closed": "closed",
        "resolved": "closed",
    }.get(next_status.lower(), "in_progress")
    body: dict[str, Any] = {"status": mapped}
    if notes:
        body["notes"] = notes
    elif next_status.lower() == "contained":
        body["notes"] = "Marked CONTAINED from Chappa V2 Command Core."
    ok, res = _req_json("PATCH", f"/api/v1/cases/{urllib.parse.quote(str(case_id), safe='')}", body, timeout=5.0)
    if not ok:
        return {"ok": False, "error": res.get("error", "update_case failed") if isinstance(res, dict) else str(res)}
    return {"ok": True, "result": res, "status": mapped}


def normalize_case_for_hud(case: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Full Vigil case record into the Chappa V2 HUD summary shape."""
    cid = str(case.get("case_id") or case.get("id") or "")
    sev = str(case.get("priority") or case.get("severity") or "medium").lower()
    st = str(case.get("status") or case.get("combined_state") or "open").lower()
    return {
        "id": cid,
        "case_id": cid,
        "title": str(case.get("title") or "Vigil Case"),
        "target": str(case.get("data_source") or case.get("assignee") or "vigil-soc"),
        "severity": sev,
        "priority": sev,
        "status": st,
        "mitre": ", ".join(case.get("mitre_techniques") or []) or "Vigil AI SOC",
        "verdict": str(case.get("description") or case.get("summary") or "Managed in Full Vigil SOC"),
        "source": "vigil-full",
        "created_at": case.get("created_at") or "",
    }
