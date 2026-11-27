/* Chappa V2 — Modified Hermes Core Controller (WebGL2 Mask + Vigil + God's Eye + SSE + Assimilis Bridge) */
(function () {
  'use strict';

  const maskCanvas = document.getElementById('maskStageCanvas');
  const hudCanvas = document.getElementById('maskHudCanvas');
  const stage = ChappaMask.createMaskStage(maskCanvas, { hudCanvas, fps: 60, zoom: 1.05 });

  let globe = null;
  let lastStatus = null;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Try loading optional custom 3D .OBJ mask from ~/.chappa/modules/custom_mask.obj
  fetch('api/chappa/custom-mask.obj')
    .then((r) => (r.ok ? r.text() : ''))
    .then((txt) => { if (txt && txt.includes('v ')) stage.loadObjMesh(txt); })
    .catch(() => {});

  window.openDrawer = function (paneName) {
    const dr = document.getElementById('workspaceDrawer');
    if (dr) dr.classList.add('open');
    document.querySelectorAll('.ch-pane').forEach((p) => p.classList.remove('active'));
    const p = document.getElementById('pane-' + paneName);
    if (p) p.classList.add('active');
    document.querySelectorAll('.ch-dtab').forEach((b) => b.classList.toggle('on', b.dataset.dtab === paneName));
    if (paneName === 'globe' && !globe) {
      const gc = document.getElementById('globeCanvas');
      if (gc && window.ChappaGlobe) {
        globe = ChappaGlobe.createGlobe(gc);
        if (lastStatus) {
          globe.setPins(lastStatus.pins || []);
          if (lastStatus.globe_focus) globe.flyTo(lastStatus.globe_focus.lat, lastStatus.globe_focus.lon, lastStatus.globe_focus.label);
        }
      }
    }
  };

  window.closeDrawer = function () {
    const dr = document.getElementById('workspaceDrawer');
    if (dr) dr.classList.remove('open');
  };

  window.hideReply = function () {
    const t = document.getElementById('replyToast');
    if (t) t.classList.remove('show');
  };

  function showReply(txt) {
    const t = document.getElementById('replyToast');
    const b = document.getElementById('replyBody');
    if (t && b && txt) {
      b.textContent = txt;
      t.classList.add('show');
    }
  }

  window.setMaskState = async function (next) {
    stage.setState(next);
    const r = await fetch('api/chappa/state', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mask_state: next })
    });
    if (r.ok) applyStatus(await r.json());
  };

  window.toggleFps = async function () {
    const btn = document.getElementById('fpsBtn');
    const next = btn && btn.dataset.fps === '12' ? 60 : 12;
    stage.setFps(next);
    const r = await fetch('api/chappa/state', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fps_cadence: next })
    });
    if (r.ok) applyStatus(await r.json());
  };

  window.onModelChange = async function (model) {
    await fetch('api/chappa/state', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active_model: model })
    });
  };

  window.sendChat = async function (e) {
    if (e) e.preventDefault();
    const inp = document.getElementById('chatInput');
    const sel = document.getElementById('modelSelect');
    const message = inp ? inp.value.trim() : '';
    if (!message) return;
    if (inp) inp.value = '';
    showReply('Hermes Core thinking…');
    const r = await fetch('api/chappa/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, model: sel ? sel.value : 'hermes-auto' })
    });
    if (!r.ok) return;
    const data = await r.json();
    if (data.reply) showReply(data.reply);
    if (data.status) applyStatus(data.status);
  };

  window.submitVigilTriage = async function (e) {
    if (e) e.preventDefault();
    const title = document.getElementById('vigilTitle').value.trim();
    const target = document.getElementById('vigilTarget').value.trim();
    const severity = document.getElementById('vigilSev').value;
    if (!title && !target) return;
    const r = await fetch('api/chappa/vigil/triage', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: title || `Alert on ${target}`, target, severity, lat: 40.7128, lon: -74.006 })
    });
    if (r.ok) {
      document.getElementById('vigilTitle').value = '';
      document.getElementById('vigilTarget').value = '';
      const d = await r.json();
      if (d.case) showReply(`Vigil Triaged Case #${d.case.id}: ${d.case.verdict}`);
      refreshStatus();
    }
  };

  window.setCaseStatus = async function (id, status) {
    const r = await fetch(`api/chappa/vigil/cases/${id}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (r.ok) {
      const d = await r.json();
      if (d.status) applyStatus(d.status);
    }
  };

  window.flyGlobe = async function (lat, lon, label) {
    if (globe) globe.flyTo(lat, lon, label);
    await fetch('api/chappa/globe/focus', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon, label })
    });
  };

  window.runDefensiveCheck = async function (e) {
    if (e) e.preventDefault();
    const inp = document.getElementById('auditHostInput');
    const pre = document.getElementById('auditResult');
    const host = inp ? inp.value.trim() : '';
    if (!host) return;
    if (pre) pre.textContent = `Running read-only DNS / TLS / Security Header audit on ${host}…`;
    const r = await fetch('api/chappa/telemetry/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ host })
    });
    if (!r.ok) return;
    const d = await r.json();
    if (pre) pre.textContent = JSON.stringify(d.report || d, null, 2);
    if (d.status) applyStatus(d.status);
  };

  window.installHotMod = async function (e) {
    if (e) e.preventDefault();
    const inp = document.getElementById('modNameInput');
    const name = inp ? inp.value.trim() : '';
    if (!name) return;
    const r = await fetch('api/chappa/modules/install', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: name, name, kind: 'playbook', version: '1.0.0', description: 'Hot-loaded without binary rebuild' })
    });
    if (r.ok) {
      inp.value = '';
      refreshStatus();
    }
  };

  function applyStatus(d) {
    if (!d) return;
    lastStatus = d;
    const st = d.mask_state || 'IDLE';
    stage.setState(st);
    stage.setFps(d.fps_cadence || 60);

    const isAlert = st === 'ALERT' || (d.open_alerts || 0) > 0;
    const dot = document.getElementById('brandDot');
    if (dot) dot.classList.toggle('alert', isAlert);
    const pill = document.getElementById('statusPill');
    if (pill) {
      pill.textContent = `${st} · ${d.open_alerts || 0} OPEN`;
      pill.classList.toggle('alert', isAlert);
    }
    const fpsBtn = document.getElementById('fpsBtn');
    if (fpsBtn) {
      const f = Number(d.fps_cadence || 60);
      fpsBtn.dataset.fps = String(f);
      fpsBtn.textContent = f <= 12 ? '12fps (On Twos)' : '60fps';
    }
    document.querySelectorAll('.ch-sdot').forEach((b) => b.classList.toggle('active', b.dataset.st === st));

    const kC = document.getElementById('kpiCases'); if (kC) kC.textContent = `${d.open_alerts || 0} open / ${d.cases_count || 0} total`;
    const kP = document.getElementById('kpiPins'); if (kP) kP.textContent = String(d.pins_count || 0);
    const kL = document.getElementById('kpiLink'); if (kL) kL.textContent = (d.bridges && d.bridges.assimilis && d.bridges.assimilis.connected) ? 'CONNECTED' : 'STANDALONE';

    const nv = document.getElementById('nodeVigilSub'); if (nv) nv.textContent = `${d.open_alerts || 0} open cases`;
    const ng = document.getElementById('nodeGlobeSub'); if (ng) ng.textContent = `${d.pins_count || 0} live pins`;
    const nm = document.getElementById('nodeModSub'); if (nm) nm.textContent = `${(d.hot_modules || []).length} hot modules`;

    // Vigil cases list
    const vc = document.getElementById('vigilCasesList');
    if (vc) {
      const cases = d.cases || [];
      vc.innerHTML = cases.length
        ? cases.map((c) => `
          <div class="ch-item ${esc(c.severity)}">
            <div class="ch-item-head">
              <b>#${c.id} [${esc(c.severity).toUpperCase()}] ${esc(c.title)}</b>
              <span>${esc(c.status).toUpperCase()}</span>
            </div>
            <div class="ch-muted"><b>MITRE:</b> ${esc(c.mitre)} · <b>IOC:</b> ${esc(c.target || 'n/a')}</div>
            <div class="ch-muted">${esc(c.verdict)}</div>
            <div class="ch-row" style="margin-top:3px">
              ${c.lat != null ? `<button type="button" class="ch-btn" onclick="openDrawer('globe');flyGlobe(${c.lat},${c.lon},'${esc(c.title).replace(/'/g, '')}')">Plot on Globe</button>` : ''}
              ${c.status !== 'contained' ? `<button type="button" class="ch-btn on" onclick="setCaseStatus(${c.id},'contained')">Contain</button>` : ''}
              ${c.status !== 'closed' ? `<button type="button" class="ch-btn" onclick="setCaseStatus(${c.id},'closed')">Close</button>` : ''}
            </div>
          </div>`).join('')
        : '<div class="ch-muted">No open Vigil SOC cases. Triage an alert above or via Hermes chat.</div>';
    }

    // Globe pins list + live 3D globe sync
    if (globe) {
      globe.setPins(d.pins || []);
      if (d.globe_focus) globe.flyTo(d.globe_focus.lat, d.globe_focus.lon, d.globe_focus.label);
    }
    const extG = document.getElementById('extGodseyeLink');
    if (extG && d.bridges && d.bridges.godseye) {
      extG.style.display = d.bridges.godseye.external_live ? 'inline-block' : 'none';
      extG.href = d.bridges.godseye.url;
    }
    const gp = document.getElementById('globePinsList');
    if (gp) {
      gp.innerHTML = (d.pins || []).map((p) => `
        <div class="ch-item ${esc(p.severity)}" style="cursor:pointer" onclick="flyGlobe(${p.lat},${p.lon},'${esc(p.label).replace(/'/g, '')}')">
          <div class="ch-item-head"><b>${esc(p.label)}</b><span>${Number(p.lat).toFixed(2)}, ${Number(p.lon).toFixed(2)}</span></div>
          <div class="ch-muted">${esc(p.ip || '')} · ${esc(p.asn || '')} — ${esc(p.notes || '')}</div>
        </div>`).join('');
    }

    // Bridge & Hot Modules pane
    const br = document.getElementById('bridgeStatusBox');
    if (br && d.bridges) {
      br.innerHTML = `
        <div class="ch-item"><b>Assimilis Manager:</b> ${d.bridges.assimilis.connected ? 'Connected (' + esc(d.bridges.assimilis.url) + ')' : 'Standalone Mode'}</div>
        <div class="ch-item"><b>Vigil AI SOC:</b> ${esc(d.bridges.vigil.mode)}</div>
        <div class="ch-item"><b>God's Eye View:</b> ${d.bridges.godseye.external_live ? 'Full Server Live' : 'Built-In 3D Globe Active'}</div>`;
    }
    const ml = document.getElementById('modulesList');
    if (ml) {
      const mods = d.hot_modules || [];
      ml.innerHTML = mods.length
        ? mods.map((m) => `<div class="ch-item"><b>${esc(m.name)}</b> v${esc(m.version)} (${esc(m.kind)})</div>`).join('')
        : '<div class="ch-muted">No hot modules installed yet.</div>';
    }

    // Chat log pane
    const cl = document.getElementById('chatLogList');
    if (cl) {
      const msgs = d.chat_history || [];
      cl.innerHTML = msgs.length
        ? msgs.map((m) => `<div class="ch-msg ${esc(m.role)}"><b>${m.role === 'user' ? 'YOU' : 'CHAPPA V2'}:</b>\n${esc(m.content)}</div>`).join('')
        : '<div class="ch-muted">Use the Hermes chat bar at the bottom to command Chappa V2.</div>';
    }
  }

  async function loadModels() {
    try {
      const r = await fetch('api/chappa/models', { cache: 'no-store' });
      if (!r.ok) return;
      const d = await r.json();
      const sel = document.getElementById('modelSelect');
      if (!sel || !Array.isArray(d.models) || !d.models.length) return;
      sel.innerHTML = d.models.map((m) => {
        const val = m.id || m.model || m.name || 'hermes-auto';
        const lbl = m.label || m.display_name || m.name || val;
        return `<option value="${esc(val)}">${esc(lbl)}</option>`;
      }).join('');
      if (lastStatus && lastStatus.active_model && Array.from(sel.options).some((o) => o.value === lastStatus.active_model)) {
        sel.value = lastStatus.active_model;
      } else if (sel.options.length) {
        sel.selectedIndex = 0;
      }
    } catch (_) {}
  }

  async function refreshStatus() {
    try {
      const r = await fetch('api/chappa/status', { cache: 'no-store' });
      if (r.ok) applyStatus(await r.json());
    } catch (_) {}
  }

  // Live SSE stream (zero polling lag!)
  if (typeof EventSource !== 'undefined') {
    const es = new EventSource('api/chappa/events');
    es.addEventListener('status', (ev) => { try { applyStatus(JSON.parse(ev.data)); } catch (_) {} });
    es.addEventListener('vigil_case', () => refreshStatus());
    es.addEventListener('globe_focus', (ev) => {
      try { const f = JSON.parse(ev.data); if (globe) globe.flyTo(f.lat, f.lon, f.label); } catch (_) {}
    });
    es.addEventListener('chat_reply', () => refreshStatus());
  }

  refreshStatus();
  loadModels();
})();
