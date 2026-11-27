/* Chappa V2 — Modified Hermes Core Controller (WebGL2 Binary Particle Mask + Full Vigil AI SOC + Full God's Eye View + Real Hermes Engine) */
(function () {
  'use strict';

  const matrixCanvas = document.getElementById('maskMatrixCanvas');
  const maskCanvas = document.getElementById('maskStageCanvas');
  const hudCanvas = document.getElementById('maskHudCanvas');
  const stage = ChappaMask.createMaskStage(maskCanvas, { matrixCanvas, hudCanvas, theme: 'red-matrix', fps: 60, zoom: 1.05 });

  let lastStatus = null;
  let activeView = 'core'; // 'core' | 'vigil' | 'godseye'
  let vigilLoaded = false;
  let godseyeLoaded = false;
  let voiceEnabled = true;
  let audioCtx = null;
  let activeAudio = null;
  let voiceRaf = 0;

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function stopSpeaking() {
    if (voiceRaf) { cancelAnimationFrame(voiceRaf); voiceRaf = 0; }
    if (activeAudio) {
      try { activeAudio.pause(); activeAudio.src = ''; } catch (_) {}
      activeAudio = null;
    }
    try { if (window.speechSynthesis) window.speechSynthesis.cancel(); } catch (_) {}
    stage.setSpeaking(false);
    stage.setSpeechLevel(0);
  }

  window.toggleVoice = function () {
    voiceEnabled = !voiceEnabled;
    const btn = document.getElementById('voiceBtn');
    if (btn) {
      btn.classList.toggle('on', voiceEnabled);
      btn.textContent = voiceEnabled ? 'Voice: Fish' : 'Voice: Muted';
    }
    if (!voiceEnabled) stopSpeaking();
  };

  async function speakReply(rawText) {
    if (!voiceEnabled) return;
    const text = String(rawText || '').replace(/[`*_#>\[\]]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600);
    if (!text) return;
    stopSpeaking();

    let voiceData = null;
    const endpoints = [
      { url: '/api/world/voice', body: { op: 'speak', text, engine: 'auto', persona: 'jarvis', prefer_fish: true } },
      { url: 'api/chappa/voice/speak', body: { text, engine: 'auto', persona: 'jarvis', prefer_fish: true } }
    ];
    for (const ep of endpoints) {
      try {
        const r = await fetch(ep.url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ep.body)
        });
        if (r.ok) {
          const d = await r.json();
          if (d && d.ok && d.audio_b64) { voiceData = d; break; }
        }
      } catch (_) {}
    }

    if (voiceData && voiceData.audio_b64) {
      try {
        const bin = atob(voiceData.audio_b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const blob = new Blob([bytes], { type: voiceData.mime || 'audio/mpeg' });
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        activeAudio = audio;

        const Ctx = window.AudioContext || window.webkitAudioContext;
        let analyser = null, samples = null;
        if (Ctx) {
          if (!audioCtx) audioCtx = new Ctx();
          if (audioCtx.state === 'suspended') await audioCtx.resume().catch(() => {});
          const src = audioCtx.createMediaElementSource(audio);
          analyser = audioCtx.createAnalyser();
          analyser.fftSize = 256;
          analyser.smoothingTimeConstant = 0.72;
          samples = new Uint8Array(analyser.fftSize);
          src.connect(analyser);
          analyser.connect(audioCtx.destination);
        }

        stage.setSpeaking(true);
        const pump = () => {
          if (!activeAudio || activeAudio.paused || activeAudio.ended) return;
          if (analyser && samples) {
            analyser.getByteTimeDomainData(samples);
            let sum = 0;
            for (let i = 0; i < samples.length; i++) {
              const v = (samples[i] - 128) / 128;
              sum += v * v;
            }
            const rms = Math.min(1.0, Math.sqrt(sum / samples.length) * 4.2);
            stage.setSpeechLevel(rms);
          }
          voiceRaf = requestAnimationFrame(pump);
        };

        audio.onplay = () => { voiceRaf = requestAnimationFrame(pump); };
        audio.onended = () => { URL.revokeObjectURL(url); stopSpeaking(); };
        audio.onerror = () => { URL.revokeObjectURL(url); stopSpeaking(); };
        await audio.play();
        return;
      } catch (_) {
        stopSpeaking();
      }
    }

    if (typeof window.speechSynthesis !== 'undefined' && typeof SpeechSynthesisUtterance !== 'undefined') {
      try {
        const u = new SpeechSynthesisUtterance(text);
        u.rate = 1.02;
        u.onstart = () => stage.setSpeaking(true);
        u.onend = () => stopSpeaking();
        u.onerror = () => stopSpeaking();
        window.speechSynthesis.speak(u);
      } catch (_) {}
    }
  }

  window.addEventListener('message', (ev) => {
    const d = ev && ev.data;
    if (!d || typeof d !== 'object') return;
    if (typeof d.chappaSpeechLevel === 'number') stage.setSpeechLevel(d.chappaSpeechLevel);
    if (typeof d.chappaSpeaking === 'boolean') stage.setSpeaking(d.chappaSpeaking);
  });
  window.chappaMaskStage = stage;
  window.chappaSpeak = speakReply;

  // Try loading optional custom 3D .OBJ mask from ~/.chappa/modules/custom_mask.obj
  fetch('api/chappa/custom-mask.obj')
    .then((r) => (r.ok ? r.text() : ''))
    .then((txt) => { if (txt && txt.includes('v ')) stage.loadObjMesh(txt); })
    .catch(() => {});

  // Full-Bleed Workspace Switcher: 3D Core <-> Full Vigil AI SOC <-> Full God's Eye View (Cesium)
  window.openAppView = function (view) {
    activeView = view || 'core';
    const ws = document.getElementById('appWorkspace');
    const vf = document.getElementById('vigilFrame');
    const gf = document.getElementById('godseyeFrame');
    const title = document.getElementById('appBarTitle');
    const badge = document.getElementById('appBarBadge');
    const popout = document.getElementById('appPopoutLink');
    const gevCtrl = document.getElementById('godseyeQuickControls');

    const navCore = document.getElementById('navCoreBtn');
    const navVigil = document.getElementById('navVigilBtn');
    const navGodseye = document.getElementById('navGodseyeBtn');
    if (navCore) navCore.classList.toggle('on', activeView === 'core');
    if (navVigil) navVigil.classList.toggle('on', activeView === 'vigil');
    if (navGodseye) navGodseye.classList.toggle('on', activeView === 'godseye');

    if (activeView === 'core') {
      if (ws) { ws.classList.remove('open'); ws.setAttribute('aria-hidden', 'true'); }
      if (vf) vf.classList.remove('active');
      if (gf) gf.classList.remove('active');
      if (stage.setPaused) stage.setPaused(false);
      const targetFps = (lastStatus && lastStatus.fps_cadence) ? Number(lastStatus.fps_cadence) : 60;
      stage.setFps(targetFps);
      return;
    }

    // Pause background mask WebGL rendering while full Cesium/Vigil workspace is active
    if (stage.setPaused) stage.setPaused(true);
    if (ws) { ws.classList.add('open'); ws.setAttribute('aria-hidden', 'false'); }

    if (activeView === 'vigil') {
      if (vf) {
        if (!vigilLoaded) {
          vf.src = 'vigil/cases';
          vigilLoaded = true;
        }
        vf.classList.add('active');
      }
      if (gf) gf.classList.remove('active');
      if (title) title.textContent = 'FULL VIGIL AI SOC CONSOLE';
      if (popout) popout.href = 'vigil/cases';
      if (gevCtrl) gevCtrl.style.display = 'none';
      const vLive = lastStatus && lastStatus.services && lastStatus.services.vigil && lastStatus.services.vigil.live;
      if (badge) {
        badge.textContent = vLive ? 'POSTGRES · LIVE' : 'BOOTING…';
        badge.classList.toggle('booting', !vLive);
      }
    } else if (activeView === 'godseye') {
      if (gf) {
        if (!godseyeLoaded) {
          gf.src = 'godseye/?welcome=0';
          godseyeLoaded = true;
        }
        gf.classList.add('active');
      }
      if (vf) vf.classList.remove('active');
      if (title) title.textContent = "FULL GOD'S EYE VIEW · 3D CESIUM GLOBE";
      if (popout) popout.href = 'godseye/?welcome=0';
      if (gevCtrl) gevCtrl.style.display = 'flex';
      const gLive = lastStatus && lastStatus.services && lastStatus.services.godseye && lastStatus.services.godseye.live;
      if (badge) {
        badge.textContent = gLive ? 'CESIUM 3D · LIVE' : 'BOOTING…';
        badge.classList.toggle('booting', !gLive);
      }
    }
  };

  window.reloadActiveApp = function () {
    const vf = document.getElementById('vigilFrame');
    const gf = document.getElementById('godseyeFrame');
    if (activeView === 'vigil' && vf) vf.src = 'vigil/cases?t=' + Date.now();
    if (activeView === 'godseye' && gf) gf.src = 'godseye/?welcome=0&t=' + Date.now();
  };

  function sendGodseyeFlyTo(lat, lon, alt) {
    const gf = document.getElementById('godseyeFrame');
    if (gf && gf.contentWindow) {
      try {
        gf.contentWindow.postMessage({ type: 'chappa:flyTo', lat: Number(lat), lon: Number(lon), alt: Number(alt || 850000) }, '*');
      } catch (_) {}
    }
  }

  window.openDrawer = function (paneName) {
    const dr = document.getElementById('workspaceDrawer');
    if (dr) dr.classList.add('open');
    document.querySelectorAll('.ch-pane').forEach((p) => p.classList.remove('active'));
    const p = document.getElementById('pane-' + paneName);
    if (p) p.classList.add('active');
    document.querySelectorAll('.ch-dtab').forEach((b) => b.classList.toggle('on', b.dataset.dtab === paneName));
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

  window.controlService = async function (service, action) {
    showReply(`${action.toUpperCase()} requested for ${service}…`);
    const r = await fetch('api/chappa/services/control', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service, action })
    });
    if (r.ok) refreshStatus();
  };

  window.sendChat = async function (e) {
    if (e) e.preventDefault();
    const inp = document.getElementById('chatInput');
    const sel = document.getElementById('modelSelect');
    const message = inp ? inp.value.trim() : '';
    if (!message) return;
    if (inp) inp.value = '';
    showReply('Hermes Engine reasoning…');
    const r = await fetch('api/chappa/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, model: sel ? sel.value : 'hermes-auto' })
    });
    if (!r.ok) return;
    const data = await r.json();
    if (data.reply) {
      showReply(data.reply);
      speakReply(data.reply);
    }
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
      if (d.case) showReply(`Logged to ${d.vigil_backend || 'Vigil'} · Case ${d.case.id}: ${d.case.title}`);
      refreshStatus();
    }
  };

  window.setCaseStatus = async function (id, status) {
    const r = await fetch(`api/chappa/vigil/cases/${encodeURIComponent(id)}/status`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status })
    });
    if (r.ok) {
      const d = await r.json();
      if (d.status) applyStatus(d.status);
    }
  };

  window.flyGlobe = async function (lat, lon, label, alt) {
    sendGodseyeFlyTo(lat, lon, alt || 850000);
    await fetch('api/chappa/globe/focus', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lat, lon, label, alt: alt || 850000 })
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
    if (activeView === 'core') stage.setFps(d.fps_cadence || 60);

    const svcs = d.services || {};
    const vSvc = svcs.vigil || {};
    const gSvc = svcs.godseye || {};
    const pgSvc = svcs.postgres || {};
    const rdSvc = svcs.redis || {};

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
      fpsBtn.textContent = f <= 12 ? '12fps' : '60fps';
    }
    document.querySelectorAll('.ch-sdot').forEach((b) => b.classList.toggle('active', b.dataset.st === st));

    const kV = document.getElementById('kpiVigil');
    if (kV) {
      kV.textContent = vSvc.live ? `LIVE · ${d.open_alerts || 0} cases · ${d.workflows_count || 0} playbooks` : (vSvc.booting ? 'BOOTING…' : 'OFFLINE');
      kV.classList.toggle('live', !!vSvc.live);
    }
    const kG = document.getElementById('kpiGodseye');
    if (kG) {
      kG.textContent = gSvc.live ? `LIVE · 3D CESIUM (${d.pins_count || 0} pins)` : (gSvc.booting ? 'BOOTING…' : 'OFFLINE');
      kG.classList.toggle('live', !!gSvc.live);
    }
    const kL = document.getElementById('kpiLink');
    if (kL) {
      const linked = d.bridges && d.bridges.assimilis && d.bridges.assimilis.connected;
      kL.textContent = linked ? 'ASSIMILIS · CONNECTED' : 'STANDALONE HERMES';
      kL.classList.toggle('live', !!linked);
    }

    const nv = document.getElementById('nodeVigilSub');
    if (nv) nv.textContent = vSvc.live ? `LIVE · ${d.open_alerts || 0} open · ${d.findings_count || 0} findings` : (vSvc.booting ? 'Booting FastAPI + Postgres…' : 'Offline — click to start');
    const ng = document.getElementById('nodeGlobeSub');
    if (ng) ng.textContent = gSvc.live ? `LIVE · 3D Cesium · ${d.pins_count || 0} pins` : (gSvc.booting ? 'Booting Cesium Globe…' : 'Offline — click to start');
    const nm = document.getElementById('nodeModSub');
    if (nm) nm.textContent = `${vSvc.live ? 'Vigil✓' : 'Vigil…'} · ${gSvc.live ? 'Globe✓' : 'Globe…'} · ${(d.hot_modules || []).length} mods`;

    // Update active app bar badge
    const badge = document.getElementById('appBarBadge');
    if (badge && activeView === 'vigil') {
      badge.textContent = vSvc.live ? `POSTGRES · LIVE (${d.cases_count || 0} cases)` : 'BOOTING…';
      badge.classList.toggle('booting', !vSvc.live);
    } else if (badge && activeView === 'godseye') {
      badge.textContent = gSvc.live ? 'CESIUM 3D · LIVE' : 'BOOTING…';
      badge.classList.toggle('booting', !gSvc.live);
    }

    // Vigil cases list in quick triage drawer
    const vc = document.getElementById('vigilCasesList');
    if (vc) {
      const cases = d.cases || [];
      vc.innerHTML = cases.length
        ? cases.map((c) => {
            const cid = esc(c.case_id || c.id);
            const rawCid = String(c.case_id || c.id).replace(/'/g, '');
            return `
              <div class="ch-item ${esc(c.severity)}">
                <div class="ch-item-head">
                  <b>${cid} [${esc(c.severity).toUpperCase()}] ${esc(c.title)}</b>
                  <span>${esc(c.status).toUpperCase()}</span>
                </div>
                <div class="ch-muted"><b>MITRE:</b> ${esc(c.mitre)} · <b>SRC:</b> ${esc(c.source || 'vigil')}</div>
                <div class="ch-muted">${esc((c.verdict || '').slice(0, 180))}</div>
                <div class="ch-row" style="margin-top:3px">
                  ${c.status !== 'contained' ? `<button type="button" class="ch-btn on" onclick="setCaseStatus('${rawCid}','contained')">Contain</button>` : ''}
                  ${c.status !== 'closed' ? `<button type="button" class="ch-btn" onclick="setCaseStatus('${rawCid}','closed')">Close</button>` : ''}
                </div>
              </div>`;
          }).join('')
        : '<div class="ch-muted">No open Vigil SOC cases yet. Create one above, run a Posture Check, or open Full Vigil Console.</div>';
    }

    // Vigil workflows list
    const wfEl = document.getElementById('vigilWorkflowsList');
    if (wfEl) {
      const wfs = d.workflows || [];
      wfEl.innerHTML = wfs.length
        ? wfs.map((w) => `<div class="ch-item"><b>${esc(w.name || w.id)}</b><div class="ch-muted">${esc(w.description || 'Vigil WORKFLOW.md playbook')}</div></div>`).join('')
        : '<div class="ch-muted">Waiting for Full Vigil playbooks…</div>';
    }

    // Geolocated pins list -> click flies Full God's Eye View
    const gp = document.getElementById('globePinsList');
    if (gp) {
      gp.innerHTML = (d.pins || []).map((p) => `
        <div class="ch-item ${esc(p.severity)}" style="cursor:pointer" onclick="closeDrawer();openAppView('godseye');flyGlobe(${p.lat},${p.lon},'${esc(p.label).replace(/'/g, '')}',750000)">
          <div class="ch-item-head"><b>${esc(p.label)}</b><span>${Number(p.lat).toFixed(2)}, ${Number(p.lon).toFixed(2)}</span></div>
          <div class="ch-muted">${esc(p.ip || '')} · ${esc(p.asn || '')} — ${esc(p.notes || '')}</div>
        </div>`).join('');
    }

    // Runtime & Bridge panel
    const br = document.getElementById('bridgeStatusBox');
    if (br) {
      br.innerHTML = `
        <div class="ch-item">
          <div class="ch-item-head"><b>Full Vigil AI SOC (FastAPI + React)</b><span>${vSvc.live ? 'LIVE' : (vSvc.booting ? 'BOOTING' : 'OFFLINE')}</span></div>
          <div class="ch-muted">${esc(vSvc.error || vSvc.url || '127.0.0.1:16987')} · ${d.cases_count || 0} cases · ${d.findings_count || 0} findings · ${d.workflows_count || 0} playbooks</div>
          <div class="ch-row">
            <button type="button" class="ch-btn on" onclick="closeDrawer();openAppView('vigil')">Open UI</button>
            <button type="button" class="ch-btn" onclick="controlService('vigil','restart')">Restart</button>
            <button type="button" class="ch-btn danger" onclick="controlService('vigil','stop')">Stop</button>
          </div>
        </div>
        <div class="ch-item">
          <div class="ch-item-head"><b>Full God's Eye View (3D Cesium + MCP)</b><span>${gSvc.live ? 'LIVE' : (gSvc.booting ? 'BOOTING' : 'OFFLINE')}</span></div>
          <div class="ch-muted">${esc(gSvc.error || gSvc.url || '127.0.0.1:14173')}</div>
          <div class="ch-row">
            <button type="button" class="ch-btn on" onclick="closeDrawer();openAppView('godseye')">Open 3D Globe</button>
            <button type="button" class="ch-btn" onclick="controlService('godseye','restart')">Restart</button>
            <button type="button" class="ch-btn danger" onclick="controlService('godseye','stop')">Stop</button>
          </div>
        </div>
        <div class="ch-item">
          <div class="ch-item-head"><b>Local Stores (Zero-Root)</b><span>PG:${pgSvc.live ? 'ON' : 'OFF'} · REDIS:${rdSvc.live ? 'ON' : 'OFF'}</span></div>
          <div class="ch-muted">PostgreSQL ${esc(pgSvc.host || '127.0.0.1')}:${esc(pgSvc.port || 15432)} · Redis ${esc(rdSvc.host || '127.0.0.1')}:${esc(rdSvc.port || 16379)}</div>
        </div>
        <div class="ch-item">
          <div class="ch-item-head"><b>Hermes Engine &amp; Assimilis Bridge</b><span>${(d.bridges && d.bridges.assimilis && d.bridges.assimilis.connected) ? 'CONNECTED' : 'STANDALONE'}</span></div>
          <div class="ch-muted">${esc((d.bridges && d.bridges.hermes && d.bridges.hermes.mode) || 'hermes-engine')} ${d.bridges && d.bridges.assimilis && d.bridges.assimilis.url ? '· ' + esc(d.bridges.assimilis.url) : ''}</div>
        </div>`;
    }

    const ml = document.getElementById('modulesList');
    if (ml) {
      const mods = d.hot_modules || [];
      ml.innerHTML = mods.length
        ? mods.map((m) => `<div class="ch-item"><b>${esc(m.name)}</b> v${esc(m.version)} (${esc(m.kind)})</div>`).join('')
        : '<div class="ch-muted">No hot modules installed yet.</div>';
    }

    const cl = document.getElementById('chatLogList');
    if (cl) {
      const msgs = d.chat_history || [];
      cl.innerHTML = msgs.length
        ? msgs.map((m) => `<div class="ch-msg ${esc(m.role)}"><b>${m.role === 'user' ? 'YOU' : 'CHAPPA V2 · HERMES'}:</b>\n${esc(m.content)}</div>`).join('')
        : '<div class="ch-muted">Use the Hermes Engine command dock at the bottom to talk to Chappa V2.</div>';
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

  if (typeof EventSource !== 'undefined') {
    const es = new EventSource('api/chappa/events');
    es.addEventListener('status', (ev) => { try { applyStatus(JSON.parse(ev.data)); } catch (_) {} });
    es.addEventListener('vigil_case', () => refreshStatus());
    es.addEventListener('globe_focus', (ev) => {
      try {
        const f = JSON.parse(ev.data);
        if (f && typeof f.lat === 'number' && typeof f.lon === 'number') {
          sendGodseyeFlyTo(f.lat, f.lon, f.alt || 850000);
        }
      } catch (_) {}
    });
    es.addEventListener('chat_reply', () => refreshStatus());
  }

  refreshStatus();
  loadModels();
})();
