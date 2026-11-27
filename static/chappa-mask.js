/* ==========================================================================
   Chappa V2 — Agentsar x Spider-Verse 3D Hacker Mask Engine
   - Procedural 3D Guy Fawkes / Hacker Mask mesh (no external 3D libs)
   - Cel-shaded rim lighting, Ben-Day halftone cheeks, cyan/crimson chromatic
     aberration, CMYK orbital rings, 12fps ("On Twos") / 60fps cadence
   - State-reactive: IDLE | RECON | ALERT | CONTAINED
   ========================================================================== */
(function (root) {
  'use strict';

  function createMaskStage(canvas, opts) {
    const o = opts || {};
    const ctx = canvas.getContext('2d');
    let W = 1, H = 1, DPR = 1;
    let yaw = 0.22, pitch = -0.06, zoom = o.zoom || 1.0;
    let dragging = false, lx = 0, ly = 0, t = 0, lastDraw = 0;
    let alive = true, rafId = 0;
    let state = String(o.state || 'IDLE').toUpperCase();
    let fps = Number(o.fps || 12);
    const transparent = o.transparent !== false;

    // Build sculpted 3D Guy Fawkes mask grid (u: -1..1 across width, v: -1..1 top..bottom)
    const NU = 16, NV = 18;
    const grid = [];
    for (let iv = 0; iv <= NV; iv++) {
      const v = (iv / NV) * 2 - 1; // -1 (forehead top) -> +1 (chin)
      const row = [];
      for (let iu = 0; iu <= NU; iu++) {
        const u = (iu / NU) * 2 - 1;
        // Tapered oval contour: wider at forehead/cheeks, narrow at chin
        const taper = v > 0.15 ? 1 - 0.56 * Math.pow((v - 0.15) / 0.85, 1.35) : 1 - 0.14 * Math.pow(Math.max(0, -v - 0.35) / 0.65, 1.6);
        const x = u * 0.96 * taper;
        const y = -v * 1.24;
        // 3D depth curve: cylindrical wrap + prominent cheekbones + nose bridge + chin
        const wrap = Math.sqrt(Math.max(0.02, 1 - u * u * 0.68)) * 0.55;
        const nose = Math.exp(-Math.pow(u / 0.16, 2)) * Math.exp(-Math.pow((v - 0.04) / 0.36, 2)) * (0.42 + Math.max(0, v + 0.15) * 0.25);
        const cheekL = Math.exp(-Math.pow((u + 0.48) / 0.28, 2) - Math.pow((v - 0.12) / 0.25, 2)) * 0.16;
        const cheekR = Math.exp(-Math.pow((u - 0.48) / 0.28, 2) - Math.pow((v - 0.12) / 0.25, 2)) * 0.16;
        const brow = Math.exp(-Math.pow((v + 0.34) / 0.12, 2)) * 0.08;
        const chin = Math.exp(-Math.pow(u / 0.26, 2) - Math.pow((v - 0.82) / 0.22, 2)) * 0.14;
        const z = wrap + nose + cheekL + cheekR + brow + chin - 0.25;
        row.push([x, y, z, u, v]);
      }
      grid.push(row);
    }

    // Feature curves mapped directly onto the 3D mask surface
    function surfPt(u, v, zOff) {
      const taper = v > 0.15 ? 1 - 0.56 * Math.pow((v - 0.15) / 0.85, 1.35) : 1 - 0.14 * Math.pow(Math.max(0, -v - 0.35) / 0.65, 1.6);
      const x = u * 0.96 * taper;
      const y = -v * 1.24;
      const wrap = Math.sqrt(Math.max(0.02, 1 - u * u * 0.68)) * 0.55;
      const nose = Math.exp(-Math.pow(u / 0.16, 2)) * Math.exp(-Math.pow((v - 0.04) / 0.36, 2)) * (0.42 + Math.max(0, v + 0.15) * 0.25);
      const cheekL = Math.exp(-Math.pow((u + 0.48) / 0.28, 2) - Math.pow((v - 0.12) / 0.25, 2)) * 0.16;
      const cheekR = Math.exp(-Math.pow((u - 0.48) / 0.28, 2) - Math.pow((v - 0.12) / 0.25, 2)) * 0.16;
      const brow = Math.exp(-Math.pow((v + 0.34) / 0.12, 2)) * 0.08;
      const chin = Math.exp(-Math.pow(u / 0.26, 2) - Math.pow((v - 0.82) / 0.22, 2)) * 0.14;
      return [x, y, wrap + nose + cheekL + cheekR + brow + chin - 0.25 + (zOff || 0.03)];
    }

    const browL = [[-0.64, -0.30], [-0.46, -0.44], [-0.26, -0.44], [-0.12, -0.32]].map(([u, v]) => surfPt(u, v, 0.04));
    const browR = [[0.12, -0.32], [0.26, -0.44], [0.46, -0.44], [0.64, -0.30]].map(([u, v]) => surfPt(u, v, 0.04));
    const eyeL = [[-0.56, -0.18], [-0.39, -0.24], [-0.21, -0.18], [-0.39, -0.12]].map(([u, v]) => surfPt(u, v, 0.03));
    const eyeR = [[0.21, -0.18], [0.39, -0.24], [0.56, -0.18], [0.39, -0.12]].map(([u, v]) => surfPt(u, v, 0.03));
    const stacheL = [[-0.03, 0.30], [-0.22, 0.35], [-0.46, 0.36], [-0.62, 0.24]].map(([u, v]) => surfPt(u, v, 0.05));
    const stacheR = [[0.03, 0.30], [0.22, 0.35], [0.46, 0.36], [0.62, 0.24]].map(([u, v]) => surfPt(u, v, 0.05));
    const smile = [[-0.30, 0.45], [-0.14, 0.49], [0, 0.50], [0.14, 0.49], [0.30, 0.45]].map(([u, v]) => surfPt(u, v, 0.04));
    const goatee = [[-0.09, 0.56], [0.09, 0.56], [0.06, 0.88], [0, 0.96], [-0.06, 0.88]].map(([u, v]) => surfPt(u, v, 0.05));
    const cheekSpotL = surfPt(-0.56, 0.08, 0.03);
    const cheekSpotR = surfPt(0.56, 0.08, 0.03);

    function resize() {
      const r = canvas.getBoundingClientRect();
      DPR = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(120, Math.round(r.width || canvas.clientWidth || 400));
      H = Math.max(120, Math.round(r.height || canvas.clientHeight || 400));
      canvas.width = Math.round(W * DPR);
      canvas.height = Math.round(H * DPR);
    }

    function proj(pt, curYaw, curPitch) {
      const cy = Math.cos(curYaw), sy = Math.sin(curYaw);
      const cp = Math.cos(curPitch), sp = Math.sin(curPitch);
      const x1 = pt[0] * cy - pt[2] * sy;
      const z1 = pt[0] * sy + pt[2] * cy;
      const y2 = pt[1] * cp - z1 * sp;
      const z2 = pt[1] * sp + z1 * cp;
      const d = 4.6 / Math.max(0.8, 5.1 - z2);
      const sc = Math.min(W, H) * 0.30 * zoom;
      return { x: W * 0.5 + x1 * d * sc, y: H * 0.5 - y2 * d * sc, z: z2 };
    }

    function palette() {
      if (state === 'ALERT') {
        return { c1: '#e81c2e', c2: '#ff6b7d', c3: '#08b6e8', fill: 'rgba(28,8,16,0.72)', feature: '#ff2b4a', eye: '#ff2b4a' };
      }
      if (state === 'RECON') {
        return { c1: '#08b6e8', c2: '#5ce5f5', c3: '#e81c2e', fill: 'rgba(8,18,34,0.68)', feature: '#050b16', eye: '#5ce5f5' };
      }
      if (state === 'CONTAINED') {
        return { c1: '#10b981', c2: '#5ce5f5', c3: '#08b6e8', fill: 'rgba(6,22,20,0.66)', feature: '#071312', eye: '#34d399' };
      }
      return { c1: '#08b6e8', c2: '#7df2ff', c3: '#e81c2e', fill: 'rgba(10,16,30,0.64)', feature: '#070c18', eye: '#08b6e8' };
    }

    function drawPoly(pts, fill, stroke, lw) {
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.closePath();
      if (fill) { ctx.fillStyle = fill; ctx.fill(); }
      if (stroke) { ctx.strokeStyle = stroke; ctx.lineWidth = lw || 1.6; ctx.stroke(); }
    }

    function drawStroke(pts, stroke, lw) {
      ctx.beginPath();
      pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
      ctx.strokeStyle = stroke;
      ctx.lineWidth = lw || 3;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
    }

    function render(now) {
      if (!alive) return;
      rafId = requestAnimationFrame(render);
      if (document.hidden) return;
      const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const minInterval = fps <= 12 ? 80 : 14;
      if (now - lastDraw < minInterval) return;
      lastDraw = now;

      resize();
      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      if (transparent) {
        ctx.clearRect(0, 0, W, H);
      } else {
        ctx.fillStyle = '#050914';
        ctx.fillRect(0, 0, W, H);
      }

      if (!reduced) {
        t += fps <= 12 ? 0.08 : 0.022;
        if (!dragging) yaw = 0.24 * Math.sin(t * 0.72);
      }

      const P = palette();
      const glitch = (state === 'ALERT' && !reduced && Math.sin(t * 17) > 0.72) ? (Math.sin(t * 53) * 5) : 0;
      const bobY = reduced ? 0 : Math.sin(t * 1.4) * 0.04;

      // Ambient holographic radial aura (subtle so mask pops against dark void)
      const aura = ctx.createRadialGradient(W * 0.5, H * 0.5, 10, W * 0.5, H * 0.5, Math.min(W, H) * 0.44);
      aura.addColorStop(0, P.c1 + '1a');
      aura.addColorStop(0.55, P.c3 + '08');
      aura.addColorStop(1, 'rgba(5, 9, 20, 0)');
      ctx.fillStyle = aura;
      ctx.fillRect(0, 0, W, H);

      // Agentsar CMYK dashed orbital rings around the 3D mask
      const ringR = Math.min(W, H) * 0.41 * zoom;
      for (let k = 0; k < 2; k++) {
        ctx.save();
        ctx.translate(W * 0.5, H * 0.5);
        ctx.rotate((k ? -1 : 1) * t * 0.28 + k * 0.7);
        ctx.strokeStyle = k === 0 ? P.c1 + '55' : P.c3 + '44';
        ctx.lineWidth = k === 0 ? 1.5 : 1.1;
        ctx.setLineDash(k === 0 ? [34, 14, 8, 14] : [16, 10]);
        ctx.beginPath();
        ctx.ellipse(0, 0, ringR * (1 + k * 0.09), ringR * (0.86 + k * 0.09), 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();
      }
      ctx.setLineDash([]);

      // Project mask mesh vertices
      const pGrid = grid.map((row) => row.map((v) => proj([v[0], v[1] + bobY, v[2]], yaw, pitch)));

      // Chromatic Spider-Verse under-offset (crimson & cyan edge ghosts)
      const off = state === 'ALERT' ? 4.5 : 2.2;
      ctx.strokeStyle = P.c3 + '55';
      ctx.lineWidth = 0.85;
      ctx.beginPath();
      for (let iv = 0; iv <= NV; iv += 2) {
        for (let iu = 0; iu < NU; iu++) {
          const a = pGrid[iv][iu], b = pGrid[iv][iu + 1];
          ctx.moveTo(a.x - off + glitch, a.y);
          ctx.lineTo(b.x - off + glitch, b.y);
        }
      }
      ctx.stroke();

      // Cel-shaded porcelain-hologram quads
      const quads = [];
      for (let iv = 0; iv < NV; iv++) {
        for (let iu = 0; iu < NU; iu++) {
          const a = pGrid[iv][iu], b = pGrid[iv][iu + 1], c = pGrid[iv + 1][iu + 1], d = pGrid[iv + 1][iu];
          const avgZ = (a.z + b.z + c.z + d.z) * 0.25;
          const uMid = (grid[iv][iu][3] + grid[iv][iu + 1][3]) * 0.5;
          const vMid = (grid[iv][iu][4] + grid[iv + 1][iu][4]) * 0.5;
          quads.push({ a, b, c, d, avgZ, uMid, vMid });
        }
      }
      quads.sort((p, q) => p.avgZ - q.avgZ);

      quads.forEach((q) => {
        const edgeRim = Math.abs(q.uMid) > 0.68 ? 0.28 : 0.08;
        ctx.fillStyle = state === 'ALERT'
          ? `rgba(255, 226, 232, ${(0.12 + edgeRim).toFixed(2)})`
          : `rgba(220, 246, 255, ${(0.11 + edgeRim).toFixed(2)})`;
        ctx.strokeStyle = P.c1 + '38';
        ctx.lineWidth = 0.7;
        ctx.beginPath();
        ctx.moveTo(q.a.x + glitch, q.a.y);
        ctx.lineTo(q.b.x + glitch, q.b.y);
        ctx.lineTo(q.c.x + glitch, q.c.y);
        ctx.lineTo(q.d.x + glitch, q.d.y);
        ctx.closePath();
        ctx.fill();
        ctx.stroke();
      });

      // Outer Spider-Verse ink rim
      const rim = [];
      for (let iv = 0; iv <= NV; iv++) rim.push(pGrid[iv][0]);
      for (let iu = 0; iu <= NU; iu++) rim.push(pGrid[NV][iu]);
      for (let iv = NV; iv >= 0; iv--) rim.push(pGrid[iv][NU]);
      for (let iu = NU; iu >= 0; iu--) rim.push(pGrid[0][iu]);
      drawStroke(rim.map((p) => ({ x: p.x + glitch, y: p.y })), P.c2, 2.2);

      // Ben-Day halftone rosy cheek dots
      [cheekSpotL, cheekSpotR].forEach((sp) => {
        const cp = proj([sp[0], sp[1] + bobY, sp[2]], yaw, pitch);
        for (let dy = -1; dy <= 1; dy++) {
          for (let dx = -1; dx <= 1; dx++) {
            if (Math.abs(dx) + Math.abs(dy) > 1) continue;
            ctx.fillStyle = 'rgba(232, 28, 46, 0.55)';
            ctx.beginPath();
            ctx.arc(cp.x + dx * 5.5 + glitch, cp.y + dy * 5.5, 2.1, 0, Math.PI * 2);
            ctx.fill();
          }
        }
      });

      // Eye cutouts + glowing cyber pupils
      const pEyeL = eyeL.map((pt) => proj([pt[0], pt[1] + bobY, pt[2]], yaw, pitch));
      const pEyeR = eyeR.map((pt) => proj([pt[0], pt[1] + bobY, pt[2]], yaw, pitch));
      drawPoly(pEyeL, '#03060d', P.c1, 1.5);
      drawPoly(pEyeR, '#03060d', P.c1, 1.5);
      [pEyeL, pEyeR].forEach((ep) => {
        const cx = (ep[0].x + ep[2].x) * 0.5 + glitch;
        const cy = (ep[1].y + ep[3].y) * 0.5;
        ctx.fillStyle = P.eye;
        ctx.beginPath();
        ctx.arc(cx, cy, state === 'ALERT' ? 3.5 : 2.6, 0, Math.PI * 2);
        ctx.fill();
      });

      // Brows, Mustache, Smile, Goatee
      const mapPts = (arr) => arr.map((pt) => {
        const p = proj([pt[0], pt[1] + bobY, pt[2]], yaw, pitch);
        return { x: p.x + glitch, y: p.y };
      });
      drawStroke(mapPts(browL), P.feature, 4.2);
      drawStroke(mapPts(browR), P.feature, 4.2);
      drawStroke(mapPts(stacheL), P.feature, 4.2);
      drawStroke(mapPts(stacheR), P.feature, 4.2);
      drawStroke(mapPts(browL), P.c1 + 'aa', 1.2);
      drawStroke(mapPts(browR), P.c1 + 'aa', 1.2);
      drawStroke(mapPts(stacheL), P.c2 + 'aa', 1.2);
      drawStroke(mapPts(stacheR), P.c2 + 'aa', 1.2);
      drawStroke(mapPts(smile), P.c2, 1.8);
      drawPoly(mapPts(goatee), P.feature, P.c1, 1.4);

      // Active RECON sweeping laser scanline across the mask
      if (state === 'RECON' && !reduced) {
        const sy = ((t * 48) % (H * 0.72)) + H * 0.14;
        const sg = ctx.createLinearGradient(0, sy - 16, 0, sy + 16);
        sg.addColorStop(0, 'transparent');
        sg.addColorStop(0.5, 'rgba(8, 182, 232, 0.45)');
        sg.addColorStop(1, 'transparent');
        ctx.fillStyle = sg;
        ctx.fillRect(W * 0.15, sy - 16, W * 0.7, 32);
      }
    }

    canvas.addEventListener('pointerdown', (e) => {
      dragging = true;
      lx = e.clientX;
      ly = e.clientY;
    });
    window.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      yaw += (e.clientX - lx) * 0.009;
      pitch = Math.max(-0.9, Math.min(0.9, pitch + (e.clientY - ly) * 0.008));
      lx = e.clientX;
      ly = e.clientY;
    });
    window.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoom = Math.max(0.65, Math.min(1.85, zoom * (e.deltaY > 0 ? 0.93 : 1.07)));
    }, { passive: false });

    rafId = requestAnimationFrame(render);

    return {
      setState(next) { state = String(next || 'IDLE').toUpperCase(); },
      setFps(next) { fps = Number(next) <= 12 ? 12 : 60; },
      destroy() { alive = false; if (rafId) cancelAnimationFrame(rafId); }
    };
  }

  root.ChappaMask = { createMaskStage };
})(typeof window !== 'undefined' ? window : globalThis);
