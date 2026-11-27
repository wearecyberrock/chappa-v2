"""Real Hermes Engine & Tool-Calling Agent Bridge for Chappa V2.

Connects Chappa V2's chat & orchestration to the REAL Hermes Engine:
  1. Primary: Assimilis Unified Model Router (/api/models/all + /api/world/models/complete)
     supporting @antigravity:*, Ollama, OpenAI, Anthropic, Gemini, OpenRouter, etc.
  2. Standalone fallback: direct ~/.hermes/.env or local Ollama when running outside Assimilis.
  3. Structured tool-calling loop driving REAL Full Vigil AI SOC (/api/v1/*),
     REAL Full God's Eye View (3D Cesium camera + pins), read-only defensive posture
     checks, and the 3D Hacker Mask operational state.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


def _load_hermes_env() -> dict[str, str]:
    env_map: dict[str, str] = {}
    env_file = Path.home() / ".hermes" / ".env"
    if not env_file.is_file():
        return env_map
    try:
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and v:
                env_map[k] = v
    except Exception:
        pass
    return env_map


def _get_env(key: str, fallback_map: dict[str, str]) -> str:
    return (os.environ.get(key) or fallback_map.get(key) or "").strip()


def fetch_models() -> list[dict[str, Any]]:
    base = [{"id": "hermes-auto", "label": "Hermes Auto (Assimilis + Antigravity)", "provider": "hermes", "type": "text"}]
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
                    return base + (text_models or models)[:60]
        except Exception:
            pass
    # Also probe local Ollama when standalone
    ollama_models: list[dict[str, Any]] = []
    try:
        ollama_base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        with urllib.request.urlopen(f"{ollama_base}/api/tags", timeout=1.0) as r:
            tags = json.loads(r.read().decode("utf-8"))
            for m in (tags.get("models") or [])[:15]:
                name = m.get("name")
                if name:
                    ollama_models.append({"id": f"ollama:{name}", "label": f"Local Ollama · {name}", "provider": "ollama", "type": "text"})
    except Exception:
        pass
    if ollama_models:
        return base + ollama_models
    return base + [
        {"id": "@antigravity:gemini-2.5-pro", "label": "Antigravity · Gemini 2.5 Pro", "provider": "antigravity", "type": "text"},
        {"id": "ollama:qwen2.5:14b", "label": "Local Ollama · Qwen 2.5 14B", "provider": "ollama", "type": "text"},
    ]


def _complete_via_assimilis(
    messages: list[dict[str, str]],
    *,
    system_prompt: str,
    model: str = "",
) -> tuple[bool, str, str]:
    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
    if not assimilis_url:
        return False, "", ""
    body: dict[str, Any] = {
        "messages": messages,
        "system": system_prompt,
    }
    if model and model != "hermes-auto":
        body["model"] = model
    try:
        req = urllib.request.Request(
            f"{assimilis_url}/api/world/models/complete",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            txt = str(data.get("text") or data.get("reply") or data.get("content") or "").strip()
            used_model = str(data.get("model") or model or "assimilis-hermes")
            if data.get("ok") and txt:
                return True, txt, f"assimilis:{used_model}"
            return False, str(data.get("error") or ""), ""
    except Exception as exc:
        return False, str(exc), ""


def _complete_via_openai_compat(
    endpoint: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, str]],
    system_prompt: str,
    provider_label: str,
) -> tuple[bool, str, str]:
    full_msgs = [{"role": "system", "content": system_prompt}] + messages
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {"model": model_name, "messages": full_msgs, "temperature": 0.2}
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
            choices = data.get("choices") or []
            if choices and isinstance(choices[0], dict):
                txt = str((choices[0].get("message") or {}).get("content") or "").strip()
                if txt:
                    return True, txt, f"{provider_label}:{model_name}"
    except Exception as exc:
        return False, str(exc), ""
    return False, "", ""


def _complete_standalone(
    messages: list[dict[str, str]],
    *,
    system_prompt: str,
    model: str = "",
) -> tuple[bool, str, str]:
    env_map = _load_hermes_env()

    # 1. Explicit Ollama model or local Ollama server
    ollama_base = _get_env("OLLAMA_HOST", env_map) or "http://127.0.0.1:11434"
    if model.startswith("ollama:"):
        ok, txt, prov = _complete_via_openai_compat(
            f"{ollama_base.rstrip('/')}/v1/chat/completions",
            "",
            model.split(":", 1)[1],
            messages,
            system_prompt,
            "ollama",
        )
        if ok:
            return ok, txt, prov

    # 2. OpenRouter / OpenAI from ~/.hermes/.env or environment
    openrouter_key = _get_env("OPENROUTER_API_KEY", env_map)
    if openrouter_key:
        m = model if (model and model != "hermes-auto" and not model.startswith("@")) else "anthropic/claude-3.5-sonnet"
        ok, txt, prov = _complete_via_openai_compat(
            "https://openrouter.ai/api/v1/chat/completions",
            openrouter_key,
            m,
            messages,
            system_prompt,
            "openrouter",
        )
        if ok:
            return ok, txt, prov

    openai_key = _get_env("OPENAI_API_KEY", env_map)
    if openai_key:
        m = model if (model and model != "hermes-auto" and not model.startswith("@")) else "gpt-4o-mini"
        ok, txt, prov = _complete_via_openai_compat(
            "https://api.openai.com/v1/chat/completions",
            openai_key,
            m,
            messages,
            system_prompt,
            "openai",
        )
        if ok:
            return ok, txt, prov

    # 3. Auto-fallback to local Ollama if running
    try:
        with urllib.request.urlopen(f"{ollama_base.rstrip('/')}/api/tags", timeout=0.8) as r:
            tags = json.loads(r.read().decode("utf-8"))
            first = ((tags.get("models") or [{}])[0]).get("name")
            if first:
                ok, txt, prov = _complete_via_openai_compat(
                    f"{ollama_base.rstrip('/')}/v1/chat/completions",
                    "",
                    first,
                    messages,
                    system_prompt,
                    "ollama",
                )
                if ok:
                    return ok, txt, prov
    except Exception:
        pass

    return False, "No live LLM provider reached via Assimilis or ~/.hermes/.env", ""


def complete(
    messages: list[dict[str, str]],
    *,
    system_prompt: str,
    model: str = "",
) -> tuple[bool, str, str]:
    ok, txt, prov = _complete_via_assimilis(messages, system_prompt=system_prompt, model=model)
    if ok:
        return True, txt, prov
    return _complete_standalone(messages, system_prompt=system_prompt, model=model)


def build_system_prompt(status_snapshot: dict[str, Any]) -> str:
    svcs = status_snapshot.get("services") or {}
    vigil_st = svcs.get("vigil") or {}
    gev_st = svcs.get("godseye") or {}
    cases = status_snapshot.get("cases") or []
    wfs = status_snapshot.get("workflows") or []
    wf_names = ", ".join(str(w.get("id") or w.get("name") or "") for w in wfs[:8]) or "none loaded"

    return (
        "You are Chappa V2, a standalone local-first DEFENSIVE Cybersecurity Operations Agent "
        "built on the Hermes Engine, integrating Full Vigil AI SOC (PostgreSQL + FastAPI + React SOC) "
        "and Full God's Eye View (Photorealistic 3D Cesium Globe + Spatial Intelligence).\n"
        "SAFETY BOUNDARY: Perform only defensive security operations, authorized read-only posture "
        "inspections (DNS/TLS/HTTP headers), alert triage, incident containment, and geospatial telemetry. "
        "Never execute or generate offensive exploitation commands.\n\n"
        f"LIVE TELEMETRY:\n"
        f"- Mask State: {status_snapshot.get('mask_state', 'IDLE')}\n"
        f"- Full Vigil AI SOC: {'LIVE' if vigil_st.get('live') else vigil_st.get('mode', 'offline')} "
        f"(open cases: {status_snapshot.get('open_alerts', 0)}, findings: {status_snapshot.get('findings_count', 0)}, "
        f"playbooks: {wf_names})\n"
        f"- Full God's Eye View: {'LIVE (3D Cesium)' if gev_st.get('live') else gev_st.get('mode', 'offline')} "
        f"(focus: {json.dumps(status_snapshot.get('globe_focus') or {})}, pins: {status_snapshot.get('pins_count', 0)})\n"
        f"- Recent Cases: {json.dumps(cases[:5])}\n\n"
        "TOOLS: When an action is needed, emit one XML tool block on its own line:\n"
        "<tool_call>{\"tool\": \"<name>\", \"args\": {...}}</tool_call>\n"
        "Available tools:\n"
        "  - vigil_triage: {\"title\": str, \"target\": str, \"severity\": \"critical|high|medium|low|info\", \"lat\": float?, \"lon\": float?}\n"
        "  - vigil_update_case: {\"case_id\": str, \"status\": \"open|in_progress|contained|closed\", \"notes\": str?}\n"
        "  - vigil_list_workflows: {}\n"
        "  - godseye_fly_to: {\"lat\": float, \"lon\": float, \"label\": str, \"alt\": float?}\n"
        "  - defensive_posture_check: {\"host\": str}\n"
        "  - set_mask_state: {\"state\": \"IDLE|RECON|ALERT|CONTAINED\"}\n"
        "Keep responses sharp, tactical, grounded in real tool output, and concise."
    )


def run_agent_turn(
    *,
    user_text: str,
    history: list[dict[str, str]],
    status_snapshot: dict[str, Any],
    tool_executor: Callable[[str, dict[str, Any]], dict[str, Any]],
    model: str = "",
) -> dict[str, Any]:
    """Run a real Hermes multi-turn + tool-calling turn against Assimilis/standalone LLMs."""
    system_prompt = build_system_prompt(status_snapshot)
    convo: list[dict[str, str]] = []
    for m in history[-12:]:
        role = m.get("role")
        content = str(m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            convo.append({"role": role, "content": content})
    if not convo or convo[-1]["role"] != "user" or convo[-1]["content"] != user_text:
        convo.append({"role": "user", "content": user_text})

    executed_tools: list[dict[str, Any]] = []
    used_provider = ""

    for _hop in range(3):
        ok, raw_reply, prov = complete(convo, system_prompt=system_prompt, model=model)
        if not ok:
            return {
                "ok": False,
                "error": raw_reply,
                "reply": "",
                "provider": "",
                "tools": executed_tools,
            }
        used_provider = prov
        match = _TOOL_CALL_RE.search(raw_reply)
        if not match:
            return {
                "ok": True,
                "reply": raw_reply.strip(),
                "provider": used_provider,
                "tools": executed_tools,
            }
        try:
            call_obj = json.loads(match.group(1))
            tname = str(call_obj.get("tool") or "").strip()
            targs = call_obj.get("args") if isinstance(call_obj.get("args"), dict) else {}
        except Exception:
            return {
                "ok": True,
                "reply": _TOOL_CALL_RE.sub("", raw_reply).strip() or raw_reply.strip(),
                "provider": used_provider,
                "tools": executed_tools,
            }
        tool_res = tool_executor(tname, targs)
        executed_tools.append({"tool": tname, "args": targs, "result": tool_res})
        convo.append({"role": "assistant", "content": raw_reply})
        convo.append({
            "role": "user",
            "content": f"[TOOL RESULT {tname}]: {json.dumps(tool_res)[:2000]}\nNow give a concise tactical answer to the operator.",
        })

    return {
        "ok": True,
        "reply": "Executed requested Chappa V2 operations via Hermes Engine.",
        "provider": used_provider,
        "tools": executed_tools,
    }


def engine_status() -> dict[str, Any]:
    assimilis_url = os.environ.get("ASSIMILIS_URL", "").strip().rstrip("/")
    env_map = _load_hermes_env()
    has_keys = any(_get_env(k, env_map) for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"))
    return {
        "connected": bool(assimilis_url or has_keys),
        "mode": "assimilis-hermes-engine" if assimilis_url else ("standalone-hermes-env" if has_keys else "awaiting-provider-key"),
        "assimilis_url": assimilis_url,
        "standalone_keys": has_keys,
    }
