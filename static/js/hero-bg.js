/*
 * Welcome page hero: a slowly turning globe of dots that follows the pointer.
 * Canvas 2D with a small 3D projection, no libraries.
 * HeroBG.mount(element, "globe")
 */
(function () {
  "use strict";

  // value noise
  const P = new Uint8Array(512);
  (function () {
    const p = [...Array(256).keys()];
    let s = 2024;
    for (let i = 255; i > 0; i--) { s = (s * 16807) % 2147483647; const j = s % (i + 1); [p[i], p[j]] = [p[j], p[i]]; }
    for (let i = 0; i < 512; i++) P[i] = p[i & 255];
  })();
  const fade = (t) => t * t * t * (t * (t * 6 - 15) + 10);
  const lerp = (a, b, t) => a + (b - a) * t;
  const grad = (h, x, y, z) => { const u = h < 8 ? x : y, v = h < 4 ? y : h === 12 || h === 14 ? x : z; return ((h & 1) ? -u : u) + ((h & 2) ? -v : v); };
  function noise(x, y, z) {
    const X = Math.floor(x) & 255, Y = Math.floor(y) & 255, Z = Math.floor(z) & 255;
    x -= Math.floor(x); y -= Math.floor(y); z -= Math.floor(z);
    const u = fade(x), v = fade(y), w = fade(z);
    const A = P[X] + Y, AA = P[A] + Z, AB = P[A + 1] + Z, B = P[X + 1] + Y, BA = P[B] + Z, BB = P[B + 1] + Z;
    return lerp(lerp(lerp(grad(P[AA] & 15, x, y, z), grad(P[BA] & 15, x - 1, y, z), u), lerp(grad(P[AB] & 15, x, y - 1, z), grad(P[BB] & 15, x - 1, y - 1, z), u), v),
      lerp(lerp(grad(P[AA + 1] & 15, x, y, z - 1), grad(P[BA + 1] & 15, x - 1, y, z - 1), u), lerp(grad(P[AB + 1] & 15, x, y - 1, z - 1), grad(P[BB + 1] & 15, x - 1, y - 1, z - 1), u), v), w);
  }

  const INK = "232,232,236";
  // pointer, smoothed, in -1..1
  function pointer(st) {
    const tx = st.mx < -9000 ? 0 : (st.mx / (st.w / st.dpr)) * 2 - 1;
    const ty = st.my < -9000 ? 0 : (st.my / (st.h / st.dpr)) * 2 - 1;
    st.px = lerp(st.px || 0, tx, 0.04); st.py = lerp(st.py || 0, ty, 0.04);
    return [st.px, st.py];
  }
  function clear(ctx, st) { ctx.globalCompositeOperation = "source-over"; ctx.fillStyle = st.bg; ctx.fillRect(0, 0, st.w, st.h); }

  // 2. Globe: a rotating sphere of data points
  function globeInit(st) {
    const n = 2600, pts = [];
    const ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < n; i++) {
      const y = 1 - (i / (n - 1)) * 2, r = Math.sqrt(1 - y * y), th = ga * i;
      // keep only "land-like" points using noise, so it reads as a world, not a ball
      const x = Math.cos(th) * r, z = Math.sin(th) * r;
      const land = noise(x * 1.8 + 5, y * 1.8, z * 1.8) > -0.02;
      pts.push([x, y, z, land, Math.random()]);
    }
    st.pts = pts;
  }
  function globe(ctx, st) {
    if (!st.pts) globeInit(st);
    clear(ctx, st);
    const [px, py] = pointer(st);
    const W = st.w, H = st.h, wide = W > H * 1.3;
    const R = wide ? Math.min(W * 0.235, H * 0.4) : W * 0.36;
    const cx = wide ? W - R - W * 0.045 : W * 0.5, cy = wide ? H * 0.55 : H * 0.25;
    const ry = st.t * 0.00012 + px * 0.6, rx = -0.35 + py * 0.3;
    const cyr = Math.cos(ry), syr = Math.sin(ry), cxr = Math.cos(rx), sxr = Math.sin(rx);
    const fov = R * 4;
    ctx.globalCompositeOperation = "lighter";
    // outline ring
    ctx.strokeStyle = `rgba(${INK},0.08)`; ctx.lineWidth = 1 * st.dpr;
    ctx.beginPath(); ctx.arc(cx, cy, R * 1.0, 0, Math.PI * 2); ctx.stroke();
    const pulse = st.t * 0.0015;
    for (const p of st.pts) {
      let x = p[0] * cyr - p[2] * syr, z = p[0] * syr + p[2] * cyr, y = p[1];
      const y2 = y * cxr - z * sxr; z = y * sxr + z * cxr; y = y2;
      const f = fov / (fov + z * R);
      const front = (1 - z) / 2; // 0 back .. 1 front
      if (!p[3] && front < 0.5) continue;
      const a = p[3] ? 0.08 + front * 0.75 : 0.05 + front * 0.1;
      const hot = p[3] && p[4] > 0.985 ? 0.5 + 0.5 * Math.sin(pulse + p[4] * 50) : 0;
      const s = (p[3] ? 1.5 : 1) * st.dpr * f * (1 + hot * 1.5);
      ctx.fillStyle = `rgba(${INK},${Math.min(1, a + hot * 0.6)})`;
      ctx.fillRect(cx + x * R * f - s / 2, cy + y * R * f - s / 2, s, s);
    }
  }

  const SCENES = { globe };

  function mount(el, name, opts = {}) {
    const draw = SCENES[name] || globe;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block";
    el.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const st = { ctx, bg: opts.background || "#0a0a0a", dpr: Math.min(window.devicePixelRatio || 1, 1.5), w: 0, h: 0, t: 0, dt: 16, mx: -9999, my: -9999 };
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    function resize() {
      const r = el.getBoundingClientRect();
      st.w = canvas.width = Math.max(1, Math.round(r.width * st.dpr));
      st.h = canvas.height = Math.max(1, Math.round(r.height * st.dpr));
    }
    resize();
    new ResizeObserver(resize).observe(el);
    const target = opts.pointerTarget || el.parentElement || el;
    target.addEventListener("pointermove", (e) => { const r = el.getBoundingClientRect(); st.mx = e.clientX - r.left; st.my = e.clientY - r.top; });
    target.addEventListener("pointerleave", () => { st.mx = st.my = -9999; });
    let visible = true, last = performance.now(), raf = 0;
    if ("IntersectionObserver" in window) new IntersectionObserver((es) => { visible = es[0].isIntersecting; if (visible && !raf) loop(performance.now()); }).observe(el);
    function loop(now) {
      raf = 0;
      if (!visible) return;
      st.dt = Math.min(now - last, 50); last = now; st.t += st.dt;
      draw(ctx, st);
      if (!still) raf = requestAnimationFrame(loop);
    }
    loop(performance.now());
    return { canvas };
  }

  window.HeroBG = { mount, scenes: Object.keys(SCENES) };
})();
