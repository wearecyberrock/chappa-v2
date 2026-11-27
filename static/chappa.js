/* Chappa V2 — Command Center Controller */
(function () {
  'use strict';
  const maskCanvas = document.getElementById('maskStageCanvas');
  const stage = ChappaMask.createMaskStage(maskCanvas, { transparent: true, fps: 12, zoom: 1.0 });

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  window.switchView = function (name, btn) {
    document.querySelectorAll('.ch-view').forEach((v) => v.classList.remove('active'));
    const tgt = document.getElementById('view-' + name);
    if (tgt) tgt.classList.add('active');
    document.querySelectorAll('[data-view-btn]').forEach((b) => b.classList.remove('on'));
    if (btn) btn.classList.add('on');
  };

  window.setMaskState = async function (next) {
    stage.setState(next);
    const r = await fetch('api/chappa/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mask_state: next })
    });
    if (r.ok) applyStatus(await r.json());
  };

  window.toggleFps = async function () {
    const btn = document.getElementById('fpsBtn');
    const next = btn && btn.dataset.fps === '12' ? 60 : 12;
    stage.setFps(next);
    const r = await fetch('api/chappa/state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fps_cadence: next })
    });
    if (r.ok) applyStatus(await r.json());
  };

  window.installDemoModule = async function () {
    const nameEl = document.getElementById('modNameInput');
    const name = (nameEl && nameEl.value.trim()) || 'custom-scanner';
    const r = await fetch('api/chappa/modules/install', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: name.toLowerCase().replace(/[^a-z0-9_-]+/g, '-'),
        name,
        kind: 'tool',
        version: '1.0.0',
        description: 'Hot-loaded module (no .exe rebuild needed)'
      })
    });
    if (r.ok) {
      if (nameEl) nameEl.value = '';
      refreshStatus();
    }
  };

  window.sendCommand = async function (e) {
    if (e) e.preventDefault();
    const inp = document.getElementById('cmdInput');
    const tgtInp = document.getElementById('targetInput');
    const task = inp ? inp.value.trim() : '';
    const target = tgtInp ? tgtInp.value.trim() : '';
    if (!task) return;
    if (inp) inp.value = '';
    const r = await fetch('api/chappa/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task, target, source: 'chappa-ui' })
    });
    if (!r.ok) return;
    const data = await r.json();
    if (data.status) applyStatus(data.status);
    const box = document.getElementById('replyBox');
    if (box && data.reply) {
      box.textContent = data.reply;
      box.classList.add('show');
    }
  };

  function applyStatus(d) {
    if (!d) return;
    const st = d.mask_state || 'IDLE';
    stage.setState(st);
    stage.setFps(d.fps_cadence || 12);
    const pill = document.getElementById('statusPill');
    if (pill) {
      pill.textContent = `${st} · ${d.open_alerts || 0} ALERTS`;
      pill.classList.toggle('alert', st === 'ALERT' || (d.open_alerts || 0) > 0);
    }
    const fpsBtn = document.getElementById('fpsBtn');
    if (fpsBtn) {
      const f = Number(d.fps_cadence || 12);
      fpsBtn.dataset.fps = String(f);
      fpsBtn.textContent = f <= 12 ? '12fps (On Twos)' : '60fps';
    }
    const hud = document.getElementById('stageHud');
    if (hud) {
      hud.innerHTML = `<b>CHAPPA V2</b> · STATE: ${esc(st)}<br>TARGET: ${esc(d.active_target || 'NONE')} · MODEL: ${esc(d.active_model || 'hermes-auto')}`;
    }
    const fList = document.getElementById('findingsList');
    if (fList) {
      const items = d.recent_findings || [];
      fList.innerHTML = items.length
        ? items.slice(0, 6).map((f) => `<div class="ch-item"><b>[${esc(f.severity)}]</b> ${esc(f.target)} — ${esc(f.summary)}</div>`).join('')
        : '<div class="ch-muted">No findings yet. Run a command below.</div>';
    }
    const mList = document.getElementById('modulesList');
    if (mList) {
      const mods = d.hot_modules || [];
      mList.innerHTML = mods.length
        ? mods.map((m) => `<div class="ch-item"><b>${esc(m.name)}</b> v${esc(m.version)} (${esc(m.kind)})</div>`).join('')
        : '<div class="ch-muted">~/.chappa/modules/ ready for hot-upgradable tools &amp; playbooks.</div>';
    }
  }

  async function refreshStatus() {
    try {
      const r = await fetch('api/chappa/status', { cache: 'no-store' });
      if (r.ok) applyStatus(await r.json());
    } catch (_) {}
  }

  refreshStatus();
  setInterval(refreshStatus, 5000);
})();
