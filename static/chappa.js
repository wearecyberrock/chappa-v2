/* Chappa V2 — Modified Hermes Core Controller (WebGL2 Mask + Vigil + God's Eye + SSE + Assimilis Bridge) */
(function () {
  'use strict';

  const matrixCanvas = document.getElementById('maskMatrixCanvas');
  const maskCanvas = document.getElementById('maskStageCanvas');
  const hudCanvas = document.getElementById('maskHudCanvas');
  const stage = ChappaMask.createMaskStage(maskCanvas, { matrixCanvas, hudCanvas, theme: 'red-matrix', fps: 60, zoom: 1.05 });

  let globe = null;
  let lastStatus = null;
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
      btn.textContent = voiceEnabled ? 'Voice: Fish/Studio' : 'Voice: Muted';
    }
    if (!voiceEnabled) stopSpeaking();
  };

  async function speakReply(rawText) {
    if (!voiceEnabled) return;
    const text = String(rawText || '').replace(/[`*_#>\[\]]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 600);
    if (!text) return;
    stopSpeaking();

    // Try Assimilis Voice Studio / Fish Audio directly on same origin (/api/world/voice), then Chappa proxy
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

    // Graceful offline fallback: Web Speech API + syllabic eye glow modulation
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

  // Allow Assimilis parent shell to drive live Voice Studio / Fish speech level directly
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

  window.openDrawer = function (paneName) {
    const dr = document.getElementById('workspaceDrawer');
    if (dr) dr.classList.add('open');
    document.querySelectorAll('.ch-pane').forEach((p) => p.classList.remove('active'));
    const p = document.getElementById('pane-' + paneName);
    if (p) p.classList.add('active');
    document.querySelectorAll('.ch-dtab').forEach((b) => b.classList.toggle('on', b.dataset.dtab === paneName));
    try { history.replaceState(null, '', '#' + paneName); } catch (_) {}
    if (paneName === 'tools') loadToolCatalog();
    if (paneName === 'term') {
      ensureTerm();
      setTimeout(() => { try { if (termFit) termFit.fit(); } catch (_) {} }, 60);
    }
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

  // ── unified red/blue tool plane: catalog browser + gated runner ──────────
  const toolCache = new Map();

  // ── raw terminal: xterm.js front end over a ConPTY session ───────────────
  let term = null, termFit = null, termSession = null, termCursor = 0, termTimer = null;

  function ensureTerm() {
    if (term || !window.Terminal) return;
    const host = document.getElementById('termHost');
    if (!host) return;
    term = new window.Terminal({
      cursorBlink: true,
      fontSize: 12,
      fontFamily: 'ui-monospace, Menlo, Consolas, monospace',
      scrollback: 3000,
      theme: {
        background: '#0a0204',
        foreground: '#ffd7de',
        cursor: '#ff1e38',
        selectionBackground: '#3a0b13',
        black: '#1a0508', red: '#ff3b52', green: '#5ee08a',
        yellow: '#f0b429', blue: '#35b7ff', magenta: '#c56bff',
        cyan: '#4de2e2', white: '#f6e9ec'
      }
    });
    term.open(host);
    if (window.FitAddon) {
      termFit = new window.FitAddon.FitAddon();
      term.loadAddon(termFit);
      try { termFit.fit(); } catch (_) {}
    }
    // Forward real keystrokes, which is what makes an interactive TUI work.
    term.onData((data) => { if (termSession) sendTermRaw(data); });
  }

  window.startTerm = async function () {
    ensureTerm();
    const kindEl = document.getElementById('termProfile');
    const customEl = document.getElementById('termCustom');
    const status = document.getElementById('termStatus');
    const kind = kindEl ? kindEl.value : 'pwsh';
    const custom = customEl ? customEl.value.trim() : '';
    const cols = term && term.cols ? term.cols : 120;
    const rows = term && term.rows ? term.rows : 32;
    if (status) status.textContent = 'starting…';
    const r = await fetch('api/chappa/term/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ kind, command: custom, cols, rows })
    });
    const d = await r.json();
    if (!d.ok) {
      if (status) status.textContent = `start failed: ${d.error || ''}${d.hint ? ' — ' + d.hint : ''}`;
      return;
    }
    termSession = d.session;
    termCursor = 0;
    if (term) { term.reset(); term.focus(); }
    if (status) status.textContent = `${d.kind} · ${d.pty ? 'ConPTY' : 'pipe'} · ${d.session}`;
    if (termTimer) clearInterval(termTimer);
    termTimer = setInterval(pollTerm, 180);
  };

  window.pollTerm = async function () {
    if (!termSession) return;
    try {
      const r = await fetch(`api/chappa/term/read?session=${encodeURIComponent(termSession)}&cursor=${termCursor}`);
      const d = await r.json();
      if (!d.ok) return;
      if (d.data) {
        if (term) term.write(d.data);
        termCursor = d.cursor;
      }
      if (!d.alive) {
        const status = document.getElementById('termStatus');
        if (status) status.textContent += ' · ended';
        clearInterval(termTimer); termTimer = null;
      }
    } catch (_) {}
  };

  function sendTermRaw(data) {
    if (!termSession) return;
    fetch('api/chappa/term/input', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: termSession, data })
    }).catch(() => {});
  }

  window.stopTerm = async function () {
    if (!termSession) return;
    await fetch('api/chappa/term/stop', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: termSession })
    }).catch(() => {});
    termSession = null;
    if (termTimer) { clearInterval(termTimer); termTimer = null; }
    const status = document.getElementById('termStatus');
    if (status) status.textContent = 'Closed.';
  };

  window.loadToolCatalog = async function () {
    const teamEl = document.getElementById('toolTeamFilter');
    const qEl = document.getElementById('toolSearch');
    const team = (teamEl && teamEl.value) || 'all';
    const q = (qEl && qEl.value) || '';
    const list = document.getElementById('toolsList');
    if (list) list.innerHTML = '<div class="ch-muted">Loading catalog…</div>';
    let data;
    try {
      const r = await fetch(`api/chappa/tools?team=${encodeURIComponent(team)}&q=${encodeURIComponent(q)}&limit=80`);
      if (!r.ok) throw new Error('HTTP ' + r.status);
      data = await r.json();
    } catch (err) {
      if (list) list.innerHTML = `<div class="ch-muted">Catalog unavailable: ${esc(String(err.message || err))}</div>`;
      return;
    }
    const counts = (data.stats && data.stats.counts) || {};
    const line = document.getElementById('toolStatsLine');
    if (line) {
      line.textContent = `${counts.tools || 0} tools · ${counts.red || 0} red · ${counts.blue || 0} blue · `
        + `${counts.both || 0} dual-use · showing ${(data.tools || []).length} of ${data.total || 0}`
        + ` · state ${data.state || '?'}${data.active_target ? ' · target ' + data.active_target : ''}`
        + (data.allow_red ? ' · red enabled' : ' · red disabled');
    }
    if (!list) return;
    list.innerHTML = '';
    (data.tools || []).forEach((t) => {
      toolCache.set(t.id, t);
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `ch-btn ch-tool-row team-${t.team}`;
      b.innerHTML = `<span class="ch-tool-name">${esc(t.title)}</span>`
        + `<span class="ch-tool-meta">${esc((t.team || '').toUpperCase())} · ${esc(t.category || '')}`
        + `${(t.params || []).length ? ' · params: ' + esc(t.params.join(', ')) : ''}</span>`;
      b.onclick = () => selectCatalogTool(t.id);
      list.appendChild(b);
    });
    if (!(data.tools || []).length) list.innerHTML = '<div class="ch-muted">No tools matched.</div>';
  };

  window.selectCatalogTool = function (id) {
    const t = toolCache.get(id);
    const detail = document.getElementById('toolDetail');
    if (!t || !detail) return;
    const commands = [].concat(t.run || [], (t.usage || []).map((u) => u[1]));
    const params = t.params || [];
    detail.innerHTML = '';
    const head = document.createElement('div');
    head.className = 'ch-muted';
    head.textContent = `${t.title} — ${t.team} · ${t.category} · phase ${t.phase}`;
    detail.appendChild(head);
    params.forEach((p) => {
      const inp = document.createElement('input');
      inp.className = 'ch-input ch-tool-param';
      inp.dataset.param = p;
      inp.placeholder = `<${p}>`;
      detail.appendChild(inp);
    });
    if (!commands.length) {
      const none = document.createElement('div');
      none.className = 'ch-muted';
      none.textContent = t.url ? `Reference/installable entry — ${t.url}` : 'This entry declares no runnable command.';
      detail.appendChild(none);
      return;
    }
    commands.slice(0, 6).forEach((cmd) => {
      const row = document.createElement('div');
      row.className = 'ch-row ch-tool-cmdrow';
      const code = document.createElement('code');
      code.className = 'ch-tool-cmd';
      code.textContent = cmd;
      const dry = document.createElement('button');
      dry.type = 'button';
      dry.className = 'ch-btn';
      dry.textContent = 'Dry';
      dry.onclick = () => runCatalogTool(id, cmd, true);
      const run = document.createElement('button');
      run.type = 'button';
      run.className = 'ch-btn on';
      run.textContent = 'Run';
      run.onclick = () => runCatalogTool(id, cmd, false);
      row.appendChild(code);
      row.appendChild(dry);
      row.appendChild(run);
      detail.appendChild(row);
    });
  };

  window.runCatalogTool = async function (id, command, dryRun) {
    const out = document.getElementById('toolRunOutput');
    const params = {};
    document.querySelectorAll('.ch-tool-param').forEach((inp) => {
      const v = (inp.value || '').trim();
      if (v) params[inp.dataset.param] = v;
    });
    if (out) out.textContent = dryRun ? 'Checking…' : 'Running…';
    let d;
    try {
      const r = await fetch('api/chappa/tools/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id, command, params, dry_run: !!dryRun, timeout_s: 60 })
      });
      d = await r.json();
    } catch (err) {
      if (out) out.textContent = 'Run failed: ' + String(err.message || err);
      return;
    }
    const lines = [`${d.ok ? 'OK' : 'REFUSED/FAILED'} · ${id}`];
    if (d.error) lines.push(`error: ${d.error}`);
    if (d.argv) lines.push(`argv: ${JSON.stringify(d.argv)}`);
    if (d.exit_code !== undefined && d.exit_code !== null) lines.push(`exit: ${d.exit_code} · ${d.duration_ms || 0}ms`);
    if (d.install_hint) lines.push(`install: ${d.install_hint}`);
    if (d.stdout) lines.push('', d.stdout.trim());
    if (d.stderr) lines.push('', '[stderr]', d.stderr.trim());
    if (out) out.textContent = lines.join('\n');
    refreshStatus();
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
    es.addEventListener('tool_run', (ev) => {
      try {
        const d = JSON.parse(ev.data);
        const out = document.getElementById('toolRunOutput');
        if (out && d.tool_id) {
          out.textContent = `${d.ok ? 'OK' : 'REFUSED/FAILED'} · ${d.title || d.tool_id}`
            + (d.error ? `\nerror: ${d.error}` : '') + (d.argv && d.argv.length ? `\nargv: ${JSON.stringify(d.argv)}` : '');
        }
        refreshStatus();
      } catch (_) {}
    });
  }

  // Deep link: /#tools opens that drawer pane directly (handy for screenshots,
  // bookmarks, and jumping straight to a pane from another app).
  const openPaneFromHash = () => {
    const name = (location.hash || '').replace(/^#\/?/, '').trim();
    if (name) openDrawer(name);
  };
  window.addEventListener('hashchange', openPaneFromHash);

  refreshStatus();
  loadModels();
  openPaneFromHash();
})();
