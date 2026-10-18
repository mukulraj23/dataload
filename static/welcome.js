(function () {
  "use strict";
  var bg = document.getElementById("heroBg");
  if (bg && window.HeroBG) window.HeroBG.mount(bg, "globe", { background: "#0a0a0a", pointerTarget: document.getElementById("hero") });

  if (window.SectionBG) document.querySelectorAll(".sec-bg").forEach(function (el) {
    window.SectionBG.mount(el, el.dataset.scene, { background: "#0a0a0a", pointerTarget: el.parentElement });
  });

  var nav = document.getElementById("nav");
  function onScroll() { nav.classList.toggle("solid", window.scrollY > 40); }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // count-up stats
  function countUp(el) {
    var end = +el.dataset.count, t0 = null;
    if (!end) return;
    function step(ts) { t0 = t0 || ts; var p = Math.min(1, (ts - t0) / 1200); el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3))); if (p < 1) requestAnimationFrame(step); }
    requestAnimationFrame(step);
  }

  // how-it-works: auto-advancing steps with a typing terminal
  var flow = document.getElementById("flow");
  if (flow) {
    var steps = flow.querySelectorAll(".flow-steps li"), panes = flow.querySelectorAll(".pane");
    var title = document.getElementById("termTitle"), typed = document.getElementById("typed");
    var titles = ["question", "gemma-4 \u00b7 plan.json", "pandas \u00b7 result"];
    var Q = "Which region has the highest average charges?";
    var cur = 0, timer = null, typer = null, started = false;
    function type() {
      clearInterval(typer); typed.textContent = ""; var i = 0;
      typer = setInterval(function () { typed.textContent = Q.slice(0, ++i); if (i >= Q.length) clearInterval(typer); }, 45);
    }
    function show(n) {
      cur = n;
      steps.forEach(function (s, i) { s.classList.toggle("on", i === n); });
      panes.forEach(function (p, i) { p.classList.toggle("on", i === n); });
      title.textContent = titles[n];
      if (n === 0) type();
      clearTimeout(timer);
      timer = setTimeout(function () { show((cur + 1) % 3); }, 4500);
    }
    steps.forEach(function (s, i) { s.addEventListener("click", function () { show(i); }); });
    new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting && !started) { started = true; show(0); } });
    }, { threshold: 0.3 }).observe(flow);
  }

  // copy button
  document.querySelectorAll(".copy").forEach(function (b) {
    b.addEventListener("click", function () {
      var label = b.querySelector("span");
      (navigator.clipboard ? navigator.clipboard.writeText(b.dataset.copy) : Promise.reject()).then(function () {
        label.textContent = "Copied";
      }, function () { label.textContent = "Select and copy"; });
      setTimeout(function () { label.textContent = "Copy"; }, 1600);
    });
  });

  var items = document.querySelectorAll(".head, .persona, .flow, .tile, .shot, .open, .faq, .foot-cta, .strip");
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.classList.add("in");
        e.target.querySelectorAll("[data-count]").forEach(countUp);
        io.unobserve(e.target);
      });
    }, { threshold: 0.12 });
    items.forEach(function (n) { n.classList.add("reveal"); io.observe(n); });
  }
})();
