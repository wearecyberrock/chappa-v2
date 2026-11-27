/* ==========================================================================
   Chappa V2 — Floating 3D Binary (1 & 0) Particle Hacker Mask Core
   - Powered by Assimilis Holo Particle Physics (spring-to-3D-target + 3D curl
     murmuration + cursor parting/vortex swirl + state scatter-reassemble)
   - ZERO solid skin/shell: the 3D Guy Fawkes Hacker Mask is formed purely out
     of ~2,200 floating, glowing 3D `1` and `0` particles suspended in space,
     with negative-space void for eyes, brows, handlebar mustache, smile & goatee
   - Live Voice-Reactive Glowing Eyes: driven by Assimilis Fish Audio / Voice
     Studio Web Audio AnalyserNode (dormant hollow sockets when silent -> blazing
     crimson-white pulsing eyes + acoustic particle ripples when speaking!)
   - Drop-in custom .OBJ particle morphing (~/.chappa/modules/custom_mask.obj)
   - Respects prefers-reduced-motion & pauses when document.hidden
   ========================================================================== */
(function (root) {
  'use strict';

  const TAU = Math.PI * 2;

  function smoothstep(e0, e1, x) {
    const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)));
    return t * t * (3 - 2 * t);
  }

  function gauss2(x, y, cx, cy, sx, sy) {
    const dx = (x - cx) / sx, dy = (y - cy) / sy;
    return Math.exp(-(dx * dx + dy * dy));
  }

  // Authentic Guy Fawkes silhouette: broad smoothly rounded forehead crown, full cheeks, tapered chin
  function maskBoundary(u, v) {
    if (v < -0.25) {
      const t = (-v - 0.25) / 0.75;
      return Math.max(0.06, 0.88 * Math.pow(Math.max(0.0, 1.0 - Math.pow(t, 4.4)), 0.34));
    }
    const t = (v + 0.25) / 1.25;
    const cheek = 0.045 * Math.sin(Math.min(1, t * 2.1) * Math.PI);
    const jaw = 0.88 * Math.pow(Math.max(0.0, 1.0 - Math.pow(t, 2.15) * 0.96), 0.56);
    return Math.max(0.06, jaw + cheek * (1.0 - smoothstep(0.65, 1.0, t)));
  }

  // Sculpted 3D facial heightfield z(u, v)
  function maskHeight(u, v) {
    const au = Math.abs(u);
    const hw = maskBoundary(u, v);
    const rn = Math.min(1.0, au / Math.max(0.06, hw));

    const domeU = Math.sqrt(Math.max(0.002, 1.0 - rn * rn * 0.86)) * 0.70;
    const domeV = Math.cos(v * 1.08) * 0.20;
    const forehead = gauss2(u, v, 0.0, -0.58, 0.62, 0.30) * 0.12;
    const temple = -gauss2(au, v, 0.68, -0.34, 0.22, 0.22) * 0.045;

    const browArchY = -0.35 + Math.pow((au - 0.34) * 1.3, 2) * 0.20;
    const browRidge = Math.exp(-Math.pow((v - browArchY) / 0.09, 2))
      * smoothstep(0.04, 0.18, au) * (1.0 - smoothstep(0.58, 0.82, au)) * 0.08;

    const eyeSocket = -gauss2(au, v, 0.34, -0.175, 0.20, 0.11) * 0.09;
    const upperLid = gauss2(au, v, 0.34, -0.235, 0.18, 0.055) * 0.04;
    const lowerLid = gauss2(au, v, 0.34, -0.092, 0.19, 0.06) * 0.045;

    const noseBridge = Math.exp(-Math.pow(u / (0.115 + Math.max(0, v + 0.20) * 0.11), 2))
      * smoothstep(-0.34, -0.12, v) * (1.0 - smoothstep(0.14, 0.25, v)) * (0.20 + smoothstep(-0.22, 0.12, v) * 0.16);
    const noseTip = gauss2(u, v, 0.0, 0.125, 0.13, 0.098) * 0.18;
    const noseWing = gauss2(au, v, 0.13, 0.155, 0.085, 0.068) * 0.09;
    const nostrilIndent = -gauss2(au, v, 0.076, 0.205, 0.045, 0.032) * 0.075;
    const underNose = -gauss2(u, v, 0.0, 0.248, 0.17, 0.045) * 0.055;

    const cheekbone = gauss2(au, v, 0.46, 0.06, 0.28, 0.22) * 0.155;
    const midCheek = gauss2(au, v, 0.40, 0.25, 0.26, 0.20) * 0.09;
    const smilePuff = gauss2(au, v, 0.30, 0.30, 0.15, 0.14) * 0.045;

    const upperLip = gauss2(u, v, 0.0, 0.365, 0.29, 0.07) * 0.085;
    const mouthCrease = -gauss2(u, v, 0.0, 0.45, 0.24, 0.028) * 0.065;
    const lowerLip = gauss2(u, v, 0.0, 0.52, 0.25, 0.068) * 0.09;
    const chinHollow = -gauss2(u, v, 0.0, 0.625, 0.24, 0.07) * 0.045;
    const chinBoss = gauss2(u, v, 0.0, 0.78, 0.26, 0.17) * 0.135;

    const edgeRoll = -Math.pow(smoothstep(0.84, 1.0, rn), 1.8) * 0.16;

    return domeU + domeV + forehead + temple + browRidge + eyeSocket + upperLid + lowerLid
      + noseBridge + noseTip + noseWing + nostrilIndent + underNose
      + cheekbone + midCheek + smilePuff
      + upperLip + mouthCrease + lowerLip + chinHollow + chinBoss + edgeRoll - 0.36;
  }

  // Signed distance to sleek squinting Guy Fawkes almond eye cutouts (negative = hollow eye socket)
  function eyeSlitSdf(u, v) {
    const au = Math.abs(u);
    const ex = (au - 0.345) / 0.162;
    if (Math.abs(ex) >= 1.0) return 0.12;
    const arch = -0.168 + ex * ex * 0.036 - ex * 0.010;
    const dy = v - arch;
    const topH = 0.045 * Math.max(0.0, 1.0 - ex * ex);
    const botH = 0.022 * Math.max(0.0, 1.0 - ex * ex);
    return dy < 0 ? (-dy - topH) : (dy - botH);
  }

  // Crisp 512x512 feature/negative-space map: black = carved void (brows, handlebar mustache, smile, goatee)
  function buildFeatureMaskData() {
    const S = 512;
    const c = document.createElement('canvas');
    c.width = S; c.height = S;
    const g = c.getContext('2d');
    const px = (u) => (u + 1.0) * 0.5 * S;
    const py = (v) => (v + 1.0) * 0.5 * S;

    g.fillStyle = '#ffffff';
    g.fillRect(0, 0, S, S);

    function softSpot(u, v, rx, ry, col) {
      g.save();
      g.translate(px(u), py(v));
      g.scale(rx * S * 0.5, ry * S * 0.5);
      const rg = g.createRadialGradient(0, 0, 0.05, 0, 0, 1);
      rg.addColorStop(0, col);
      rg.addColorStop(1, 'rgba(0,0,0,0)');
      g.fillStyle = rg;
      g.beginPath();
      g.arc(0, 0, 1, 0, TAU);
      g.fill();
      g.restore();
    }

    // Subtle nostril indentations only (keep bright 1/0 eyelid ribbon between arched brow and sleek almond eye!)
    softSpot(-0.075, 0.205, 0.046, 0.030, 'rgba(0,0,0,0.78)');
    softSpot(0.075, 0.205, 0.046, 0.030, 'rgba(0,0,0,0.78)');

    function drawMirrorShape(fn) {
      [-1, 1].forEach((sgn) => {
        g.save();
        g.beginPath();
        fn(sgn);
        g.closePath();
        g.fillStyle = '#000000';
        g.fill();
        g.restore();
      });
    }

    // Iconic slim arched Guy Fawkes eyebrows (leaves clean glowing eyelid gap above the almond eyes)
    drawMirrorShape((s) => {
      g.moveTo(px(s * 0.11), py(-0.315));
      g.bezierCurveTo(px(s * 0.25), py(-0.460), px(s * 0.49), py(-0.460), px(s * 0.65), py(-0.315));
      g.bezierCurveTo(px(s * 0.50), py(-0.395), px(s * 0.27), py(-0.395), px(s * 0.13), py(-0.282));
    });

    // Iconic curled upturned handlebar mustache (crisp negative space cutout matching image.png!)
    drawMirrorShape((s) => {
      g.moveTo(px(s * 0.004), py(0.320));
      g.bezierCurveTo(px(s * 0.12), py(0.280), px(s * 0.24), py(0.388), px(s * 0.44), py(0.376));
      g.bezierCurveTo(px(s * 0.545), py(0.365), px(s * 0.61), py(0.295), px(s * 0.655), py(0.215));
      g.bezierCurveTo(px(s * 0.585), py(0.340), px(s * 0.505), py(0.432), px(s * 0.34), py(0.442));
      g.bezierCurveTo(px(s * 0.19), py(0.448), px(s * 0.08), py(0.392), px(s * 0.004), py(0.384));
    });

    // Crisp carved smile slit
    g.strokeStyle = '#000000';
    g.lineWidth = 7;
    g.lineCap = 'round';
    g.beginPath();
    g.moveTo(px(-0.25), py(0.462));
    g.quadraticCurveTo(px(0), py(0.490), px(0.25), py(0.462));
    g.stroke();

    // Iconic tapered pointed goatee
    g.beginPath();
    g.moveTo(px(-0.088), py(0.575));
    g.quadraticCurveTo(px(0), py(0.556), px(0.088), py(0.575));
    g.bezierCurveTo(px(0.068), py(0.73), px(0.044), py(0.86), px(0.0), py(0.955));
    g.bezierCurveTo(px(-0.044), py(0.86), px(-0.068), py(0.73), px(-0.088), py(0.575));
    g.closePath();
    g.fillStyle = '#000000';
    g.fill();

    const img = g.getImageData(0, 0, S, S).data;
    return { S, img };
  }

  // Crisp 512x256 Dual-Channel Binary Glyph Atlas:
  //   Tile 0 (0..256) = '0', Tile 1 (256..512) = '1'
  //   R = crisp geometric digit stroke, G = soft neon glow bloom
  function buildBinaryGlyphAtlas() {
    const c = document.createElement('canvas');
    c.width = 512; c.height = 256;
    const g = c.getContext('2d');
    g.fillStyle = '#000000';
    g.fillRect(0, 0, 512, 256);

    g.font = '800 198px "DejaVu Sans Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
    g.textAlign = 'center';
    g.textBaseline = 'middle';

    g.shadowColor = '#00ff00';
    g.shadowBlur = 28;
    g.fillStyle = '#00c400';
    g.fillText('0', 128, 134); g.fillText('1', 384, 134);
    g.fillText('0', 128, 134); g.fillText('1', 384, 134);

    g.globalCompositeOperation = 'lighter';
    g.shadowBlur = 0;
    g.fillStyle = '#ff0000';
    g.fillText('0', 128, 134); g.fillText('1', 384, 134);
    return c;
  }

  // Sample floating 3D `1` & `0` particles across the Guy Fawkes 3D topology (ZERO solid mesh!)
  function buildMaskParticleCloud() {
    const feat = buildFeatureMaskData();
    const readFeat = (u, v) => {
      const ix = Math.max(0, Math.min(feat.S - 1, Math.round((u + 1.0) * 0.5 * (feat.S - 1))));
      const iy = Math.max(0, Math.min(feat.S - 1, Math.round((v + 1.0) * 0.5 * (feat.S - 1))));
      return feat.img[(iy * feat.S + ix) * 4] / 255;
    };

    const particles = []; // { x, y, z, lum, size, phase, colX, kind }
    const eps = 0.012;
    const Lkey = [0.10, 0.16, 0.98];
    const Lfill = [-0.38, -0.12, 0.92];
    const hash = (a, b) => {
      const s = Math.sin(a * 127.1 + b * 311.7) * 43758.5453;
      return s - Math.floor(s);
    };

    // Layer 1: High-Definition 3D Floating Guy Fawkes Binary Cloud (~1,850 crisp floating `1` & `0` particles)
    const COLS = 47, ROWS = 55;
    for (let r = 0; r < ROWS; r++) {
      const v = (r / (ROWS - 1)) * 1.94 - 0.97;
      const hw = maskBoundary(0, v);
      const rowShift = (r % 2) * 0.010;
      for (let c = 0; c < COLS; c++) {
        const uRaw = (c / (COLS - 1)) * 1.84 - 0.92 + rowShift;
        if (Math.abs(uRaw) > hw * 0.99) continue;

        // Sleek hollow Guy Fawkes almond eye cutouts (kept empty for voice-reactive glowing eyes)
        const es = eyeSlitSdf(uRaw, v);
        if (es < 0.008) continue;

        // Carved negative-space eyebrows, handlebar mustache, smile crease, goatee
        const fv = readFeat(uRaw, v);
        if (fv < 0.38) continue;

        const jx = (hash(c, r) - 0.5) * 0.010;
        const jy = (hash(r + 17, c + 3) - 0.5) * 0.009;
        const u = uRaw + jx;
        const vv = v + jy;
        const rn = Math.min(1.0, Math.abs(u) / Math.max(0.06, maskBoundary(0, vv)));

        const x = u * 1.04;
        const y = -vv * 1.14;
        const z = maskHeight(u, vv);

        // Real 3D analytical normal with balanced frontal wrap lighting (matches image.png clarity!)
        const dzdu = (maskHeight(u + eps, vv) - maskHeight(u - eps, vv)) / (2 * eps);
        const dzdv = (maskHeight(u, vv + eps) - maskHeight(u, vv - eps)) / (2 * eps);
        let nx = -dzdu / 1.04, ny = dzdv / 1.14, nz = 1.0;
        const nlen = Math.hypot(nx, ny, nz) || 1.0;
        nx /= nlen; ny /= nlen; nz /= nlen;

        const wrapKey = Math.max(0, (nx * Lkey[0] + ny * Lkey[1] + nz * Lkey[2] + 0.42) / 1.42);
        const diffFill = Math.max(0, nx * Lfill[0] + ny * Lfill[1] + nz * Lfill[2]);
        // Soft outer vignette like reference image.png while keeping upper lids, cheeks, nose & chin crisp!
        const edgeFade = 1.0 - smoothstep(0.76, 1.05, rn);
        const topBotFade = (1.0 - smoothstep(0.84, 1.04, Math.abs(vv))) * 0.35 + 0.65;
        const lum = Math.max(0.22, Math.min(1.0,
          (0.26 + 0.58 * wrapKey + 0.22 * diffFill) * (0.36 + 0.64 * edgeFade) * topBotFade * fv
        ));

        if (rn > 0.89 && hash(c * 3, r * 5) > edgeFade + 0.42) continue;

        const size = 0.84 + 0.34 * lum + hash(c + 5, r + 9) * 0.14;
        particles.push({
          x, y, z,
          lum,
          size,
          phase: hash(c * 7 + 1, r * 11 + 2) * TAU,
          colX: c,
          rowY: r,
          kind: 0
        });

        // Layer 2: Volumetric Inner-Depth Parallax `1` & `0` Particles (tight depth offset for crisp 3D volume)
        if (((c + r) % 3 === 0) && rn < 0.82 && lum > 0.38 && es > 0.04) {
          particles.push({
            x: x * 0.97,
            y: y * 0.97,
            z: z - 0.12 - hash(c + 31, r + 41) * 0.08,
            lum: lum * 0.34,
            size: size * 0.72,
            phase: hash(c * 13 + 9, r * 5 + 3) * TAU,
            colX: c,
            rowY: r,
            kind: 0
          });
        }
      }
    }

    // Layer 3: Assimilis-Style Murmuration Scout `1` & `0` Swarm (~400 drifting particles around the mask)
    const SCOUTS = 400;
    const ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < SCOUTS; i++) {
      const yy = 1 - (2 * (i + 0.5)) / SCOUTS;
      const rr = Math.sqrt(Math.max(0, 1 - yy * yy));
      const a = ga * i;
      const rad = 1.24 + (i % 19) * 0.045;
      particles.push({
        x: Math.cos(a) * rr * rad,
        y: yy * rad * 1.05,
        z: Math.sin(a) * rr * rad * 0.85,
        lum: 0.22 + (i % 7) * 0.055,
        size: 0.62 + (i % 5) * 0.10,
        phase: a % TAU,
        colX: i % 46,
        rowY: i % 46,
        kind: 1
      });
    }

    // Layer 4: Voice-Reactive Sculpted Almond 3D Eye Cores (34 precision particles per eye!)
    // Dormant dark embers when silent -> blazing crimson-red almond eyes with ruby-white iris when Fish/Voice Studio speaks!
    [-1, 1].forEach((side) => {
      const cxU = side * 0.345;
      for (let k = 0; k < 34; k++) {
        const s = (k / 33) * 2.0 - 1.0; // -1..+1 across almond eye width
        const ex = s * 0.82;
        const archV = -0.168 + ex * ex * 0.034 - ex * 0.010;
        const vertOff = ((k % 3) - 1) * 0.011 * Math.max(0.15, 1.0 - ex * ex);
        const u = cxU + ex * 0.145;
        const v = archV + vertOff;
        const baseZ = maskHeight(u, v) - 0.025;
        const pupilW = Math.exp(-(ex * ex) * 3.8); // concentrated bright iris in center, fiery crimson along almond corners
        particles.push({
          x: u * 1.04,
          y: -v * 1.14,
          z: baseZ + pupilW * 0.03,
          lum: 0.28 + 0.72 * pupilW,
          size: 0.72 + 0.95 * pupilW,
          phase: (k * 0.43) % TAU,
          colX: side < 0 ? 12 : 34,
          rowY: 18,
          kind: 2
        });
      }
    });

    return particles;
  }

  // Optional custom .OBJ parser -> samples floating 3D `1` & `0` particles onto any uploaded 3D mesh!
  function parseObjToParticles(text) {
    const rawV = [];
    const lines = String(text || '').split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i].trim();
      if (ln.startsWith('v ')) {
        const p = ln.split(/\s+/);
        rawV.push([parseFloat(p[1]) || 0, parseFloat(p[2]) || 0, parseFloat(p[3]) || 0]);
      }
    }
    if (rawV.length < 20) return null;
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9, minZ = 1e9, maxZ = -1e9;
    for (let i = 0; i < rawV.length; i++) {
      const v = rawV[i];
      if (v[0] < minX) minX = v[0]; if (v[0] > maxX) maxX = v[0];
      if (v[1] < minY) minY = v[1]; if (v[1] > maxY) maxY = v[1];
      if (v[2] < minZ) minZ = v[2]; if (v[2] > maxZ) maxZ = v[2];
    }
    const cx = (minX + maxX) * 0.5, cy = (minY + maxY) * 0.5, cz = (minZ + maxZ) * 0.5;
    const sc = 2.05 / Math.max(0.001, maxX - minX, maxY - minY, maxZ - minZ);
    const step = Math.max(1, Math.floor(rawV.length / 2000));
    const pts = [];
    for (let i = 0; i < rawV.length; i += step) {
      const v = rawV[i];
      const x = (v[0] - cx) * sc, y = (v[1] - cy) * sc, z = (v[2] - cz) * sc;
      pts.push({ x, y, z, lum: Math.max(0.25, Math.min(1.0, 0.55 + z * 0.45)), size: 1.0, phase: (i * 0.73) % TAU, colX: Math.floor((x + 1.2) * 16), rowY: Math.floor((1.2 - y) * 16), kind: 0 });
    }
    return pts;
  }

  const PT_VS = `#version 300 es
  precision highp float;
  precision highp int;
  layout(location = 0) in vec3 aPos;
  layout(location = 1) in vec4 aMeta; // x=lum, y=phase, z=size, w=kind (0=face, 1=scout, 2=eye)
  layout(location = 2) in vec2 aGrid; // x=colX, y=rowY

  uniform vec2 uRes;
  uniform float uTime;
  uniform float uZoom;
  uniform float uDpr;
  uniform float uSpeech;
  uniform int uState; // 0=IDLE, 1=RECON, 2=ALERT, 3=CONTAINED

  out float vLum;
  out float vBit;
  out float vHot;
  out float vKind;
  out float vScan;

  float hash11(float p) { return fract(sin(p * 127.1 + 311.7) * 43758.5453123); }

  void main() {
    float zCam = 3.85 - aPos.z;
    float aspect = uRes.x / max(1.0, uRes.y);
    float f = 2.40 * uZoom;
    vec2 ndc = vec2(aPos.x * f / (zCam * aspect), aPos.y * f / zCam);
    float ndcZ = clamp((zCam - 1.0) / 6.0 * 2.0 - 1.0, -0.99, 0.99);
    gl_Position = vec4(ndc, ndcZ, 1.0);

    float kind = aMeta.w;
    vKind = kind;
    float depthScale = clamp(3.85 / max(1.2, zCam), 0.55, 1.85);
    float stageScale = clamp(min(uRes.x, uRes.y) / 680.0, 0.48, 1.35);

    if (kind > 1.5) {
      // Voice-reactive crimson almond eyes (stealthy dark ember silent -> blazing crimson-red iris speaking!)
      float alertBase = (uState == 2) ? 0.36 : 0.04;
      float eyePower = max(alertBase, 0.04 + uSpeech * 0.96);
      float eyeExpand = 0.85 + uSpeech * 0.58 + (uState == 2 ? 0.16 : 0.0);
      gl_PointSize = clamp(aMeta.z * 9.5 * eyeExpand * depthScale * stageScale * uDpr, 2.0, 26.0 * uDpr);
      vLum = aMeta.x * eyePower;
      vHot = clamp(pow(aMeta.x, 2.2) * uSpeech * 0.72, 0.0, 0.78);
      vBit = 0.0;
      vScan = 0.0;
      return;
    }

    // Dynamic cascading Matrix column glow + live 0/1 bit flipping per particle
    float colH = hash11(aGrid.x * 13.7 + 1.9);
    float spd = (2.1 + fract(colH * 7.31) * 3.4) * (uState == 2 ? 1.7 : 1.0);
    float headPos = colH * 28.0 + uTime * spd;
    float trail = 1.0 - fract((headPos - aGrid.y) / 22.0);
    float streamBoost = smoothstep(0.28, 0.96, trail);
    float isLead = smoothstep(0.92, 0.992, trail);

    float flip = floor(uTime * (1.4 + fract(colH * 11.3) * 2.2) + aMeta.y * 5.0);
    vBit = step(0.5, hash11(aMeta.y * 53.7 + flip * 1.37));

    // Crimson eye light spill onto adjacent 1/0 face particles when speaking via Fish / Voice Studio!
    float dEyeL = length(aPos.xy - vec2(-0.36, 0.19));
    float dEyeR = length(aPos.xy - vec2( 0.36, 0.19));
    float eyeSpill = exp(-min(dEyeL, dEyeR) * 5.2) * uSpeech * 0.65;

    float scanBeam = 0.0;
    if (uState == 1) {
      float beamY = sin(uTime * 1.9) * 1.08;
      scanBeam = exp(-pow((aPos.y - beamY) / 0.085, 2.0));
    }
    vScan = scanBeam;

    float basePx = (kind > 0.5) ? 9.5 : 11.4;
    gl_PointSize = clamp(aMeta.z * basePx * depthScale * stageScale * uDpr * (1.0 + isLead * 0.14 + scanBeam * 0.22), 2.8, 28.0 * uDpr);

    float depthFade = clamp(1.18 - (zCam - 3.1) * 0.35, 0.28, 1.25);
    vLum = aMeta.x * depthFade * (0.64 + 0.54 * streamBoost) + eyeSpill + scanBeam * 0.72;
    vHot = clamp(isLead * 0.72 + smoothstep(0.96, 1.48, vLum) * 0.50 + eyeSpill * 0.5 + scanBeam * 0.80, 0.0, 0.92);
  }`;

  const PT_FS = `#version 300 es
  precision highp float;
  precision highp int;
  in float vLum;
  in float vBit;
  in float vHot;
  in float vKind;
  in float vScan;

  uniform sampler2D uGlyphTex;
  uniform float uRedTheme;
  uniform int uState;
  out vec4 outColor;

  void main() {
    // Palette: Red Matrix crimson default, Emerald cyber-lock on CONTAINED
    vec3 colDeep = vec3(0.60, 0.03, 0.08);
    vec3 colMid  = vec3(1.00, 0.10, 0.20);
    vec3 colHot  = vec3(1.00, 0.80, 0.86);
    if (uState == 2) {
      colDeep = vec3(0.76, 0.02, 0.06);
      colMid  = vec3(1.00, 0.07, 0.15);
      colHot  = vec3(1.00, 0.88, 0.82);
    } else if (uState == 3) {
      colDeep = vec3(0.05, 0.45, 0.30);
      colMid  = vec3(0.09, 0.94, 0.64);
      colHot  = vec3(0.86, 1.00, 0.95);
    } else if (uRedTheme < 0.5) {
      colDeep = vec3(0.03, 0.40, 0.62);
      colMid  = vec3(0.08, 0.82, 1.00);
      colHot  = vec3(0.84, 0.98, 1.00);
    }

    if (vKind > 1.5) {
      // Sculpted glowing crimson almond eye plasma (fierce neon crimson with ruby-white iris!)
      vec2 p = gl_PointCoord * 2.0 - 1.0;
      float r2 = dot(p, p);
      if (r2 > 1.0) discard;
      float core = exp(-r2 * 4.6);
      float aura = exp(-r2 * 1.9);
      vec3 rgb = mix(colMid, colHot, clamp(core * vHot * 0.95, 0.0, 0.85));
      float a = clamp((aura * 0.26 + core * 0.46) * vLum, 0.0, 0.72);
      outColor = vec4(rgb * (1.05 + 0.75 * vLum), a);
      return;
    }

    // Crisp floating 1 & 0 sprite sampled directly from our dual-channel glyph atlas
    vec2 uv = clamp(gl_PointCoord, 0.03, 0.97);
    vec2 guv = vec2((vBit + uv.x) * 0.5, uv.y);
    vec2 g = texture(uGlyphTex, guv).rg;
    float stroke = g.r;
    float halo = g.g;
    if (stroke < 0.02 && halo < 0.03) discard;

    vec3 rgb = mix(colDeep, colMid, clamp(vLum * 0.95, 0.0, 1.0));
    rgb = mix(rgb, colHot, vHot);
    float energy = (stroke * 1.10 + halo * 0.34) * clamp(vLum, 0.10, 1.55);
    float alpha = clamp((stroke * 0.92 + halo * 0.30) * clamp(vLum, 0.14, 0.96), 0.0, 0.92);
    outColor = vec4(rgb * (0.72 + 0.70 * energy), alpha);
  }`;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      console.warn('ChappaMask shader error:', gl.getShaderInfoLog(sh));
      gl.deleteShader(sh);
      return null;
    }
    return sh;
  }

  function link(gl, vsSrc, fsSrc) {
    const vs = compile(gl, gl.VERTEX_SHADER, vsSrc);
    const fs = compile(gl, gl.FRAGMENT_SHADER, fsSrc);
    if (!vs || !fs) return null;
    const p = gl.createProgram();
    gl.attachShader(p, vs); gl.attachShader(p, fs); gl.linkProgram(p);
    gl.deleteShader(vs); gl.deleteShader(fs);
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
      console.warn('ChappaMask link error:', gl.getProgramInfoLog(p));
      return null;
    }
    return p;
  }

  function createMaskStage(canvas, opts) {
    const o = opts || {};
    const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, depth: true, premultipliedAlpha: false });
    let W = 1, H = 1, DPR = 1;
    let yaw = 0.20, pitch = -0.04, zoom = o.zoom || 1.05;
    let dragging = false, lx = 0, ly = 0, t = 0, lastDraw = 0;
    let alive = true, rafId = 0;
    let state = String(o.state || 'IDLE').toUpperCase();
    let fps = Number(o.fps || 60);
    let redTheme = o.theme !== 'agentsar';

    // Pointer state for Assimilis-style particle parting & vortex swirl
    let mouseIn = false, pmx = 0, pmy = 0, pmvx = 0, pmvy = 0;

    // Live Voice-Reactive Eye Glow state (driven by Assimilis Fish Audio / Voice Studio AnalyserNode)
    let targetSpeech = 0.0;
    let smoothSpeech = 0.0;
    let speakingFlag = false;

    const hudCanvas = o.hudCanvas || null;
    const hudCtx = hudCanvas ? hudCanvas.getContext('2d') : null;
    const matrixCanvas = o.matrixCanvas || null;
    const matrixCtx = matrixCanvas ? matrixCanvas.getContext('2d') : null;
    let matrixDrops = [], matrixCols = 0;

    // Assimilis Holo Particle Physics TypedArrays
    let N = 0;
    let hx, hy, hz, px, py, pz, vx, vy, vz;
    let posInterleaved, metaBufData, gridBufData;
    let pKind, pPhase;
    let progPt = null, vaoPt = null, bPos = null, bMeta = null, bGrid = null, texGlyph = null;

    function loadParticleCloud(list, keepPositions) {
      N = list.length;
      const oldPx = keepPositions && px ? px : null;
      const oldPy = keepPositions && py ? py : null;
      const oldPz = keepPositions && pz ? pz : null;
      hx = new Float32Array(N); hy = new Float32Array(N); hz = new Float32Array(N);
      px = new Float32Array(N); py = new Float32Array(N); pz = new Float32Array(N);
      vx = new Float32Array(N); vy = new Float32Array(N); vz = new Float32Array(N);
      pKind = new Uint8Array(N);
      pPhase = new Float32Array(N);
      posInterleaved = new Float32Array(N * 3);
      metaBufData = new Float32Array(N * 4);
      gridBufData = new Float32Array(N * 2);

      for (let i = 0; i < N; i++) {
        const pt = list[i];
        hx[i] = pt.x; hy[i] = pt.y; hz[i] = pt.z;
        if (oldPx && i < oldPx.length) {
          px[i] = oldPx[i]; py[i] = oldPy[i]; pz[i] = oldPz[i];
        } else {
          // Spawn softly at rotated home pose so first frame is crisp and immediate
          const cy = Math.cos(yaw), sy = Math.sin(yaw);
          px[i] = pt.x * cy - pt.z * sy;
          py[i] = pt.y;
          pz[i] = pt.x * sy + pt.z * cy;
        }
        pKind[i] = pt.kind | 0;
        pPhase[i] = pt.phase || 0;
        metaBufData[i * 4] = pt.lum;
        metaBufData[i * 4 + 1] = pt.phase || 0;
        metaBufData[i * 4 + 2] = pt.size || 1.0;
        metaBufData[i * 4 + 3] = pt.kind | 0;
        gridBufData[i * 2] = pt.colX || 0;
        gridBufData[i * 2 + 1] = pt.rowY || 0;
      }

      if (gl && vaoPt) {
        gl.bindVertexArray(vaoPt);
        gl.bindBuffer(gl.ARRAY_BUFFER, bPos);
        gl.bufferData(gl.ARRAY_BUFFER, posInterleaved, gl.DYNAMIC_DRAW);
        gl.bindBuffer(gl.ARRAY_BUFFER, bMeta);
        gl.bufferData(gl.ARRAY_BUFFER, metaBufData, gl.STATIC_DRAW);
        gl.bindBuffer(gl.ARRAY_BUFFER, bGrid);
        gl.bufferData(gl.ARRAY_BUFFER, gridBufData, gl.STATIC_DRAW);
        gl.bindVertexArray(null);
      }
    }

    function swirlImpulse(strength) {
      const s = strength || 0.55;
      const dir = (Math.random() < 0.5 ? 1 : -1) * s;
      for (let i = 0; i < N; i++) {
        if (pKind[i] === 2) continue;
        vx[i] += -py[i] * dir + Math.cos(pPhase[i] * 3.0) * 0.25 * s;
        vy[i] += px[i] * dir + Math.sin(pPhase[i] * 3.0) * 0.25 * s;
        vz[i] += Math.sin(pPhase[i]) * 0.35 * s;
      }
    }

    if (gl) {
      progPt = link(gl, PT_VS, PT_FS);

      const glyphCanvas = buildBinaryGlyphAtlas();
      texGlyph = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, texGlyph);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, glyphCanvas);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

      vaoPt = gl.createVertexArray();
      gl.bindVertexArray(vaoPt);
      bPos = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bPos);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

      bMeta = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bMeta);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 4, gl.FLOAT, false, 0, 0);

      bGrid = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bGrid);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);
    }

    loadParticleCloud(buildMaskParticleCloud(), false);

    function stateCode() {
      if (state === 'RECON') return 1;
      if (state === 'ALERT') return 2;
      if (state === 'CONTAINED') return 3;
      return 0;
    }

    function resize() {
      const r = canvas.getBoundingClientRect();
      DPR = Math.min(2, window.devicePixelRatio || 1);
      W = Math.max(160, Math.round(r.width || canvas.clientWidth || 500));
      H = Math.max(160, Math.round(r.height || canvas.clientHeight || 500));
      const pw = Math.round(W * DPR), ph = Math.round(H * DPR);
      if (canvas.width !== pw || canvas.height !== ph) { canvas.width = pw; canvas.height = ph; }
      if (hudCanvas && (hudCanvas.width !== pw || hudCanvas.height !== ph)) { hudCanvas.width = pw; hudCanvas.height = ph; }
      if (matrixCanvas && (matrixCanvas.width !== pw || matrixCanvas.height !== ph)) {
        matrixCanvas.width = pw; matrixCanvas.height = ph;
        matrixCols = Math.max(20, Math.floor(W / 17));
        matrixDrops = Array.from({ length: matrixCols }, (_, i) => ({
          y: ((i * 8.7) % (H / 16)),
          spd: 0.24 + ((i * 13) % 7) * 0.052,
          len: 12 + (i % 13),
          seed: i * 17 + 3
        }));
      }
    }

    // Subtle background Red Matrix 1/0 rain framing the floating 3D binary mask
    function drawMatrixRain(reduced) {
      if (!matrixCtx) return;
      matrixCtx.setTransform(DPR, 0, 0, DPR, 0, 0);
      matrixCtx.clearRect(0, 0, W, H);
      if (!redTheme) return;

      const cellW = W / Math.max(1, matrixCols);
      const cellH = 16;
      matrixCtx.font = '700 12px ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
      matrixCtx.textAlign = 'center';

      for (let c = 0; c < matrixCols; c++) {
        const d = matrixDrops[c];
        if (!reduced) {
          d.y += d.spd * (state === 'ALERT' ? 1.55 : 1.0);
          if ((d.y - d.len) * cellH > H + 20) d.y = -Math.random() * 12;
        }
        const x = c * cellW + cellW * 0.5;
        // Clear quiet center vignette so the floating 3D 1/0 mask stands out cleanly against pure void!
        const distCtr = Math.abs(x - W * 0.5) / (W * 0.5);
        const colAlpha = 0.06 + 0.72 * Math.pow(Math.min(1, Math.max(0, (distCtr - 0.16) / 0.84)), 1.3);
        if (colAlpha < 0.08) continue;

        const headRow = Math.floor(d.y);
        for (let k = 0; k < d.len; k++) {
          const row = headRow - k;
          const y = row * cellH;
          if (y < -cellH || y > H + cellH) continue;
          const bit = ((row * 31 + d.seed + (reduced ? 0 : Math.floor(t * 2))) & 1) ? '1' : '0';
          const fade = 1 - k / d.len;
          if (k === 0) {
            matrixCtx.fillStyle = `rgba(255, 196, 208, ${(0.82 * colAlpha).toFixed(2)})`;
          } else if (k < 4) {
            matrixCtx.fillStyle = `rgba(255, 34, 62, ${(0.72 * fade * colAlpha).toFixed(2)})`;
          } else {
            matrixCtx.fillStyle = `rgba(195, 14, 36, ${(0.52 * fade * colAlpha).toFixed(2)})`;
          }
          matrixCtx.fillText(bit, x, y);
        }
      }
    }

    function drawHudRings() {
      if (!hudCtx) return;
      hudCtx.setTransform(DPR, 0, 0, DPR, 0, 0);
      hudCtx.clearRect(0, 0, W, H);
      const cx = W * 0.5, cy = H * 0.5;
      const R = Math.min(W, H) * 0.375 * zoom;
      const c1 = redTheme
        ? (state === 'CONTAINED' ? '#10b981' : '#ff243b')
        : (state === 'ALERT' ? '#e81c2e' : (state === 'CONTAINED' ? '#10b981' : '#08b6e8'));
      const c2 = redTheme ? '#ff6b7d' : (state === 'ALERT' ? '#08b6e8' : '#e81c2e');
      const speechBoost = 1.0 + smoothSpeech * 0.045;

      [
        { r: R * 1.03 * speechBoost, w: 1.35, col: c1 + '58', dash: [44, 16, 10, 16], spd: 0.18 },
        { r: R * 1.15, w: 1.0, col: c2 + '3c', dash: [22, 12], spd: -0.12 },
        { r: R * 1.26, w: 0.85, col: c1 + '2a', dash: [6, 10], spd: 0.08 }
      ].forEach((rg, idx) => {
        hudCtx.save();
        hudCtx.translate(cx, cy);
        hudCtx.rotate(t * rg.spd + idx * 0.9);
        hudCtx.strokeStyle = rg.col;
        hudCtx.lineWidth = rg.w;
        hudCtx.setLineDash(rg.dash);
        hudCtx.beginPath();
        hudCtx.arc(0, 0, rg.r, 0, TAU);
        hudCtx.stroke();
        hudCtx.restore();
      });
      hudCtx.setLineDash([]);
    }

    // Assimilis Holo Particle Physics Step: spring-to-3D-mask + curl flow + cursor vortex + voice acoustic wave
    function stepParticles(dt, reduced) {
      const cy = Math.cos(yaw), sy = Math.sin(yaw);
      const cp = Math.cos(pitch), sp = Math.sin(pitch);
      const bob = reduced ? 0 : Math.sin(t * 1.35) * 0.032;

      // Smooth voice envelope (fast crisp attack on syllables, smooth release)
      let desiredSpeech = targetSpeech;
      if (speakingFlag && desiredSpeech < 0.04) {
        // Natural syllabic modulation fallback when Web Speech API lacks AnalyserNode
        const syll = 0.52 + 0.34 * Math.sin(t * 14.5) + 0.22 * Math.sin(t * 23.0 + 1.2) + 0.12 * Math.cos(t * 8.2);
        desiredSpeech = Math.max(0.18, Math.min(1.0, syll));
      }
      const attack = desiredSpeech > smoothSpeech ? 0.42 : 0.14;
      smoothSpeech += (desiredSpeech - smoothSpeech) * attack;

      const dragFace = Math.exp(-7.6 * dt);
      const dragScout = Math.exp(-2.3 * dt);
      const spgFace = 30.0;
      const spgEye = 44.0;
      const hoverRad = 0.46, hoverRad2 = hoverRad * hoverRad;
      const mvSpd = Math.hypot(pmvx, pmvy);
      const f1 = 2.0, flowT = t * 0.72;

      for (let i = 0; i < N; i++) {
        const k = pKind[i];
        const x0 = hx[i], y0 = hy[i] + bob, z0 = hz[i];
        // Rotate 3D target by live camera yaw & pitch
        const rx1 = x0 * cy - z0 * sy;
        const rz1 = x0 * sy + z0 * cy;
        const ry2 = y0 * cp - rz1 * sp;
        const rz2 = y0 * sp + rz1 * cp;

        if (reduced) {
          px[i] = rx1; py[i] = ry2; pz[i] = rz2;
          posInterleaved[i * 3] = rx1;
          posInterleaved[i * 3 + 1] = ry2;
          posInterleaved[i * 3 + 2] = rz2;
          continue;
        }

        const x = px[i], y = py[i], z = pz[i];
        const ph = pPhase[i];

        if (k === 1) {
          // Assimilis-style murmuration scout `1`/`0` particle drifting in 3D curl flow around the mask
          const r = Math.hypot(x, y, z) || 0.001;
          const targetR = 1.48 + 0.24 * Math.sin(t * 0.9 + ph);
          const err = (targetR - r) / r;
          let ax = x * err * 2.6 + (Math.sin(y * f1 + flowT) * Math.cos(z * f1 - flowT * 0.7) - z * 0.48) * 0.95;
          let ay = y * err * 2.6 + (Math.sin(z * f1 - flowT * 0.8) * Math.cos(x * f1 + flowT * 0.6) + Math.sin(t * 0.6 + ph) * 0.28) * 0.95;
          let az = z * err * 2.6 + (Math.sin(x * f1 + flowT * 0.9) * Math.cos(y * f1 - flowT * 0.5) + x * 0.48) * 0.95;
          if (mouseIn && !dragging) {
            const dx = x - pmx, dy = y - pmy, d2 = dx * dx + dy * dy;
            if (d2 < 0.55) {
              const d = Math.sqrt(d2) + 1e-4, f2 = (1 - d / 0.74) ** 2;
              ax += (dx / d) * 6.5 * f2 - (dy / d) * 4.5 * f2;
              ay += (dy / d) * 6.5 * f2 + (dx / d) * 4.5 * f2;
            }
          }
          vx[i] = (vx[i] + ax * dt) * dragScout;
          vy[i] = (vy[i] + ay * dt) * dragScout;
          vz[i] = (vz[i] + az * dt) * dragScout;
          px[i] = x + vx[i] * dt;
          py[i] = y + vy[i] * dt;
          pz[i] = z + vz[i] * dt;
        } else if (k === 2) {
          // Voice-reactive 3D glowing eye core particle (locked smoothly inside socket, vibrates with speech)
          const vib = smoothSpeech * 0.022;
          const tx = rx1 + Math.cos(t * 16.0 + ph) * vib;
          const ty = ry2 + Math.sin(t * 18.0 + ph) * vib * 0.5;
          const tz = rz2 + smoothSpeech * 0.035;
          vx[i] = (vx[i] + (tx - x) * spgEye * dt) * dragFace;
          vy[i] = (vy[i] + (ty - y) * spgEye * dt) * dragFace;
          vz[i] = (vz[i] + (tz - z) * spgEye * dt) * dragFace;
          px[i] = x + vx[i] * dt;
          py[i] = y + vy[i] * dt;
          pz[i] = z + vz[i] * dt;
        } else {
          // Primary floating 3D `1` & `0` face particle: springs to 3D mask contour + gentle living hover float!
          const floatAmp = 0.015 + (state === 'ALERT' ? 0.010 : 0.0);
          let tx = rx1 + Math.sin(t * 1.9 + ph + y0 * 3.2) * floatAmp;
          let ty = ry2 + Math.cos(t * 1.6 + ph + x0 * 3.2) * floatAmp;
          let tz = rz2 + Math.sin(t * 1.4 + ph * 1.7) * floatAmp * 1.3;

          // Subtle acoustic pressure ripple radiating outward when speaking via Fish / Voice Studio!
          if (smoothSpeech > 0.02) {
            const rad = Math.hypot(x0, y0) + 0.001;
            const wave = Math.sin(rad * 10.5 - t * 14.0) * smoothSpeech * 0.038;
            tx += (x0 / rad) * wave * 0.45;
            ty += (y0 / rad) * wave * 0.45;
            tz += wave;
          }

          let ax = (tx - x) * spgFace;
          let ay = (ty - y) * spgFace;
          let az = (tz - z) * spgFace;

          // Assimilis Holo Engine pointer parting & vortex swirl!
          if (mouseIn && !dragging) {
            const dx = x - pmx, dy = y - pmy, d2 = dx * dx + dy * dy;
            if (d2 < hoverRad2) {
              const d = Math.sqrt(d2) + 1e-4;
              const fall = 1 - d / hoverRad;
              const f2 = fall * fall;
              const part = 5.4 * f2 * (d < 0.25 ? 1.35 : 0.7);
              const cross = dx * pmvy - dy * pmvx;
              const sgn = Math.abs(cross) > 0.01 ? (cross >= 0 ? 1 : -1) : 1;
              const swirl = 3.8 * f2 * (0.65 + Math.min(1.5, mvSpd * 0.2)) * sgn;
              ax += (dx / d) * part + (-dy / d) * swirl + pmvx * 0.75 * f2;
              ay += (dy / d) * part + (dx / d) * swirl + pmvy * 0.75 * f2;
              az += (0.45 - d) * 2.4 * f2;
            }
          }

          vx[i] = (vx[i] + ax * dt) * dragFace;
          vy[i] = (vy[i] + ay * dt) * dragFace;
          vz[i] = (vz[i] + az * dt) * dragFace;
          px[i] = x + vx[i] * dt;
          py[i] = y + vy[i] * dt;
          pz[i] = z + vz[i] * dt;
        }

        posInterleaved[i * 3] = px[i];
        posInterleaved[i * 3 + 1] = py[i];
        posInterleaved[i * 3 + 2] = pz[i];
      }
      pmvx *= Math.exp(-9 * dt);
      pmvy *= Math.exp(-9 * dt);
    }

    let paused = false;

    function render(now) {
      if (!alive) return;
      rafId = requestAnimationFrame(render);
      if (paused || document.hidden) return;
      const reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      const minInterval = fps <= 12 ? 80 : 14;
      if (now - lastDraw < minInterval) return;
      const dt = lastDraw ? Math.min(0.05, Math.max(0.008, (now - lastDraw) / 1000)) : 0.016;
      lastDraw = now;

      resize();
      if (!reduced) {
        t += fps <= 12 ? 0.065 : dt;
        if (!dragging) yaw = 0.28 * Math.sin(t * 0.58);
      }

      drawMatrixRain(reduced);
      stepParticles(dt, reduced);

      if (gl && progPt && vaoPt && N > 0) {
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        // Upload live floating particle positions from Assimilis physics engine
        gl.bindBuffer(gl.ARRAY_BUFFER, bPos);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, posInterleaved);

        // Pure luminous additive holographic particles (zero solid background shell!)
        gl.disable(gl.DEPTH_TEST);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE);

        gl.useProgram(progPt);
        gl.uniform2f(gl.getUniformLocation(progPt, 'uRes'), W, H);
        gl.uniform1f(gl.getUniformLocation(progPt, 'uTime'), t);
        gl.uniform1f(gl.getUniformLocation(progPt, 'uZoom'), zoom);
        gl.uniform1f(gl.getUniformLocation(progPt, 'uDpr'), DPR);
        gl.uniform1f(gl.getUniformLocation(progPt, 'uSpeech'), smoothSpeech);
        gl.uniform1i(gl.getUniformLocation(progPt, 'uState'), stateCode());
        gl.uniform1f(gl.getUniformLocation(progPt, 'uRedTheme'), redTheme ? 1.0 : 0.0);

        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texGlyph);
        gl.uniform1i(gl.getUniformLocation(progPt, 'uGlyphTex'), 0);

        gl.bindVertexArray(vaoPt);
        gl.drawArrays(gl.POINTS, 0, N);
        gl.bindVertexArray(null);
      }

      drawHudRings();
    }

    canvas.addEventListener('pointerdown', (e) => {
      dragging = true; lx = e.clientX; ly = e.clientY;
    });
    canvas.addEventListener('pointerleave', () => { mouseIn = false; });
    window.addEventListener('pointermove', (e) => {
      const r = canvas.getBoundingClientRect();
      if (dragging) {
        yaw += (e.clientX - lx) * 0.009;
        pitch = Math.max(-0.75, Math.min(0.75, pitch + (e.clientY - ly) * 0.008));
        lx = e.clientX; ly = e.clientY;
        return;
      }
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) {
        const aspect = r.width / Math.max(1, r.height);
        const nx = ((e.clientX - r.left) / Math.max(1, r.width) * 2 - 1) * aspect * (1.6 / zoom);
        const ny = -((e.clientY - r.top) / Math.max(1, r.height) * 2 - 1) * (1.6 / zoom);
        if (mouseIn) {
          pmvx = Math.max(-12, Math.min(12, (nx - pmx) * 32));
          pmvy = Math.max(-12, Math.min(12, (ny - pmy) * 32));
        }
        pmx = nx; pmy = ny; mouseIn = true;
      } else {
        mouseIn = false;
      }
    });
    window.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoom = Math.max(0.68, Math.min(1.65, zoom * (e.deltaY > 0 ? 0.93 : 1.07)));
    }, { passive: false });

    rafId = requestAnimationFrame(render);

    return {
      setState(next) {
        const n = String(next || 'IDLE').toUpperCase();
        if (n !== state) swirlImpulse(0.65);
        state = n;
      },
      setSpeechLevel(lvl) {
        targetSpeech = Math.max(0, Math.min(1.5, Number(lvl) || 0));
      },
      setSpeaking(active) {
        speakingFlag = !!active;
        if (!active) targetSpeech = 0;
      },
      setFps(next) { fps = Number(next) <= 12 ? 12 : 60; },
      setPaused(flag) { paused = !!flag; },
      setTheme(next) { redTheme = next !== 'agentsar'; },
      loadObjMesh(objText) {
        const pts = parseObjToParticles(objText);
        if (pts) { loadParticleCloud(pts, true); swirlImpulse(0.9); }
        return !!pts;
      },
      destroy() { alive = false; if (rafId) cancelAnimationFrame(rafId); }
    };
  }

  root.ChappaMask = { createMaskStage, parseObjText: parseObjToParticles };
})(typeof window !== 'undefined' ? window : globalThis);
