/* ==========================================================================
   Chappa V2 — Interactive God's Eye View 3D Geospatial Globe
   - Renders live Vigil SOC pins, traceroute/correlation arcs, smooth camera
     flyTo(lat, lon), orbital satellites, and drag-orbit/zoom
   - Seamless offline-first globe that pairs with external gods-eye-view
   ========================================================================== */
(function (root) {
  'use strict';

  function createGlobe(canvas) {
    const ctx = canvas.getContext('2d');
    let W = 1, H = 1, DPR = 1;
    let yaw = 1.32, pitch = 0.28, targetYaw = 1.32, targetPitch = 0.28, zoom = 1.0;
    let dragging = false, lx = 0, ly = 0, t = 0, alive = true, rafId = 0;
    let pins = [];
    let focusLabel = 'KINGSTON HQ';

    // Procedural continent point cloud (zero CDN)
    const land = [];
    for (let i = 0; i < 900; i++) {
      const u = Math.sin(i * 12.9898) * 43758.5453;
      const v = Math.sin(i * 78.233) * 19341.231;
      const lat = Math.asin((u - Math.floor(u)) * 2 - 1);
      const lon = (v - Math.floor(v)) * Math.PI * 2 - Math.PI;
      const c = Math.sin(lon * 2.1 + Math.cos(lat * 3.0)) + Math.cos(lat * 2.6 - lon * 1.3) + 0.45 * Math.sin(lon * 4.8 + lat * 3.9);
      if (c > 0.26) {
        land.push([Math.cos(lat) * Math.cos(lon), Math.sin(lat), Math.cos(lat) * Math.sin(lon), c > 1.05 ? 1 : 0]);
      }
    }

    function llTo3D(latDeg, lonDeg, rad) {
      const lat = (latDeg * Math.PI) / 180;
      const lon = (lonDeg * Math.PI) / 180;
      const r = rad || 1.42;
      return [r * Math.cos(lat) * Math.cos(lon), r * Math.sin(lat), r * Math.cos(lat) * Math.sin(lon)];
    }

    function proj(x, y, z) {
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const cp = Math.cos(pitch), sp = Math.sin(pitch);
      const x1 = x * cy - z * sy, z1 = x * sy + z * cy;
      const y2 = y * cp - z1 * sp, z2 = y * sp + z1 * cp;
      const d = 5.0 / Math.max(0.8, 5.4 - z2);
      const sc = Math.min(W, H) * 0.27 * zoom;
      return { x: W * 0.5 + x1 * d * sc, y: H * 0.5 - y2 * d * sc, z: z2 };
    }

    function resize() {
      const r = canvas.getBoundingClientRect();
      DPR = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(200, Math.round(r.width || 600));
      H = Math.max(200, Math.round(r.height || 400));
      if (canvas.width !== Math.round(W * DPR) || canvas.height !== Math.round(H * DPR)) {
        canvas.width = Math.round(W * DPR);
        canvas.height = Math.round(H * DPR);
      }
    }

    function frame() {
      if (!alive) return;
      rafId = requestAnimationFrame(frame);
      if (document.hidden) return;
      resize();
      t += 0.016;
      if (!dragging) {
        yaw += (targetYaw - yaw) * 0.06;
        pitch += (targetPitch - pitch) * 0.06;
        targetYaw += 0.0022;
      }

      ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const ctr = proj(0, 0, 0);
      const R = Math.min(W, H) * 0.35 * zoom;

      // Atmosphere glow (Red Matrix Crimson)
      const atm = ctx.createRadialGradient(ctr.x, ctr.y, R * 0.55, ctr.x, ctr.y, R * 1.4);
      atm.addColorStop(0, 'rgba(232, 28, 46, 0.22)');
      atm.addColorStop(0.65, 'rgba(255, 70, 90, 0.06)');
      atm.addColorStop(1, 'transparent');
      ctx.fillStyle = atm;
      ctx.fillRect(0, 0, W, H);

      // Lat/Lon wireframe sphere
      ctx.strokeStyle = 'rgba(232, 28, 46, 0.28)';
      ctx.lineWidth = 1;
      for (let lat = -60; lat <= 60; lat += 30) {
        const rl = (lat * Math.PI) / 180, y = Math.sin(rl) * 1.4, cr = Math.cos(rl) * 1.4;
        ctx.beginPath();
        for (let i = 0; i <= 40; i++) {
          const a = (i / 40) * Math.PI * 2;
          const p = proj(Math.cos(a) * cr, y, Math.sin(a) * cr);
          i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
        }
        ctx.stroke();
      }
      for (let m = 0; m < 12; m++) {
        const lon = (m / 12) * Math.PI;
        ctx.beginPath();
        for (let i = 0; i <= 40; i++) {
          const a = (i / 40) * Math.PI * 2;
          const p = proj(Math.cos(a) * Math.cos(lon) * 1.4, Math.sin(a) * 1.4, Math.cos(a) * Math.sin(lon) * 1.4);
          i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
        }
        ctx.stroke();
      }

      // Landmasses
      land.forEach((pt) => {
        const p = proj(pt[0] * 1.41, pt[1] * 1.41, pt[2] * 1.41);
        if (p.z < -0.25) return;
        ctx.fillStyle = pt[3] ? '#ff6b7d' : '#e81c2e';
        ctx.globalAlpha = Math.max(0.2, Math.min(0.95, (p.z + 1.4) / 2.4));
        ctx.fillRect(p.x - 1.3, p.y - 1.3, 2.6, 2.6);
      });
      ctx.globalAlpha = 1;

      // Correlation arcs from HQ to all SOC pins
      const hq = pins[0] ? llTo3D(pins[0].lat, pins[0].lon, 1.44) : llTo3D(18.0179, -76.8099, 1.44);
      pins.slice(1, 14).forEach((pin) => {
        const dst = llTo3D(pin.lat, pin.lon, 1.44);
        const col = (pin.severity === 'critical' || pin.severity === 'high') ? '#ff2a42' : '#ff8a98';
        ctx.strokeStyle = col + '99';
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        for (let s = 0; s <= 18; s++) {
          const f = s / 18;
          const lift = 1.0 + Math.sin(f * Math.PI) * 0.34;
          const mx = (hq[0] * (1 - f) + dst[0] * f) * lift;
          const my = (hq[1] * (1 - f) + dst[1] * f) * lift;
          const mz = (hq[2] * (1 - f) + dst[2] * f) * lift;
          const p = proj(mx, my, mz);
          s ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y);
        }
        ctx.stroke();
      });

      // Live SOC & Telemetry Pins
      ctx.font = '600 10px ui-monospace, SFMono-Regular, Menlo, monospace';
      pins.forEach((pin, idx) => {
        const v = llTo3D(pin.lat, pin.lon, 1.45);
        const p = proj(v[0], v[1], v[2]);
        if (p.z < -0.1) return;
        const hot = pin.severity === 'critical' || pin.severity === 'high';
        const col = hot ? '#ff2a42' : '#ff8a98';
        ctx.strokeStyle = col;
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 4.5 + Math.sin(t * 4 + idx) * 2.2, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = hot ? '#ffffff' : col;
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2.8, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = '#ffeef1';
        ctx.fillText(String(pin.label || 'PIN').slice(0, 22), p.x + 9, p.y + 3);
      });

      // Focus HUD pill
      ctx.fillStyle = 'rgba(14, 4, 8, 0.86)';
      ctx.strokeStyle = 'rgba(232, 28, 46, 0.55)';
      ctx.fillRect(14, H - 36, 260, 24);
      ctx.strokeRect(14, H - 36, 260, 24);
      ctx.fillStyle = '#ff6b7d';
      ctx.fillText(`GOD'S EYE · ${focusLabel.slice(0, 24)} · ${pins.length} PINS`, 22, H - 20);
    }

    canvas.addEventListener('pointerdown', (e) => { dragging = true; lx = e.clientX; ly = e.clientY; });
    window.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      yaw += (e.clientX - lx) * 0.008;
      targetYaw = yaw;
      pitch = Math.max(-1.1, Math.min(1.1, pitch + (e.clientY - ly) * 0.007));
      targetPitch = pitch;
      lx = e.clientX; ly = e.clientY;
    });
    window.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoom = Math.max(0.65, Math.min(1.9, zoom * (e.deltaY > 0 ? 0.93 : 1.07)));
    }, { passive: false });

    rafId = requestAnimationFrame(frame);

    return {
      setPins(list) { pins = Array.isArray(list) ? list : []; },
      flyTo(lat, lon, label) {
        targetYaw = -((Number(lon) || 0) * Math.PI) / 180 + Math.PI * 0.5;
        targetPitch = Math.max(-0.9, Math.min(0.9, ((Number(lat) || 0) * Math.PI) / 180 * 0.65));
        if (label) focusLabel = String(label);
      },
      destroy() { alive = false; if (rafId) cancelAnimationFrame(rafId); }
    };
  }

  root.ChappaGlobe = { createGlobe };
})(typeof window !== 'undefined' ? window : globalThis);
