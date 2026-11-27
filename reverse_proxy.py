"""Full-method reverse proxy for Chappa V2's full upstream apps (/vigil/* and /godseye/*).

Supports both standalone mode (http://127.0.0.1:7480/vigil/, /godseye/) AND
proxied Assimilis mode (http://127.0.0.1:8787/chappa-v2/vigil/, /chappa-v2/godseye/)
simultaneously via X-Forwarded-Prefix — with ZERO modifications to the upstream
git submodules apps/vigil and apps/gods-eye-view.
"""
from __future__ import annotations

import http.client
import json
import re
from typing import Any
from urllib.parse import urlparse

from runtime_manager import GODSEYE_HOST, GODSEYE_PORT, MANAGER, VIGIL_HOST, VIGIL_PORT

MAX_BODY = 16 * 1024 * 1024
MAX_RESPONSE = 32 * 1024 * 1024
TIMEOUT = 45

_HOP_HEADERS = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailer", "trailers", "transfer-encoding", "upgrade",
})
_DROP_IN = _HOP_HEADERS | {"host", "accept-encoding", "content-length", "x-forwarded-prefix", "x-hermes-csrf-token"}
_DROP_OUT = _HOP_HEADERS | {
    "content-length", "content-encoding", "x-frame-options",
    "content-security-policy", "content-security-policy-report-only",
}

_GEV_HTML_ATTR_RE = re.compile(
    r'(\b(?:href|src|action|data-logo-src)\s*=\s*["\'])(/(?!/))',
    re.IGNORECASE,
)


def _public_prefix(handler: Any) -> str:
    fwd = str(handler.headers.get("X-Forwarded-Prefix") or "").strip().rstrip("/")
    if fwd and not fwd.startswith("/"):
        fwd = "/" + fwd
    return fwd


def _build_godseye_base_shim(public_base: str) -> bytes:
    base_json = json.dumps(public_base.rstrip("/"))
    js = f"""/* Chappa V2 subpath bootstrapper for Full God's Eye View (zero upstream edits) */
(function () {{
  var BASE = {base_json};
  if (!BASE) return;
  window.CESIUM_BASE_URL = BASE + '/cesium/';

  var PREFIXES = [
    '/assets/', '/api/', '/cesium/', '/data/', '/icons/',
    '/logo.svg', '/mic.svg', '/manifest.webmanifest', '/mcp',
    '/textures/', '/models/', '/fonts/', '/workers/', '/shaders/'
  ];

  function shouldPrefix(pathname) {{
    if (!pathname || pathname.indexOf(BASE + '/') === 0 || pathname === BASE) return false;
    for (var i = 0; i < PREFIXES.length; i++) {{
      if (pathname.indexOf(PREFIXES[i]) === 0) return true;
    }}
    return false;
  }}

  function rewriteUrl(input) {{
    if (typeof input === 'string') {{
      if (input.indexOf('//') === 0) return input;
      if (input.charAt(0) === '/') {{
        return shouldPrefix(input) ? (BASE + input) : input;
      }}
      if (input.indexOf(window.location.origin + '/') === 0) {{
        var rel = input.slice(window.location.origin.length);
        return shouldPrefix(rel) ? (window.location.origin + BASE + rel) : input;
      }}
      return input;
    }}
    if (input instanceof URL) {{
      if (input.origin === window.location.origin && shouldPrefix(input.pathname)) {{
        return new URL(BASE + input.pathname + input.search + input.hash, input.origin);
      }}
    }}
    return input;
  }}

  var origFetch = window.fetch;
  if (typeof origFetch === 'function') {{
    window.fetch = function (input, init) {{
      try {{
        if (typeof input === 'string' || input instanceof URL) {{
          input = rewriteUrl(input);
        }} else if (input && typeof Request !== 'undefined' && input instanceof Request) {{
          var next = rewriteUrl(input.url);
          if (next !== input.url) {{
            input = new Request(next, input);
          }}
        }}
      }} catch (_) {{}}
      return origFetch.call(this, input, init);
    }};
  }}

  if (typeof navigator !== 'undefined' && typeof navigator.sendBeacon === 'function') {{
    var origBeacon = navigator.sendBeacon.bind(navigator);
    navigator.sendBeacon = function (url, data) {{
      try {{ url = rewriteUrl(url); }} catch (_) {{}}
      return origBeacon(url, data);
    }};
  }}

  var origOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function (method, url) {{
    var args = Array.prototype.slice.call(arguments);
    try {{ args[1] = rewriteUrl(url); }} catch (_) {{}}
    return origOpen.apply(this, args);
  }};

  if (typeof window.EventSource === 'function') {{
    var OrigES = window.EventSource;
    window.EventSource = function (url, cfg) {{
      return new OrigES(rewriteUrl(url), cfg);
    }};
    window.EventSource.prototype = OrigES.prototype;
  }}

  if (typeof window.Worker === 'function') {{
    var OrigWorker = window.Worker;
    window.Worker = function (url, opts) {{
      return new OrigWorker(rewriteUrl(url), opts);
    }};
    window.Worker.prototype = OrigWorker.prototype;
  }}

  var origSetAttr = Element.prototype.setAttribute;
  Element.prototype.setAttribute = function (name, value) {{
    if ((name === 'href' || name === 'src' || name === 'data-logo-src') && typeof value === 'string') {{
      value = rewriteUrl(value);
    }}
    return origSetAttr.call(this, name, value);
  }};

  function patchProp(proto, prop) {{
    if (!proto) return;
    var desc = Object.getOwnPropertyDescriptor(proto, prop);
    if (!desc || !desc.set) return;
    Object.defineProperty(proto, prop, {{
      configurable: true,
      enumerable: desc.enumerable,
      get: desc.get,
      set: function (v) {{
        return desc.set.call(this, typeof v === 'string' ? rewriteUrl(v) : v);
      }}
    }});
  }}
  patchProp(HTMLLinkElement.prototype, 'href');
  patchProp(HTMLScriptElement.prototype, 'src');
  patchProp(HTMLImageElement.prototype, 'src');

  // Allow Chappa V2 Command Core / Hermes Agent to fly Full God's Eye View smoothly
  window.addEventListener('message', function (ev) {{
    var d = ev && ev.data;
    if (!d || typeof d !== 'object') return;
    if (d.type === 'chappa:flyTo' && typeof d.lat === 'number' && typeof d.lon === 'number') {{
      var alt = typeof d.alt === 'number' ? d.alt : 850000;
      var hash = '#v=2&lat=' + d.lat.toFixed(5) + '&lon=' + d.lon.toFixed(5) + '&alt=' + Math.round(alt);
      if (window.location.hash !== hash) {{
        window.location.hash = hash;
        try {{ window.dispatchEvent(new HashChangeEvent('hashchange')); }} catch (_) {{}}
      }}
    }}
  }});
}})();
"""
    return js.encode("utf-8")


def _build_vigil_assimilis_shim() -> bytes:
    """Attach Assimilis CSRF header and land straight in Vigil's live SOC Console (Setup stays accessible in top bar)."""
    js = """/* Chappa V2 -> Full Vigil SOC embed bootstrapper */
(function () {
  try {
    if (!window.localStorage.getItem('vigil.setupDismissed')) {
      window.localStorage.setItem('vigil.setupDismissed', '1');
    }
    if (!window.localStorage.getItem('vigil.consoleTourSeen')) {
      window.localStorage.setItem('vigil.consoleTourSeen', '1');
    }
  } catch (_) {}

  function getAssimilisCsrf() {
    try {
      var topWin = window.top;
      if (topWin && topWin !== window && topWin.document) {
        var meta = topWin.document.querySelector('meta[name="hermes-csrf-token"], meta[name="csrf-token"]');
        if (meta && meta.content) return meta.content;
      }
    } catch (_) {}
    try {
      var p = window.parent;
      if (p && p !== window && p.__ASSIMILIS_CSRF__) return p.__ASSIMILIS_CSRF__;
    } catch (_) {}
    return '';
  }

  var origFetch = window.fetch;
  if (typeof origFetch === 'function') {
    window.fetch = function (input, init) {
      var method = ((init && init.method) || (input && input.method) || 'GET').toUpperCase();
      if (method !== 'GET' && method !== 'HEAD' && method !== 'OPTIONS') {
        var tok = getAssimilisCsrf();
        if (tok) {
          init = Object.assign({}, init || {});
          var hdrs = new Headers(init.headers || (input && input.headers) || {});
          if (!hdrs.has('X-Hermes-Csrf-Token')) hdrs.set('X-Hermes-Csrf-Token', tok);
          init.headers = hdrs;
        }
      }
      return origFetch.call(this, input, init);
    };
  }
})();
"""
    return js.encode("utf-8")


def _booting_html(app_name: str, subtitle: str, error: str = "") -> bytes:
    err_block = f'<p class="err">{error}</p>' if error else ""
    html_doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{app_name} — Starting…</title>
<meta http-equiv="refresh" content="2">
<style>
  html,body{{margin:0;height:100%;background:#060104;color:#ffeef1;font:13px/1.5 ui-monospace,monospace;display:grid;place-items:center}}
  .box{{max-width:480px;padding:24px 28px;border-radius:12px;border:1px solid rgba(255,30,56,.45);background:rgba(18,4,8,.92);box-shadow:0 0 40px rgba(255,30,56,.16);text-align:center}}
  .dot{{display:inline-block;width:10px;height:10px;border-radius:50%;background:#ff1e38;box-shadow:0 0 14px #ff1e38;margin-right:8px;animation:p 1s infinite alternate}}
  @keyframes p{{from{{opacity:.4;transform:scale(.85)}}to{{opacity:1;transform:scale(1.2)}}}}
  h2{{margin:0 0 8px;font-size:15px;letter-spacing:.1em}}
  p{{margin:6px 0;color:#c998a2}}
  .err{{color:#ff8696;font-size:12px;margin-top:12px}}
</style></head>
<body><div class="box"><h2><span class="dot"></span>{app_name}</h2>
<p>{subtitle}</p><p>Auto-connecting as soon as the service is ready…</p>{err_block}</div></body></html>"""
    return html_doc.encode("utf-8")


def _read_request_body(handler: Any, method: str) -> bytes | None:
    if method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    clen = int(handler.headers.get("Content-Length") or "0")
    if clen <= 0:
        return b"" if method in ("POST", "PUT", "PATCH") else None
    if clen > MAX_BODY:
        return None
    return handler.rfile.read(clen)


def proxy_vigil(handler: Any, method: str) -> None:
    parsed = urlparse(handler.path)
    fwd = _public_prefix(handler)
    public_base = f"{fwd}/vigil"

    if parsed.path == "/vigil":
        handler.send_response(302)
        handler.send_header("Location", f"{public_base}/")
        handler.end_headers()
        return

    rel = parsed.path[len("/vigil"):] or "/"
    if rel == "/__chappa_vigil_shim.js":
        data = _build_vigil_assimilis_shim()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/javascript; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if method != "HEAD":
            handler.wfile.write(data)
        return

    target_path = rel + (f"?{parsed.query}" if parsed.query else "")
    body_bytes = _read_request_body(handler, method)
    headers_in = {k: v for k, v in handler.headers.items() if k.lower() not in _DROP_IN}
    headers_in["Host"] = f"{VIGIL_HOST}:{VIGIL_PORT}"

    try:
        conn = http.client.HTTPConnection(VIGIL_HOST, VIGIL_PORT, timeout=TIMEOUT)
        conn.request(method, target_path, body=body_bytes, headers=headers_in)
        resp = conn.getresponse()
        data = resp.read(MAX_RESPONSE)
        resp_headers = resp.getheaders()
        status = resp.status
        conn.close()
    except Exception as exc:
        # Kick off Vigil startup if it wasn't running yet
        MANAGER.start_service("vigil")
        st = MANAGER.status().get("vigil", {})
        if rel.startswith("/api/") or rel.startswith("/mcp"):
            raw = json.dumps({"ok": False, "error": f"Full Vigil starting: {exc}", "vigil": st}).encode("utf-8")
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Content-Length", str(len(raw)))
            handler.end_headers()
            if method != "HEAD":
                handler.wfile.write(raw)
        else:
            raw = _booting_html(
                "FULL VIGIL AI SOC",
                "Booting FastAPI + PostgreSQL + React SOC Console (auth bypassed behind Assimilis)…",
                st.get("error", ""),
            )
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(raw)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            if method != "HEAD":
                handler.wfile.write(raw)
        return

    ctype = ""
    for k, v in resp_headers:
        if k.lower() == "content-type":
            ctype = v.lower()
            break

    if "text/html" in ctype and data:
        txt = data.decode("utf-8", errors="replace")
        txt = txt.replace('<base href="/">', f'<base href="{public_base}/">', 1)
        txt = txt.replace(
            '<meta name="vigil-base-path" content="">',
            f'<meta name="vigil-base-path" content="{public_base}">',
            1,
        )
        shim_tag = f'<script src="{public_base}/__chappa_vigil_shim.js"></script>'
        if shim_tag not in txt:
            if "<head>" in txt:
                txt = txt.replace("<head>", f"<head>\n    {shim_tag}", 1)
            elif "</head>" in txt:
                txt = txt.replace("</head>", f"  {shim_tag}\n</head>", 1)
        data = txt.encode("utf-8")

    handler.send_response(status)
    for k, v in resp_headers:
        kl = k.lower()
        if kl in _DROP_OUT:
            continue
        if kl == "location" and v.startswith("/") and not v.startswith(public_base):
            v = public_base + v
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    if method != "HEAD":
        handler.wfile.write(data)


def proxy_godseye(handler: Any, method: str) -> None:
    parsed = urlparse(handler.path)
    fwd = _public_prefix(handler)
    public_base = f"{fwd}/godseye"

    if parsed.path == "/godseye":
        qs = f"?{parsed.query}" if parsed.query else "?welcome=0"
        handler.send_response(302)
        handler.send_header("Location", f"{public_base}/{qs}")
        handler.end_headers()
        return

    rel = parsed.path[len("/godseye"):] or "/"
    if rel == "/__chappa_base.js":
        data = _build_godseye_base_shim(public_base)
        handler.send_response(200)
        handler.send_header("Content-Type", "application/javascript; charset=utf-8")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "no-store")
        handler.end_headers()
        if method != "HEAD":
            handler.wfile.write(data)
        return

    target_path = rel + (f"?{parsed.query}" if parsed.query else "")

    body_bytes = _read_request_body(handler, method)
    headers_in = {k: v for k, v in handler.headers.items() if k.lower() not in _DROP_IN}
    headers_in["Host"] = f"{GODSEYE_HOST}:{GODSEYE_PORT}"

    try:
        conn = http.client.HTTPConnection(GODSEYE_HOST, GODSEYE_PORT, timeout=TIMEOUT)
        conn.request(method, target_path, body=body_bytes, headers=headers_in)
        resp = conn.getresponse()
        data = resp.read(MAX_RESPONSE)
        resp_headers = resp.getheaders()
        status = resp.status
        conn.close()
    except Exception as exc:
        MANAGER.start_service("godseye")
        st = MANAGER.status().get("godseye", {})
        if rel.startswith("/api/") or rel.startswith("/mcp"):
            raw = json.dumps({"ok": False, "error": f"Full God's Eye View starting: {exc}", "godseye": st}).encode("utf-8")
            handler.send_response(503)
            handler.send_header("Content-Type", "application/json; charset=utf-8")
            handler.send_header("Content-Length", str(len(raw)))
            handler.end_headers()
            if method != "HEAD":
                handler.wfile.write(raw)
        else:
            raw = _booting_html(
                "FULL GOD'S EYE VIEW",
                "Booting Photorealistic 3D Cesium Globe + Live Spatial Providers + MCP…",
                st.get("error", ""),
            )
            handler.send_response(200)
            handler.send_header("Content-Type", "text/html; charset=utf-8")
            handler.send_header("Content-Length", str(len(raw)))
            handler.send_header("Cache-Control", "no-store")
            handler.end_headers()
            if method != "HEAD":
                handler.wfile.write(raw)
        return

    ctype = ""
    for k, v in resp_headers:
        if k.lower() == "content-type":
            ctype = v.lower()
            break

    if "text/html" in ctype and data:
        txt = data.decode("utf-8", errors="replace")
        # Rewrite root-relative HTML attributes to point through public_base
        txt = _GEV_HTML_ATTR_RE.sub(lambda m: f"{m.group(1)}{public_base}{m.group(2)}", txt)
        # Inject subpath bootstrapper BEFORE Cesium.js and the Vite bundle execute
        shim_tag = f'<script src="{public_base}/__chappa_base.js"></script>'
        if "<head>" in txt:
            txt = txt.replace("<head>", f"<head>\n  {shim_tag}", 1)
        elif "<HEAD>" in txt:
            txt = txt.replace("<HEAD>", f"<HEAD>\n  {shim_tag}", 1)
        data = txt.encode("utf-8")

    handler.send_response(status)
    for k, v in resp_headers:
        kl = k.lower()
        if kl in _DROP_OUT:
            continue
        if kl == "location" and v.startswith("/") and not v.startswith(public_base):
            v = public_base + v
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    if method != "HEAD":
        handler.wfile.write(data)
