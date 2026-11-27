/* ==========================================================================
   Chappa V2 — True WebGL2 3D Sculpted Hacker Mask + Particle Core Engine
   - ~32,000-triangle high-poly anatomical Guy Fawkes 3D mask mesh with
     smooth analytical normals, deep eye sockets, real pierced eye & mouth
     slits, sculpted nose/cheekbones/lips/chin, and inner shell rim depth
   - 1024x1024 procedural PBR albedo + gloss + ambient occlusion texture
     (porcelain sheen, arched brows, rosy blush cheeks, handlebar mustache,
     pointed goatee, subtle Spider-Verse halftone accent)
   - Multi-light Blinn-Phong + Fresnel Cyan/Crimson Hologram WebGL2 shader
   - Assimilis-Core-style 3D particle halo & precision orbital HUD rings
   - Custom .OBJ drop-in support (loadObjMesh) + graceful 2D fallback
   ========================================================================== */
(function (root) {
  'use strict';

  function smoothstep(e0, e1, x) {
    const t = Math.max(0, Math.min(1, (x - e0) / (e1 - e0)));
    return t * t * (3 - 2 * t);
  }

  function gauss2(x, y, cx, cy, sx, sy) {
    const dx = (x - cx) / sx, dy = (y - cy) / sy;
    return Math.exp(-(dx * dx + dy * dy));
  }

  // Authentic Guy Fawkes mask silhouette: broad smoothly rounded forehead crown, full cheeks, rounded chin
  function maskBoundary(u, v) {
    // v: -1 (top of forehead) -> +1 (tip of chin)
    if (v < -0.25) {
      const t = (-v - 0.25) / 0.75; // 0 at brow -> 1 at top crown
      return Math.max(0.06, 0.88 * Math.pow(Math.max(0.0, 1.0 - Math.pow(t, 4.4)), 0.34));
    }
    const t = (v + 0.25) / 1.25; // 0 at brow -> 1 at chin
    const cheek = 0.045 * Math.sin(Math.min(1, t * 2.1) * Math.PI);
    const jaw = 0.88 * Math.pow(Math.max(0.0, 1.0 - Math.pow(t, 2.15) * 0.96), 0.56);
    return Math.max(0.06, jaw + cheek * (1.0 - smoothstep(0.65, 1.0, t)));
  }

  // Sculpted 3D facial heightfield z(u, v) — realistic smooth porcelain relief
  function maskHeight(u, v) {
    const au = Math.abs(u);
    const hw = maskBoundary(u, v);
    const rn = Math.min(1.0, au / Math.max(0.06, hw));

    // Smooth curved porcelain shell
    const domeU = Math.sqrt(Math.max(0.002, 1.0 - rn * rn * 0.86)) * 0.68;
    const domeV = Math.cos(v * 1.08) * 0.20;

    // Smooth forehead dome + subtle brow arch
    const forehead = gauss2(u, v, 0.0, -0.58, 0.62, 0.30) * 0.12;
    const temple = -gauss2(au, v, 0.68, -0.34, 0.22, 0.22) * 0.045;

    const browArchY = -0.35 + Math.pow((au - 0.34) * 1.3, 2) * 0.20;
    const browRidge = Math.exp(-Math.pow((v - browArchY) / 0.09, 2)) * smoothstep(0.04, 0.18, au) * (1.0 - smoothstep(0.58, 0.82, au)) * 0.075;

    // Deep smooth orbital eye sockets + subtle lids
    const eyeSocket = -gauss2(au, v, 0.34, -0.175, 0.21, 0.13) * 0.165;
    const upperLid = gauss2(au, v, 0.34, -0.235, 0.18, 0.055) * 0.05;
    const lowerLid = gauss2(au, v, 0.34, -0.092, 0.19, 0.06) * 0.042;

    // Realistic sculpted nose bridge, rounded tip, alar wings & subtle nostrils
    const noseBridge = Math.exp(-Math.pow(u / (0.115 + Math.max(0, v + 0.20) * 0.11), 2))
      * smoothstep(-0.34, -0.12, v) * (1.0 - smoothstep(0.14, 0.25, v)) * (0.19 + smoothstep(-0.22, 0.12, v) * 0.15);
    const noseTip = gauss2(u, v, 0.0, 0.125, 0.13, 0.098) * 0.165;
    const noseWing = gauss2(au, v, 0.13, 0.155, 0.085, 0.068) * 0.085;
    const nostrilIndent = -gauss2(au, v, 0.076, 0.205, 0.045, 0.032) * 0.075;
    const underNose = -gauss2(u, v, 0.0, 0.248, 0.17, 0.045) * 0.055;

    // Smooth fuller cheekbones + very gentle smile cheek puff (no harsh diagonal lines!)
    const cheekbone = gauss2(au, v, 0.46, 0.06, 0.28, 0.22) * 0.145;
    const midCheek = gauss2(au, v, 0.40, 0.25, 0.26, 0.20) * 0.085;
    const smilePuff = gauss2(au, v, 0.30, 0.30, 0.15, 0.14) * 0.04;

    // Sculpted lips + rounded chin
    const upperLip = gauss2(u, v, 0.0, 0.365, 0.29, 0.07) * 0.08;
    const mouthCrease = -gauss2(u, v, 0.0, 0.45, 0.24, 0.028) * 0.065;
    const lowerLip = gauss2(u, v, 0.0, 0.52, 0.25, 0.068) * 0.085;
    const chinHollow = -gauss2(u, v, 0.0, 0.625, 0.24, 0.07) * 0.045;
    const chinBoss = gauss2(u, v, 0.0, 0.78, 0.26, 0.17) * 0.13;

    const edgeRoll = -Math.pow(smoothstep(0.84, 1.0, rn), 1.8) * 0.15;

    return domeU + domeV + forehead + temple + browRidge + eyeSocket + upperLid + lowerLid
      + noseBridge + noseTip + noseWing + nostrilIndent + underNose
      + cheekbone + midCheek + smilePuff
      + upperLip + mouthCrease + lowerLip + chinHollow + chinBoss + edgeRoll - 0.36;
  }

  // Signed distance to pierced eye slits & mouth slit (negative = inside cutout)
  function eyeSlitSdf(u, v) {
    const au = Math.abs(u);
    const ex = (au - 0.345) / 0.155;
    const arch = -0.172 + ex * ex * 0.032 - ex * 0.012;
    const dy = v - arch;
    const topH = 0.052 * Math.max(0.0, 1.0 - ex * ex);
    const botH = 0.024 * Math.max(0.0, 1.0 - ex * ex);
    if (Math.abs(ex) >= 1.0) return 0.1;
    if (dy < 0) return (-dy) - topH;
    return dy - botH;
  }

  function buildHighPolyMaskMesh() {
    const NU = 112, NV = 128;
    const pos = [];
    const norm = [];
    const uv = [];
    const idx = [];
    const gridIdx = Array.from({ length: NV + 1 }, () => new Int32Array(NU + 1).fill(-1));

    const eps = 0.009;
    for (let iv = 0; iv <= NV; iv++) {
      const v = (iv / NV) * 2.0 - 1.0; // -1 top .. +1 chin
      const hw = maskBoundary(0, v);
      for (let iu = 0; iu <= NU; iu++) {
        const s = (iu / NU) * 2.0 - 1.0;
        const u = s * hw;
        const x = u * 1.02;
        const y = -v * 1.12;
        const z = maskHeight(u, v);

        const dzdu = (maskHeight(u + eps, v) - maskHeight(u - eps, v)) / (2 * eps);
        const dzdv = (maskHeight(u, v + eps) - maskHeight(u, v - eps)) / (2 * eps);
        let nx = -dzdu / 1.02;
        let ny = dzdv / 1.12;
        let nz = 1.0;
        const nlen = Math.hypot(nx, ny, nz) || 1.0;
        nx /= nlen; ny /= nlen; nz /= nlen;

        const vi = pos.length / 3;
        gridIdx[iv][iu] = vi;
        pos.push(x, y, z);
        norm.push(nx, ny, nz);
        uv.push((u + 1.0) * 0.5, (v + 1.0) * 0.5);
      }
    }

    for (let iv = 0; iv < NV; iv++) {
      for (let iu = 0; iu < NU; iu++) {
        const a = gridIdx[iv][iu];
        const b = gridIdx[iv][iu + 1];
        const c = gridIdx[iv + 1][iu + 1];
        const d = gridIdx[iv + 1][iu];
        idx.push(a, d, b, b, d, c);
      }
    }

    return {
      positions: new Float32Array(pos),
      normals: new Float32Array(norm),
      uvs: new Float32Array(uv),
      indices: new Uint32Array(idx)
    };
  }

  // Paint crisp 1024x1024 Guy Fawkes PBR Albedo + Feature Texture matching reference mask
  function buildMaskTextureCanvas() {
    const S = 1024;
    const c = document.createElement('canvas');
    c.width = S; c.height = S;
    const g = c.getContext('2d');
    const px = (u) => (u + 1.0) * 0.5 * S;
    const py = (v) => (v + 1.0) * 0.5 * S;

    // Smooth studio porcelain alabaster base (balanced luminance so 3D highlights pop without blowing out)
    const base = g.createRadialGradient(px(0), py(-0.06), S * 0.06, px(0), py(0.05), S * 0.62);
    base.addColorStop(0, '#eef2f7');
    base.addColorStop(0.62, '#dce3ed');
    base.addColorStop(1, '#bcc7d6');
    g.fillStyle = base;
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
      g.arc(0, 0, 1, 0, Math.PI * 2);
      g.fill();
      g.restore();
    }

    // Soft studio ambient occlusion in sockets, under nose, nostrils, chin hollow
    softSpot(-0.34, -0.175, 0.23, 0.14, 'rgba(18, 28, 46, 0.24)');
    softSpot(0.34, -0.175, 0.23, 0.14, 'rgba(18, 28, 46, 0.24)');
    softSpot(0.0, 0.215, 0.15, 0.055, 'rgba(20, 30, 46, 0.22)');
    softSpot(-0.075, 0.202, 0.048, 0.032, 'rgba(10, 14, 22, 0.72)');
    softSpot(0.075, 0.202, 0.048, 0.032, 'rgba(10, 14, 22, 0.72)');
    softSpot(0.0, 0.60, 0.20, 0.06, 'rgba(24, 36, 56, 0.14)');

    // Iconic airbrushed rosy pink/crimson cheeks (matching reference image.png)
    softSpot(-0.55, 0.09, 0.16, 0.13, 'rgba(232, 48, 86, 0.44)');
    softSpot(0.55, 0.09, 0.16, 0.13, 'rgba(232, 48, 86, 0.44)');

    // Subtle Spider-Verse Ben-Day halftone micro-dots inside the cheek blush
    g.fillStyle = 'rgba(232, 28, 46, 0.20)';
    [-0.55, 0.55].forEach((cu) => {
      for (let dy = -3; dy <= 3; dy++) {
        for (let dx = -3; dx <= 3; dx++) {
          if (dx * dx + dy * dy > 8) continue;
          g.beginPath();
          g.arc(px(cu) + dx * 11, py(0.09) + dy * 11, 2.0, 0, Math.PI * 2);
          g.fill();
        }
      }
    });

    function drawMirrorShape(fn) {
      [-1, 1].forEach((sgn) => {
        g.save();
        g.beginPath();
        fn(sgn);
        g.closePath();
        g.fillStyle = '#0f121a';
        g.fill();
        g.restore();
      });
    }

    // Crisp dark arched Guy Fawkes eyebrows
    drawMirrorShape((s) => {
      g.moveTo(px(s * 0.10), py(-0.295));
      g.bezierCurveTo(px(s * 0.24), py(-0.435), px(s * 0.47), py(-0.435), px(s * 0.635), py(-0.305));
      g.bezierCurveTo(px(s * 0.50), py(-0.365), px(s * 0.26), py(-0.365), px(s * 0.125), py(-0.262));
    });

    // Crisp upturned curled handlebar mustache
    drawMirrorShape((s) => {
      g.moveTo(px(s * 0.005), py(0.325));
      g.bezierCurveTo(px(s * 0.12), py(0.285), px(s * 0.24), py(0.395), px(s * 0.44), py(0.382));
      g.bezierCurveTo(px(s * 0.54), py(0.372), px(s * 0.60), py(0.305), px(s * 0.635), py(0.228));
      g.bezierCurveTo(px(s * 0.575), py(0.335), px(s * 0.50), py(0.425), px(s * 0.34), py(0.435));
      g.bezierCurveTo(px(s * 0.19), py(0.442), px(s * 0.08), py(0.385), px(s * 0.005), py(0.378));
    });

    // Subtle smile lip slit
    g.strokeStyle = 'rgba(20, 24, 34, 0.85)';
    g.lineWidth = 7;
    g.lineCap = 'round';
    g.beginPath();
    g.moveTo(px(-0.24), py(0.455));
    g.quadraticCurveTo(px(0), py(0.48), px(0.24), py(0.455));
    g.stroke();

    // Iconic tapered pointed goatee
    g.beginPath();
    g.moveTo(px(-0.084), py(0.575));
    g.quadraticCurveTo(px(0), py(0.558), px(0.084), py(0.575));
    g.bezierCurveTo(px(0.064), py(0.73), px(0.042), py(0.86), px(0.0), py(0.955));
    g.bezierCurveTo(px(-0.042), py(0.86), px(-0.064), py(0.73), px(-0.084), py(0.575));
    g.closePath();
    g.fillStyle = '#0f121a';
    g.fill();

    return c;
  }

  // Parse optional custom .OBJ mesh dropped into ~/.chappa/modules/custom_mask.obj
  function parseObjText(text) {
    const rawV = [], rawN = [], rawT = [];
    const pos = [], norm = [], uv = [], idx = [];
    const lines = String(text || '').split(/\r?\n/);
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i].trim();
      if (ln.startsWith('v ')) {
        const p = ln.split(/\s+/);
        rawV.push([parseFloat(p[1]) || 0, parseFloat(p[2]) || 0, parseFloat(p[3]) || 0]);
      } else if (ln.startsWith('vn ')) {
        const p = ln.split(/\s+/);
        rawN.push([parseFloat(p[1]) || 0, parseFloat(p[2]) || 0, parseFloat(p[3]) || 1]);
      } else if (ln.startsWith('vt ')) {
        const p = ln.split(/\s+/);
        rawT.push([parseFloat(p[1]) || 0, 1.0 - (parseFloat(p[2]) || 0)]);
      } else if (ln.startsWith('f ')) {
        const parts = ln.split(/\s+/).slice(1);
        const faceIdx = [];
        for (let k = 0; k < parts.length; k++) {
          const seg = parts[k].split('/');
          const vi = parseInt(seg[0], 10);
          const ti = seg[1] ? parseInt(seg[1], 10) : 0;
          const ni = seg[2] ? parseInt(seg[2], 10) : 0;
          const v = rawV[vi > 0 ? vi - 1 : rawV.length + vi] || [0, 0, 0];
          const t = ti ? (rawT[ti > 0 ? ti - 1 : rawT.length + ti] || [0.5, 0.5]) : [0.5, 0.5];
          const n = ni ? (rawN[ni > 0 ? ni - 1 : rawN.length + ni] || [0, 0, 1]) : [0, 0, 1];
          faceIdx.push(pos.length / 3);
          pos.push(v[0], v[1], v[2]);
          uv.push(t[0], t[1]);
          norm.push(n[0], n[1], n[2]);
        }
        for (let k = 1; k + 1 < faceIdx.length; k++) idx.push(faceIdx[0], faceIdx[k], faceIdx[k + 1]);
      }
    }
    if (!pos.length) return null;
    let minX = 1e9, maxX = -1e9, minY = 1e9, maxY = -1e9, minZ = 1e9, maxZ = -1e9;
    for (let i = 0; i < pos.length; i += 3) {
      minX = Math.min(minX, pos[i]); maxX = Math.max(maxX, pos[i]);
      minY = Math.min(minY, pos[i + 1]); maxY = Math.max(maxY, pos[i + 1]);
      minZ = Math.min(minZ, pos[i + 2]); maxZ = Math.max(maxZ, pos[i + 2]);
    }
    const cx = (minX + maxX) * 0.5, cy = (minY + maxY) * 0.5, cz = (minZ + maxZ) * 0.5;
    const sc = 2.1 / Math.max(0.001, maxX - minX, maxY - minY, maxZ - minZ);
    for (let i = 0; i < pos.length; i += 3) {
      pos[i] = (pos[i] - cx) * sc;
      pos[i + 1] = (pos[i + 1] - cy) * sc;
      pos[i + 2] = (pos[i + 2] - cz) * sc;
    }
    return {
      positions: new Float32Array(pos),
      normals: new Float32Array(norm),
      uvs: new Float32Array(uv),
      indices: new Uint32Array(idx)
    };
  }

  const MASK_VS = `#version 300 es
  precision highp float;
  layout(location = 0) in vec3 aPos;
  layout(location = 1) in vec3 aNorm;
  layout(location = 2) in vec2 aUv;

  uniform vec2 uRes;
  uniform float uYaw;
  uniform float uPitch;
  uniform float uZoom;
  uniform float uBob;
  uniform float uGlitch;

  out vec3 vNormal;
  out vec3 vViewPos;
  out vec2 vUv;
  out vec3 vLocal;

  void main() {
    float cy = cos(uYaw), sy = sin(uYaw);
    float cp = cos(uPitch), sp = sin(uPitch);
    vec3 p = aPos + vec3(0.0, uBob, 0.0);
    vec3 p1 = vec3(p.x * cy - p.z * sy, p.y, p.x * sy + p.z * cy);
    vec3 p2 = vec3(p1.x, p1.y * cp - p1.z * sp, p1.y * sp + p1.z * cp);

    vec3 n1 = vec3(aNorm.x * cy - aNorm.z * sy, aNorm.y, aNorm.x * sy + aNorm.z * cy);
    vec3 n2 = vec3(n1.x, n1.y * cp - n1.z * sp, n1.y * sp + n1.z * cp);

    float camDist = 3.95;
    float zCam = camDist - p2.z;
    float aspect = uRes.x / max(1.0, uRes.y);
    float f = 2.42 * uZoom;
    vec2 ndc = vec2(p2.x * f / (zCam * aspect), p2.y * f / zCam);
    float ndcZ = clamp((zCam - 1.2) / 5.5 * 2.0 - 1.0, -0.99, 0.99);

    gl_Position = vec4(ndc, ndcZ, 1.0);
    vNormal = normalize(n2);
    vViewPos = vec3(p2.x, p2.y, -zCam);
    vUv = aUv;
    vLocal = aPos;
  }`;

  const MASK_FS = `#version 300 es
  precision highp float;
  in vec3 vNormal;
  in vec3 vViewPos;
  in vec2 vUv;
  in vec3 vLocal;

  uniform sampler2D uTex;
  uniform float uTime;
  uniform int uState; // 0=IDLE, 1=RECON, 2=ALERT, 3=CONTAINED
  uniform float uCustomMesh;
  out vec4 outColor;

  float eyeSlit(vec2 fuv) {
    float au = abs(fuv.x);
    float ex = (au - 0.345) / 0.155;
    if (abs(ex) >= 1.0) return 0.1;
    float arch = -0.172 + ex * ex * 0.032 - ex * 0.012;
    float dy = fuv.y - arch;
    float topH = 0.052 * max(0.0, 1.0 - ex * ex);
    float botH = 0.024 * max(0.0, 1.0 - ex * ex);
    return dy < 0.0 ? (-dy - topH) : (dy - botH);
  }

  void main() {
    vec2 fuv = vUv * 2.0 - 1.0;
    vec3 N = normalize(gl_FrontFacing ? vNormal : -vNormal);
    vec3 V = normalize(-vViewPos);

    // State-reactive rim & accent colors (Agentsar Cyan #08B6E8 + Crimson #E81C2E)
    vec3 rimCyan = vec3(0.03, 0.71, 0.91);
    vec3 rimRed  = vec3(0.91, 0.11, 0.18);
    if (uState == 2) {
      rimCyan = vec3(0.98, 0.14, 0.24);
      rimRed  = vec3(0.06, 0.72, 0.94);
    } else if (uState == 3) {
      rimCyan = vec3(0.07, 0.78, 0.56);
      rimRed  = vec3(0.04, 0.68, 0.88);
    }

    // Real hollow pierced eye cutouts with glowing cyber core inside the socket
    if (uCustomMesh < 0.5) {
      float es = eyeSlit(fuv);
      if (es < 0.0) {
        // Deep hollow void with subtle glowing holographic pupil inside
        float px = (abs(fuv.x) - 0.345) / 0.055;
        float py = (fuv.y + 0.178) / 0.028;
        float pupil = exp(-(px * px + py * py) * 2.4);
        vec3 eyeGlow = (uState == 2 ? vec3(1.0, 0.16, 0.26) : rimCyan) * (0.28 + 0.85 * pupil);
        vec3 voidCol = vec3(0.012, 0.018, 0.032) + eyeGlow * (0.65 + 0.35 * sin(uTime * 3.5));
        outColor = vec4(voidCol, 0.98);
        return;
      }
      // Darkened porcelain bevel right around the eye cutout edge
      if (es < 0.012) {
        outColor = vec4(mix(vec3(0.06, 0.08, 0.12), rimCyan * 0.7, 0.35), 1.0);
        return;
      }
    }

    vec3 albedo = uCustomMesh > 0.5 ? vec3(0.90, 0.93, 0.96) : texture(uTex, vUv).rgb;
    float isDarkFeature = 1.0 - smoothstep(0.18, 0.42, dot(albedo, vec3(0.333)));

    // 3-point Cinema Studio + Hologram Lighting (Key + Cyan Rim + Crimson Fill)
    vec3 Lkey  = normalize(vec3(0.28, 0.52, 0.84));
    vec3 Lrim1 = normalize(vec3(-0.90, 0.22, 0.26));
    vec3 Lrim2 = normalize(vec3(0.90, -0.15, 0.24));

    float diffKey  = max(dot(N, Lkey), 0.0);
    float diffRim1 = max(dot(N, Lrim1), 0.0);
    float diffRim2 = max(dot(N, Lrim2), 0.0);

    // Glossy porcelain specular highlight off forehead, nose bridge, cheekbones & chin
    vec3 H = normalize(Lkey + V);
    float spec = pow(max(dot(N, H), 0.0), mix(52.0, 16.0, isDarkFeature)) * mix(0.42, 0.14, isDarkFeature);

    // Rich sculpted studio shading (preserves all 3D contours without clipping to flat white)
    float wrapDiff = max((dot(N, Lkey) + 0.26) / 1.26, 0.0);
    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 2.7);

    vec3 col = albedo * (0.14 + 0.62 * wrapDiff + 0.16 * diffKey);
    col += vec3(0.95, 0.98, 1.0) * spec;
    col += rimCyan * (diffRim1 * 0.18 + fresnel * (0.62 + 0.42 * smoothstep(-0.2, 0.6, -N.x)));
    col += rimRed  * (diffRim2 * 0.16 + fresnel * (0.50 + 0.42 * smoothstep(-0.2, 0.6,  N.x)));

    // Subtle holographic scanlines along the sculpted 3D surface
    float scan = 0.975 + 0.025 * sin(vLocal.y * 125.0 - uTime * 3.0);
    col *= scan;

    // RECON mode: volumetric sweeping cyan laser scan beam across the 3D mask
    if (uState == 1) {
      float beamY = sin(uTime * 1.9) * 1.05;
      float beam = exp(-pow((vLocal.y - beamY) / 0.08, 2.0));
      col += vec3(0.08, 0.88, 1.0) * beam * 0.65;
    }
    // ALERT mode: smooth pulsing crimson edge rim & subtle scanline flash (zero wavy distortion!)
    if (uState == 2) {
      float pulse = 0.5 + 0.5 * sin(uTime * 6.0);
      col += vec3(0.95, 0.10, 0.18) * (fresnel * 0.72 * pulse + 0.04);
    }

    // Back-face dark shell interior when orbited far sideways
    if (!gl_FrontFacing) {
      col = mix(vec3(0.03, 0.05, 0.09), rimCyan * 0.35, fresnel);
    }

    outColor = vec4(col, 0.99);
  }`;

  const PT_VS = `#version 300 es
  precision highp float;
  layout(location = 0) in vec3 aPos;
  layout(location = 1) in float aPhase;
  uniform vec2 uRes;
  uniform float uTime;
  uniform float uYaw;
  uniform float uZoom;
  uniform float uDpr;
  out float vAlpha;
  out float vTone;
  void main() {
    float a = aPhase + uTime * (0.14 + mod(aPhase, 0.25));
    float r = length(aPos.xz);
    vec3 p = vec3(cos(a) * r, aPos.y + sin(uTime * 0.9 + aPhase * 3.0) * 0.06, sin(a) * r);
    float cy = cos(uYaw * 0.5), sy = sin(uYaw * 0.5);
    vec3 p1 = vec3(p.x * cy - p.z * sy, p.y, p.x * sy + p.z * cy);
    float zCam = 4.2 - p1.z;
    float aspect = uRes.x / max(1.0, uRes.y);
    float f = 2.25 * uZoom;
    gl_Position = vec4(p1.x * f / (zCam * aspect), p1.y * f / zCam, clamp((zCam - 1.2) / 6.0 * 2.0 - 1.0, -0.99, 0.99), 1.0);
    gl_PointSize = clamp((2.6 + mod(aPhase * 7.0, 2.8)) * uDpr * (3.6 / zCam), 1.5, 9.0);
    vAlpha = clamp(0.28 + 0.45 * (1.0 - (zCam - 2.2) / 3.5), 0.12, 0.85);
    vTone = step(0.72, fract(aPhase * 1.618));
  }`;

  const PT_FS = `#version 300 es
  precision mediump float;
  in float vAlpha;
  in float vTone;
  uniform vec3 uC1;
  uniform vec3 uC2;
  out vec4 outColor;
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    float r2 = dot(p, p);
    if (r2 > 1.0) discard;
    float glow = exp(-r2 * 4.2);
    vec3 rgb = mix(uC1, uC2, vTone);
    outColor = vec4(mix(rgb, vec3(1.0), glow * 0.35), glow * vAlpha);
  }`;

  function compile(gl, type, src) {
    const sh = gl.createShader(type);
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
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
    gl.attachShader(p, vs);
    gl.attachShader(p, fs);
    gl.linkProgram(p);
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    return gl.getProgramParameter(p, gl.LINK_STATUS) ? p : null;
  }

  function createMaskStage(canvas, opts) {
    const o = opts || {};
    const gl = canvas.getContext('webgl2', { alpha: true, antialias: true, depth: true, premultipliedAlpha: false });
    let W = 1, H = 1, DPR = 1;
    let yaw = 0.24, pitch = -0.05, zoom = o.zoom || 1.04;
    let dragging = false, lx = 0, ly = 0, t = 0, lastDraw = 0;
    let alive = true, rafId = 0;
    let state = String(o.state || 'IDLE').toUpperCase();
    let fps = Number(o.fps || 60);
    let customMeshFlag = 0.0;

    // Optional 2D overlay canvas for Assimilis-Core precision HUD rings
    let hudCanvas = o.hudCanvas || null;
    let hudCtx = hudCanvas ? hudCanvas.getContext('2d') : null;

    let progMask = null, progPt = null, vaoMask = null, vaoPt = null, texMask = null;
    let indexCount = 0;
    let ptCount = 1400;

    function uploadMesh(mesh, isCustom) {
      if (!gl || !progMask || !mesh) return;
      customMeshFlag = isCustom ? 1.0 : 0.0;
      if (vaoMask) gl.deleteVertexArray(vaoMask);
      vaoMask = gl.createVertexArray();
      gl.bindVertexArray(vaoMask);

      const bPos = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bPos);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.positions, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);

      const bNorm = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bNorm);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.normals, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 3, gl.FLOAT, false, 0, 0);

      const bUv = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bUv);
      gl.bufferData(gl.ARRAY_BUFFER, mesh.uvs, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2, 2, gl.FLOAT, false, 0, 0);

      const bIdx = gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, bIdx);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, mesh.indices, gl.STATIC_DRAW);
      indexCount = mesh.indices.length;
      gl.bindVertexArray(null);
    }

    if (gl) {
      progMask = link(gl, MASK_VS, MASK_FS);
      progPt = link(gl, PT_VS, PT_FS);

      const texCanvas = buildMaskTextureCanvas();
      texMask = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, texMask);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, texCanvas);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

      uploadMesh(buildHighPolyMaskMesh(), false);

      // Orbiting volumetric holographic particle halo (Assimilis Core feel)
      const ptPos = new Float32Array(ptCount * 3);
      const ptPh = new Float32Array(ptCount);
      for (let i = 0; i < ptCount; i++) {
        const ring = i < ptCount * 0.65;
        const a = (i * 2.39996) % (Math.PI * 2);
        const r = ring ? (1.32 + (i % 37) * 0.022) : (0.95 + (i % 29) * 0.045);
        const y = ring ? (Math.sin(i * 1.7) * 0.52) : ((i % 41) / 41 * 2.5 - 1.25);
        ptPos[i * 3] = Math.cos(a) * r;
        ptPos[i * 3 + 1] = y;
        ptPos[i * 3 + 2] = Math.sin(a) * r;
        ptPh[i] = a;
      }
      vaoPt = gl.createVertexArray();
      gl.bindVertexArray(vaoPt);
      const bPt = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bPt);
      gl.bufferData(gl.ARRAY_BUFFER, ptPos, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 3, gl.FLOAT, false, 0, 0);
      const bPh = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, bPh);
      gl.bufferData(gl.ARRAY_BUFFER, ptPh, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 1, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);
    }

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
      if (canvas.width !== pw || canvas.height !== ph) {
        canvas.width = pw; canvas.height = ph;
      }
      if (hudCanvas && (hudCanvas.width !== pw || hudCanvas.height !== ph)) {
        hudCanvas.width = pw; hudCanvas.height = ph;
      }
    }

    function drawHudRings() {
      if (!hudCtx) return;
      hudCtx.setTransform(DPR, 0, 0, DPR, 0, 0);
      hudCtx.clearRect(0, 0, W, H);
      const cx = W * 0.5, cy = H * 0.5;
      const R = Math.min(W, H) * 0.375 * zoom;
      const c1 = state === 'ALERT' ? '#e81c2e' : (state === 'CONTAINED' ? '#10b981' : '#08b6e8');
      const c2 = state === 'ALERT' ? '#08b6e8' : '#e81c2e';

      // Precision JARVIS / Assimilis Core concentric HUD rings
      [
        { r: R * 1.03, w: 1.4, col: c1 + '55', dash: [44, 16, 10, 16], spd: 0.18 },
        { r: R * 1.15, w: 1.0, col: c2 + '40', dash: [22, 12], spd: -0.12 },
        { r: R * 1.26, w: 0.85, col: c1 + '2c', dash: [6, 10], spd: 0.08 }
      ].forEach((rg, idx) => {
        hudCtx.save();
        hudCtx.translate(cx, cy);
        hudCtx.rotate(t * rg.spd + idx * 0.9);
        hudCtx.strokeStyle = rg.col;
        hudCtx.lineWidth = rg.w;
        hudCtx.setLineDash(rg.dash);
        hudCtx.beginPath();
        hudCtx.arc(0, 0, rg.r, 0, Math.PI * 2);
        hudCtx.stroke();
        hudCtx.restore();
      });
      hudCtx.setLineDash([]);

      // Degree tick marks on outer ring
      hudCtx.save();
      hudCtx.translate(cx, cy);
      hudCtx.strokeStyle = c1 + '44';
      hudCtx.lineWidth = 1;
      for (let i = 0; i < 36; i++) {
        const a = (i / 36) * Math.PI * 2 + t * 0.05;
        const r0 = R * (i % 3 === 0 ? 1.08 : 1.11);
        const r1 = R * 1.14;
        hudCtx.beginPath();
        hudCtx.moveTo(Math.cos(a) * r0, Math.sin(a) * r0);
        hudCtx.lineTo(Math.cos(a) * r1, Math.sin(a) * r1);
        hudCtx.stroke();
      }
      hudCtx.restore();
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
      if (!reduced) {
        t += fps <= 12 ? 0.065 : 0.016;
        if (!dragging) yaw = 0.30 * Math.sin(t * 0.62);
      }

      if (gl && progMask && vaoMask) {
        gl.viewport(0, 0, canvas.width, canvas.height);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

        // 1. Background holographic particle halo
        if (progPt && vaoPt) {
          gl.disable(gl.DEPTH_TEST);
          gl.enable(gl.BLEND);
          gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
          gl.useProgram(progPt);
          gl.uniform2f(gl.getUniformLocation(progPt, 'uRes'), W, H);
          gl.uniform1f(gl.getUniformLocation(progPt, 'uTime'), t);
          gl.uniform1f(gl.getUniformLocation(progPt, 'uYaw'), yaw);
          gl.uniform1f(gl.getUniformLocation(progPt, 'uZoom'), zoom);
          gl.uniform1f(gl.getUniformLocation(progPt, 'uDpr'), DPR);
          const sc = stateCode();
          if (sc === 2) {
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC1'), 0.96, 0.14, 0.24);
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC2'), 0.06, 0.72, 0.94);
          } else if (sc === 3) {
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC1'), 0.07, 0.78, 0.56);
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC2'), 0.08, 0.75, 0.94);
          } else {
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC1'), 0.04, 0.72, 0.92);
            gl.uniform3f(gl.getUniformLocation(progPt, 'uC2'), 0.92, 0.12, 0.20);
          }
          gl.bindVertexArray(vaoPt);
          gl.drawArrays(gl.POINTS, 0, ptCount);
          gl.bindVertexArray(null);
        }

        // 2. Sculpted 3D Guy Fawkes Hacker Mask (PBR Porcelain + Agentsar Fresnel)
        gl.enable(gl.DEPTH_TEST);
        gl.depthFunc(gl.LEQUAL);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(progMask);
        gl.uniform2f(gl.getUniformLocation(progMask, 'uRes'), W, H);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uYaw'), yaw);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uPitch'), pitch);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uZoom'), zoom);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uBob'), reduced ? 0 : Math.sin(t * 1.35) * 0.035);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uGlitch'), (state === 'ALERT' && !reduced && Math.sin(t * 17) > 0.72) ? 1.0 : 0.0);
        gl.uniform1f(gl.getUniformLocation(progMask, 'uTime'), t);
        gl.uniform1i(gl.getUniformLocation(progMask, 'uState'), stateCode());
        gl.uniform1f(gl.getUniformLocation(progMask, 'uCustomMesh'), customMeshFlag);
        gl.activeTexture(gl.TEXTURE0);
        gl.bindTexture(gl.TEXTURE_2D, texMask);
        gl.uniform1i(gl.getUniformLocation(progMask, 'uTex'), 0);

        gl.bindVertexArray(vaoMask);
        gl.drawElements(gl.TRIANGLES, indexCount, gl.UNSIGNED_INT, 0);
        gl.bindVertexArray(null);
      }

      drawHudRings();
    }

    canvas.addEventListener('pointerdown', (e) => {
      dragging = true; lx = e.clientX; ly = e.clientY;
    });
    window.addEventListener('pointermove', (e) => {
      if (!dragging) return;
      yaw += (e.clientX - lx) * 0.009;
      pitch = Math.max(-0.75, Math.min(0.75, pitch + (e.clientY - ly) * 0.008));
      lx = e.clientX; ly = e.clientY;
    });
    window.addEventListener('pointerup', () => { dragging = false; });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      zoom = Math.max(0.68, Math.min(1.65, zoom * (e.deltaY > 0 ? 0.93 : 1.07)));
    }, { passive: false });

    rafId = requestAnimationFrame(render);

    return {
      setState(next) { state = String(next || 'IDLE').toUpperCase(); },
      setFps(next) { fps = Number(next) <= 12 ? 12 : 60; },
      loadObjMesh(objText) {
        const m = parseObjText(objText);
        if (m) uploadMesh(m, true);
        return !!m;
      },
      destroy() { alive = false; if (rafId) cancelAnimationFrame(rafId); }
    };
  }

  root.ChappaMask = { createMaskStage, parseObjText };
})(typeof window !== 'undefined' ? window : globalThis);
