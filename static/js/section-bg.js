/*
 * Moving backgrounds for two welcome page sections.
 * SectionBG.mount(element, "matrix" | "scatter")
 * Monochrome Canvas 2D, pauses when off screen, respects reduced motion.
 */
(function () {
  "use strict";

  function hash(n) { const s = Math.sin(n * 127.1) * 43758.5453; return s - Math.floor(s); }
  function vnoise(x) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return hash(i) * (1 - u) + hash(i + 1) * u; }

  /* 1. matrix: a grid of dots that rises and falls like a live bar chart (the logo, at scale) */
  function matrix(ctx, st) {
    const { w, h, t, dpr } = st;
    ctx.clearRect(0, 0, w, h);
    const gap = 22 * dpr, cols = Math.ceil(w / gap) + 1, rows = Math.ceil(h / gap) + 1;
    const tt = t * 0.00025;
    for (let c = 0; c < cols; c++) {
      const x = c * gap + gap / 2;
      const dx = st.mx < 0 ? 1 : Math.min(1, Math.abs(x - st.mx) / (220 * dpr));
      let level = 0.18 + 0.55 * vnoise(c * 0.23 + tt) + 0.2 * Math.sin(c * 0.11 + tt * 3);
      level += (1 - dx) * 0.25;
      const lit = Math.floor(Math.max(0, Math.min(1, level)) * rows);
      for (let r = 0; r < rows; r++) {
        const y = h - (r * gap + gap / 2);
        const on = r < lit, top = r === lit - 1;
        ctx.globalAlpha = on ? (top ? 0.9 : 0.16 + 0.34 * (r / Math.max(1, lit))) : 0.07;
        ctx.fillStyle = "#ededed";
        ctx.beginPath();
        ctx.arc(x, y, (on ? (top ? 2.6 : 1.9) : 1) * dpr, 0, 6.283);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }

  /* 2. scatter: a scatter plot whose points gather onto a trend line, then let go */
  function scatterInit(st) {
    st.pts = Array.from({ length: 170 }, (_, i) => ({ u: hash(i + 1), e: (hash(i + 99) - 0.5) * 2, s: hash(i + 7) }));
  }
  function scatter(ctx, st) {
    const { w, h, t, dpr } = st;
    ctx.clearRect(0, 0, w, h);
    const L = w * 0.08, R = w * 0.94, B = h * 0.86, T = h * 0.14;
    const cycle = (Math.sin(t * 0.00035) + 1) / 2;
    const fit = Math.pow(cycle, 3);
    ctx.strokeStyle = "rgba(237,237,237,.08)"; ctx.lineWidth = 1 * dpr;
    for (let k = 0; k <= 5; k++) { const y = B - (B - T) * k / 5; ctx.beginPath(); ctx.moveTo(L, y); ctx.lineTo(R, y); ctx.stroke(); }
    ctx.strokeStyle = "rgba(237,237,237,.22)";
    ctx.beginPath(); ctx.moveTo(L, T); ctx.lineTo(L, B); ctx.lineTo(R, B); ctx.stroke();
    const line = (u) => B - (B - T) * (0.15 + 0.7 * u);
    ctx.setLineDash([4 * dpr, 6 * dpr]);
    ctx.strokeStyle = `rgba(237,237,237,${0.12 + fit * 0.5})`;
    ctx.beginPath(); ctx.moveTo(L, line(0)); ctx.lineTo(R, line(1)); ctx.stroke();
    ctx.setLineDash([]);
    for (const p of st.pts) {
      const x = L + (R - L) * p.u;
      const wob = Math.sin(t * 0.0006 + p.s * 20) * 6 * dpr;
      const y = line(p.u) + p.e * (B - T) * 0.32 * (1 - fit * 0.85) + wob;
      let a = 0.25 + p.s * 0.5;
      if (st.mx > 0 && Math.hypot(x - st.mx, y - st.my) < 90 * dpr) a = 1;
      ctx.globalAlpha = a; ctx.fillStyle = "#ededed";
      ctx.beginPath(); ctx.arc(x, y, (1.2 + p.s * 1.6) * dpr, 0, 6.283); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  const SCENES = { matrix: [matrix], scatter: [scatter, scatterInit] };

  function mount(el, name, opts = {}) {
    const [draw, init] = SCENES[name] || SCENES.matrix;
    const canvas = document.createElement("canvas");
    canvas.setAttribute("aria-hidden", "true");
    canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block";
    el.appendChild(canvas);
    const ctx = canvas.getContext("2d");
    const st = { bg: opts.background || "#0a0a0a", dpr: Math.min(window.devicePixelRatio || 1, 1.5), w: 0, h: 0, t: 0, mx: -1, my: -1 };
    if (init) init(st);
    function resize() {
      const r = el.getBoundingClientRect();
      st.w = canvas.width = Math.max(1, Math.round(r.width * st.dpr));
      st.h = canvas.height = Math.max(1, Math.round(r.height * st.dpr));
    }
    resize();
    new ResizeObserver(resize).observe(el);
    const target = opts.pointerTarget || el.parentElement || el;
    target.addEventListener("pointermove", (e) => { const r = el.getBoundingClientRect(); st.mx = (e.clientX - r.left) * st.dpr; st.my = (e.clientY - r.top) * st.dpr; });
    target.addEventListener("pointerleave", () => { st.mx = st.my = -1; });
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    let visible = true, last = performance.now(), raf = 0;
    function loop(now) {
      raf = 0;
      if (!visible) return;
      st.t += Math.min(now - last, 50); last = now;
      draw(ctx, st);
      if (!still) raf = requestAnimationFrame(loop);
    }
    if ("IntersectionObserver" in window) new IntersectionObserver((es) => { visible = es[0].isIntersecting; if (visible && !raf) { last = performance.now(); loop(last); } }).observe(el);
    loop(performance.now());
    return { canvas };
  }

  window.SectionBG = { mount, scenes: Object.keys(SCENES) };
})();
