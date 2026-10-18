/* DataLoad front-end. Plain JS, no build step. */
(() => {
  "use strict";

  // i18n
  const I18N = {
    en: {
      tagline: "Talk to your data in your language",
      how_title: "How it works",
      how1: "Gemma 4 turns your question into a small query plan",
      how2: "pandas does the maths. The AI never guesses numbers",
      how3: "Every answer comes with a chart, proof and warnings",
      s1: "Gemma 4 understands the question", s2: "pandas computes exact numbers", s3: "Chart + proof + warnings",
      trust: "Every number is verified by code. If the data can't answer, it says so.",
      sample_badge: "Demo dataset (public file)",
      preview: "View data", change: "Change data", columns: "Columns", health: "Data Health",
      no_ai: "· instant, no AI", share: "Share report", download: "Download",
      eyebrow: "Step 1 of 2",
      hero_title: "Where is your data?",
      hero_sub: "Upload a spreadsheet, photograph a register, or open a demo dataset. Then ask a question in plain words.",
      opt_file: "Upload CSV / Excel", opt_file_sub: "Click here or drop a file",
      opt_photo: "Register photo", opt_photo_sub: "Handwritten tables work too",
      opt_sample: "Demo datasets", opt_sample_sub: "7 public CSV files to try",
      demos_title: "Pick a demo dataset", demo_loading: "Loading",
      placeholder: "Ask a question about your data",
      foot: "Numbers are calculated with pandas · Model: Gemma 4 (open-weight)",
      key_title: "Add your Gemini API key",
      key_sub: "Gemma 4 runs through the free Gemini API. Add the key once; it stays saved in this browser.",
      key_link: "Get a free key from Google AI Studio", key_note: "The key is only sent to Google's API.",
      cancel: "Cancel", save: "Save",
      photo_title: "Register photo to table", reading_photo: "Gemma 4 is reading the photo…",
      photo_note: "Please review. Highlighted cells (??) could not be read. Click a cell to fix it.",
      add_row: "+ Row", use_table: "Use this data",
      welcome_h: "Your data is ready",
      welcome_p: (n, c) => `Found ${n} rows and ${c} columns. Pick a question below or type your own.`,
      thinking: "Thinking", conf: { high: "Reliable", medium: "Use with care", low: "Low confidence" },
      cached: "cached", proof: "Show proof", hide_proof: "Hide proof", explain: "Explain with AI", copy: "Copy",
      copied: "Copied", tab_code: "Code", tab_rows: "Rows used", tab_plan: "Gemma's plan", tab_result: "Result",
      model_time: "Model", calc_time: "Calculation", rows_used: (n) => `${n} rows used`,
      err_net: "Could not reach the server. Check your internet.",
      err_429: "Free API limit reached. Wait a minute or use another key.",
      err_key: "That API key looks invalid. Please add a new one.",
      err_gone: "The data was cleared on the server (it may have restarted). Please upload again.",
      err_read: "Could not read that file. Use CSV or Excel.",
      err_photo: "No table found in that photo. Try a clear, straight photo.",
      err_generic: "Something went wrong. Please try again.",
      err_big: "That file is too big. The limit is 20 MB.",
      err_empty: "That file is empty.",
      err_server: "The server hit an error with that request. Please try again.",
      err_copy: "Couldn't copy. Select the text and copy it yourself.",
      share_title: "DataLoad report", key_saved: "Key saved",
    },
  };

  // state
  const S = {
    lang: "en",
    key: localStorage.getItem("ds_key") || "",
    serverKey: false,
    ds: null,
    history: [], // {q, res}
    busy: false,
    pending: null, // action to retry after key is saved
    photoName: "Register photo",
  };
  const t = (k) => I18N[S.lang][k];
  const IC = {
    clock: '<path d="M12 7v5l3 2"/><circle cx="12" cy="12" r="9"/>',
    alert: '<path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
    spark: '<path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6"/>',
    code: '<path d="m16 18 6-6-6-6M8 6l-6 6 6 6"/>',
    copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/>',
    rows: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M3 15h18"/>',
    dot: '<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>',
  };
  const icon = (n, s = 15) => `<svg class="ic" viewBox="0 0 24 24" width="${s}" height="${s}" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${IC[n]}</svg>`;
  const $ = (s, el = document) => el.querySelector(s);
  const el = (tag, cls, html) => {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html !== undefined) e.innerHTML = html;
    return e;
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const RAW_COL = /(^|_)(year|yr|id|code|zip|pin|pincode|roll|no|number|phone|mobile)($|_)/i;
  const fmtCell = (v, col) => (typeof v === "number" && Number.isInteger(v) && (RAW_COL.test(String(col || "")) || (v >= 1800 && v <= 2100 && /year|date|yr|season/i.test(String(col || ""))))) ? String(v) : fmtNum(v);
  const fmtNum = (v) => (typeof v === "number" ? (Number.isInteger(v) || Math.abs(v) >= 100 ? v.toLocaleString("en-IN", { maximumFractionDigits: 0 }) : v.toLocaleString("en-IN", { maximumFractionDigits: 2 })) : v ?? "");

  // API
  class ApiError extends Error {
    constructor(status, code) { super(code); this.status = status; this.code = code; }
  }
  async function api(path, { json, form, method = "POST" } = {}) {
    const headers = {};
    if (S.key) headers["X-Api-Key"] = S.key;
    let body;
    if (json) { headers["Content-Type"] = "application/json"; body = JSON.stringify(json); }
    if (form) body = form;
    let r;
    try {
      r = await fetch(path, { method, headers, body });
    } catch (e) {
      throw new ApiError(0, "NETWORK");
    }
    let data = null;
    try { data = await r.json(); } catch (_) { /* ignore */ }
    if (!r.ok) throw new ApiError(r.status, (data && data.error) || `HTTP_${r.status}`);
    return data;
  }
  function errText(e) {
    if (!(e instanceof ApiError)) return t("err_generic");
    if (e.status === 0) return t("err_net");
    if (e.status === 429) return t("err_429");
    if (e.status === 401) return t("err_key");
    if (e.code === "DATASET_GONE") return t("err_gone");
    if (String(e.code).startsWith("READ_FAILED") || e.code === "EMPTY_DATA") return t("err_read");
    if (e.code === "PHOTO_NOT_TABLE") return t("err_photo");
    if (e.status === 413 || e.code === "FILE_TOO_BIG") return t("err_big");
    if (e.code === "EMPTY_FILE") return t("err_empty");
    if (e.status >= 500) return t("err_server");
    return t("err_generic");
  }
  const needsKey = (e) => e instanceof ApiError && e.status === 401;

  function hasKey() { return S.serverKey || !!S.key; }

  /** Run fn; if the server says the key is missing/invalid, ask once and retry automatically. */
  async function withKey(fn) {
    if (!hasKey()) { S.pending = fn; openKeyModal(); return; }
    try {
      await fn();
    } catch (e) {
      if (needsKey(e) && !S.serverKey) {
        if (e.code === "API_KEY_INVALID") { S.key = ""; localStorage.removeItem("ds_key"); }
        S.pending = fn; openKeyModal(e.code === "API_KEY_INVALID");
      } else throw e;
    }
  }

  // i18n apply
  function applyLang() {
    document.documentElement.lang = S.lang;
    document.querySelectorAll("[data-i18n]").forEach((n) => {
      const v = t(n.dataset.i18n);
      if (typeof v === "string") n.innerHTML = esc(v).replace(/\n/g, "<br>");
    });
    $("#qInput").placeholder = t("placeholder");
    updateKeyBtn();
  }

  // sidebar
  function renderSidebar() {
    const d = S.ds;
    $("#sideEmpty").classList.toggle("hidden", !!d);
    $("#sideData").classList.toggle("hidden", !d);
    document.querySelector(".layout").classList.toggle("no-data", !d);
    if (!d) return;
    $("#dsName").textContent = d.name;
    $("#dsDims").textContent = `${d.n_rows.toLocaleString("en-IN")} rows · ${d.n_cols} columns`;
    $("#sampleBadge").classList.toggle("hidden", !d.is_sample);
    const kindIcon = { number: "#", time: "D", category: "Aa", text: "T" };
    $("#colChips").innerHTML = d.columns.map((c) => `<span class="chip"><i>${kindIcon[c.kind] || ""}</i>${esc(c.name)}</span>`).join("");
    $("#healthList").innerHTML = d.health.map((h) => `<li class="${h.level}">${esc(h[S.lang])}</li>`).join("");
    $("#shareBox").classList.toggle("hidden", !S.history.some((h) => h.res && h.res.ok));
  }

  // dataset loading
  function showChat() {
    $("#hero").classList.add("hidden");
    $("#chat").classList.remove("hidden");
  }
  function showHero() {
    $("#chat").classList.add("hidden");
    $("#hero").classList.remove("hidden");
  }

  const histKey = () => "ds_hist_" + (S.ds ? S.ds.id : "");
  function saveHistory() {
    if (!S.ds) return;
    try { sessionStorage.setItem(histKey(), JSON.stringify(S.history.slice(-30))); } catch (_) { /* storage full: skip */ }
  }
  function setDataset(d, keepHistory) {
    S.ds = d;
    S.history = [];
    if (keepHistory) { try { S.history = JSON.parse(sessionStorage.getItem(histKey()) || "[]"); } catch (_) { S.history = []; } }
    sessionStorage.setItem("ds_id", d.id);
    renderSidebar();
    showChat();
    rerenderThread();
    renderSuggest();
    setTimeout(() => $("#qInput").focus(), 50);
  }

  async function loadFile(file) {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    toast("Uploading " + file.name);
    try { setDataset(await api("/api/upload", { form: fd })); hideToast(); }
    catch (e) { toast(errText(e), 4000); }
  }

  async function openDemos() {
    const list = $("#demoList");
    $("#demoModal").classList.remove("hidden");
    if (list.dataset.loaded) return;
    try {
      const demos = await api("/api/demos", { method: "GET" });
      list.innerHTML = "";
      demos.forEach((d) => {
        const b = el("button", "demo-item", `<b>${esc(d.title)}</b><span>${esc(d.about)}</span><code>${esc(d.file)}</code>`);
        b.type = "button";
        b.onclick = () => loadDemo(d.id, b);
        list.appendChild(b);
      });
      list.dataset.loaded = "1";
    } catch (e) { list.innerHTML = `<div class="note warn">${esc(errText(e))}</div>`; }
  }
  async function loadDemo(id, btn) {
    if (btn) { btn.disabled = true; btn.classList.add("loading"); }
    try { const d = await api(`/api/demo/${encodeURIComponent(id)}`); closeModals(); setDataset(d); }
    catch (e) { toast(errText(e), 4000); }
    if (btn) { btn.disabled = false; btn.classList.remove("loading"); }
  }

  // photo flow
  let photoTimerId = null, photoReq = 0, photoUrl = null;
  function openPhoto(file) {
    if (!file) return;
    const my = ++photoReq;
    const live = () => my === photoReq && !$("#photoModal").classList.contains("hidden");
    S.photoName = file.name || "Register photo";
    if (photoUrl) URL.revokeObjectURL(photoUrl);
    photoUrl = URL.createObjectURL(file);
    $("#photoPreview").src = photoUrl;
    $("#photoModal").classList.remove("hidden");
    $("#photoLoading").classList.remove("hidden");
    $("#photoResult").classList.add("hidden");
    $("#photoError").classList.add("hidden");
    $("#photoTimer").textContent = "0.0s";
    clearInterval(photoTimerId);

    const run = async () => {
      if (!live()) return;
      const t0 = performance.now();
      clearInterval(photoTimerId);
      photoTimerId = setInterval(() => { $("#photoTimer").textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s"; }, 100);
      const fd = new FormData();
      fd.append("file", file);
      let res;
      try { res = await api("/api/photo", { form: fd }); }
      finally { if (my === photoReq) clearInterval(photoTimerId); }
      if (!live()) return;
      renderPhotoTable(res.table);
      $("#photoNote").textContent = `${t("photo_note")} (${res.seconds}s)`;
      $("#photoLoading").classList.add("hidden");
      $("#photoResult").classList.remove("hidden");
    };
    withKey(run).catch((e) => {
      if (!live()) return;
      clearInterval(photoTimerId);
      $("#photoLoading").classList.add("hidden");
      $("#photoError").textContent = errText(e);
      $("#photoError").classList.remove("hidden");
    });
  }

  function renderPhotoTable(tb) {
    const tbl = $("#photoTable");
    const head = `<thead><tr>${tb.columns.map((c) => `<th contenteditable="true">${esc(c)}</th>`).join("")}</tr></thead>`;
    const rows = tb.rows.map((r) => `<tr>${r.map((v) => {
      const s = v == null ? "" : String(v);
      return `<td contenteditable="true" class="${s.includes("??") ? "unsure" : ""}">${esc(s)}</td>`;
    }).join("")}</tr>`).join("");
    tbl.innerHTML = head + `<tbody>${rows}</tbody>`;
  }
  function addPhotoRow() {
    const hr = $("#photoTable thead tr");
    if (!hr) return;
    const n = hr.children.length;
    const tr = el("tr");
    for (let i = 0; i < n; i++) { const td = el("td"); td.contentEditable = "true"; tr.appendChild(td); }
    $("#photoTable tbody").appendChild(tr);
    tr.firstChild.focus();
  }
  async function usePhotoTable() {
    const columns = [...document.querySelectorAll("#photoTable thead th")].map((th) => th.textContent.trim() || "col");
    const rows = [...document.querySelectorAll("#photoTable tbody tr")]
      .map((tr) => [...tr.children].map((td) => td.textContent.trim()))
      .filter((r) => r.some((v) => v !== ""));
    try {
      const d = await api("/api/table", { json: { columns, rows, name: S.photoName, lang: S.lang } });
      closeModals();
      setDataset(d);
    } catch (e) { toast(errText(e), 4000); }
  }

  // chat
  function botMsg(inner, plain) {
    const m = el("div", "msg bot");
    m.innerHTML = `<div class="avatar"><svg viewBox="0 0 100 100" fill="currentColor" aria-hidden="true"><circle cx="14" cy="14" r="3" opacity=".35"/><circle cx="14" cy="38" r="3" opacity=".35"/><circle cx="14" cy="62" r="3" opacity=".35"/><circle cx="14" cy="86" r="9"/><circle cx="38" cy="14" r="3" opacity=".35"/><circle cx="38" cy="38" r="3" opacity=".35"/><circle cx="38" cy="62" r="9"/><circle cx="38" cy="86" r="9"/><circle cx="62" cy="14" r="3" opacity=".35"/><circle cx="62" cy="38" r="9"/><circle cx="62" cy="62" r="9"/><circle cx="62" cy="86" r="9"/><circle cx="86" cy="14" r="9"/><circle cx="86" cy="38" r="9"/><circle cx="86" cy="62" r="9"/><circle cx="86" cy="86" r="9"/></svg></div>`;
    const c = el("div", "card" + (plain ? " plain" : ""));
    if (typeof inner === "string") c.innerHTML = inner; else c.appendChild(inner);
    m.appendChild(c);
    return m;
  }
  function userMsg(q) {
    const m = el("div", "msg user");
    m.appendChild(el("div", "bubble", esc(q)));
    return m;
  }
  function scrollDown() {
    const th = $("#thread");
    requestAnimationFrame(() => { th.scrollTop = th.scrollHeight; });
  }

  function rerenderThread() {
    const th = $("#thread");
    CHARTS.forEach((c) => c.destroy());
    CHARTS = [];
    th.innerHTML = "";
    if (!S.ds) return;
    th.appendChild(botMsg(`<div class="welcome"><h2>${esc(t("welcome_h"))}</h2><p>${esc(t("welcome_p")(S.ds.n_rows, S.ds.n_cols))}</p></div>`, true));
    S.history.forEach((h) => {
      th.appendChild(userMsg(h.q));
      th.appendChild(h.res ? answerCard(h) : errorCard(h));
    });
    scrollDown();
  }

  function renderSuggest() {
    const box = $("#suggest");
    box.innerHTML = "";
    (S.ds?.suggestions || []).forEach((s) => {
      const b = el("button", "sugg", esc(s));
      b.type = "button";
      b.onclick = () => ask(s);
      b.disabled = S.busy;
      box.appendChild(b);
    });
  }

  function errorCard(h) {
    return botMsg(`<div class="answer-text bad">${esc(h.err)}</div>`);
  }

  function tableHTML(tb, maxRows = 50) {
    if (!tb) return "";
    const isNum = tb.rows.length ? tb.rows[0].map((_, i) => tb.rows.every((r) => r[i] == null || typeof r[i] === "number")) : [];
    return `<table><thead><tr>${tb.columns.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
      tb.rows.slice(0, maxRows).map((r) => `<tr>${r.map((v, i) => `<td class="${isNum[i] ? "num" : ""}">${esc(fmtCell(v, tb.columns[i]))}</td>`).join("")}</tr>`).join("")
    }</tbody></table>`;
  }

  const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const prettyLabel = (v) => {
    const m = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(String(v));
    if (!m || +m[2] < 1 || +m[2] > 12) return v;
    return m[3] ? `${+m[3]} ${MON[+m[2] - 1]}` : `${MON[+m[2] - 1]} ${m[1].slice(2)}`;
  };
  const NICE = { kwh: "kWh", bill_rs: "Bill (₹)", units: "Units", students: "Students" };
  const niceCol = (c) => NICE[c] || String(c || "").replace(/_per_/g, " per ").replace(/_/g, " ");
  const PALETTE = ["#ededed", "#8a8a8a", "#5fb98a", "#4a4a4a", "#c9c9c9", "#2f6f52"];
  let CHARTS = [];
  function drawChart(canvas, spec) {
    if (!window.Chart || !spec || !canvas || !canvas.isConnected) return;
    const line = spec.kind === "line";
    const many = spec.datasets.length > 1;
    CHARTS.push(new Chart(canvas, {
      type: line ? "line" : "bar",
      data: {
        labels: spec.labels.map(prettyLabel),
        datasets: spec.datasets.map((d, i) => ({
          label: prettyLabel(d.label) || niceCol(spec.y_title), data: d.data,
          backgroundColor: line ? "rgba(237,237,237,.06)" : (many ? PALETTE[i % PALETTE.length] : spec.labels.map((_, j) => j === 0 ? "#ededed" : "#3a3a3a")),
          borderColor: PALETTE[i % PALETTE.length], borderWidth: line ? 2.5 : 0, borderRadius: 4,
          fill: line, tension: .3, cubicInterpolationMode: "monotone", pointRadius: line ? 3.5 : 0, pointBackgroundColor: "#ededed", maxBarThickness: 46,
        })),
      },
      options: {
        responsive: true, maintainAspectRatio: false, animation: { duration: 450 },
        plugins: {
          legend: { display: many, labels: { color: "#a1a1a1", font: { family: "Geist", size: 12 }, boxWidth: 12, boxHeight: 12, useBorderRadius: true, borderRadius: 3 } },
          tooltip: { backgroundColor: "rgba(17,17,17,.96)", borderColor: "rgba(255,255,255,.15)", borderWidth: 1, padding: 10, cornerRadius: 10, titleFont: { family: "Geist" }, bodyFont: { family: "Geist" },
            callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtNum(c.parsed.y)}` } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { font: { family: "Geist", size: 11.5 }, color: "#7a7a7a", maxRotation: 40, autoSkip: true } },
          y: { grid: { color: "rgba(255,255,255,.06)" }, border: { display: false }, ticks: { font: { family: "Geist", size: 11.5 }, color: "#7a7a7a", callback: (v) => fmtNum(v) },
            title: { display: !!spec.y_title, text: niceCol(spec.y_title), color: "#7a7a7a", font: { family: "Geist", size: 12 } } },
        },
      },
    }));
  }

  function answerCard(h) {
    const r = h.res;
    const wrap = el("div");
    const text = r[S.lang] || r.en || r.hi;
    const tm = r.timing || {};
    const confIcon = icon("dot", 10);
    wrap.innerHTML = `
      <div class="answer-text ${r.ok ? "" : "bad"}">${esc(text)}</div>
      <div class="meta">
        <span class="pill fast" title="${esc(t("model_time"))} ${tm.model}s · ${esc(t("calc_time"))} ${tm.calc}s">${icon("clock", 13)} ${tm.total?.toFixed ? tm.total.toFixed(1) : tm.total}s${tm.cached ? " · " + esc(t("cached")) : ""}</span>
        <span class="pill ${r.confidence}">${confIcon} ${esc(t("conf")[r.confidence])}</span>
        ${r.ok ? `<span class="pill">${esc(t("rows_used")(r.rows_used_count))}</span>` : ""}
      </div>
      ${(r.caveats || []).map((c) => `<div class="note warn">${icon("alert")}<span>${esc(c[S.lang])}</span></div>`).join("")}
      ${r.chart ? `<div class="chart-box"><canvas></canvas></div>` : ""}
      ${!r.chart && r.table && r.ok ? `<div class="table-scroll mini-table">${tableHTML(r.table, 30)}</div>` : ""}
      ${h.insight ? `<div class="note ai">${icon("spark")}<span>${esc(h.insight)}</span></div>` : ""}
    `;
    if (r.ok) {
      const act = el("div", "actions");
      const proofBtn = el("button", "btn sm ghost", icon("code") + esc(t("proof")));
      const explBtn = el("button", "btn sm ghost", icon("spark") + esc(t("explain")));
      const copyBtn = el("button", "btn sm ghost", icon("copy") + esc(t("copy")));
      if (h.insight) explBtn.disabled = true;
      act.append(proofBtn, explBtn, copyBtn);
      wrap.appendChild(act);
      const proof = el("div", "proof hidden");
      proof.innerHTML = `
        <div class="tabs">
          <button class="active" data-tab="code">${esc(t("tab_code"))}</button>
          <button data-tab="rows">${esc(t("tab_rows"))}</button>
          ${r.table ? `<button data-tab="result">${esc(t("tab_result"))}</button>` : ""}
          <button data-tab="plan">${esc(t("tab_plan"))}</button>
        </div>
        <div class="tab-body">
          <div data-pane="code"><pre class="code">${esc(r.code)}</pre></div>
          <div data-pane="rows" class="hidden"><div class="table-scroll">${tableHTML(r.rows_used)}</div></div>
          ${r.table ? `<div data-pane="result" class="hidden"><div class="table-scroll">${tableHTML(r.table)}</div></div>` : ""}
          <div data-pane="plan" class="hidden"><pre class="code">${esc(JSON.stringify(r.plan, null, 2))}</pre></div>
          <div class="proof-foot">${esc(t("model_time"))}: ${tm.model}s · ${esc(t("calc_time"))}: ${tm.calc}s</div>
        </div>`;
      wrap.appendChild(proof);
      proof.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => {
        proof.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
        proof.querySelectorAll("[data-pane]").forEach((p) => p.classList.toggle("hidden", p.dataset.pane !== b.dataset.tab));
      }));
      proofBtn.onclick = () => {
        const open = proof.classList.toggle("hidden");
        proofBtn.innerHTML = icon("code") + esc(open ? t("proof") : t("hide_proof"));
      };
      copyBtn.onclick = () => copyText(`${h.q}\n${text}`);
      explBtn.onclick = async () => {
        if (h.insight || explBtn.disabled) return;
        explBtn.disabled = true;
        explBtn.innerHTML = `<span class="dots"><i></i><i></i><i></i></span>`;
        const resultText = r.en + (r.table ? "\n" + r.table.columns.join(" | ") + "\n" + r.table.rows.slice(0, 10).map((x) => x.join(" | ")).join("\n") : "");
        try {
          await withKey(async () => {
            const res = await api("/api/explain", { json: { question: h.q, result: resultText, lang: S.lang } });
            h.insight = res.text;
            saveHistory();
            const n = el("div", "note ai", `${icon("spark")}<span>${esc(res.text)}</span>`);
            act.before(n);
          });
        } catch (e) { toast(errText(e), 4000); }
        explBtn.disabled = !!h.insight;
        explBtn.innerHTML = icon("spark") + esc(t("explain"));
      };
    }
    const msg = botMsg(wrap);
    if (r.chart) setTimeout(() => drawChart(wrap.querySelector("canvas"), r.chart), 0);
    return msg;
  }

  async function ask(question) {
    const q = (question ?? $("#qInput").value).trim();
    if (!q || S.busy || !S.ds) return;
    const doAsk = async () => {
      S.busy = true;
      setBusyUI();
      $("#qInput").value = "";
      autoGrow();
      const th = $("#thread");
      const um = userMsg(q);
      th.appendChild(um);
      const t0 = performance.now();
      const typing = botMsg(`<span class="typing"><span class="dots"><i></i><i></i><i></i></span><span>${esc(t("thinking"))} · <b class="tt">0.0s</b></span></span>`, true);
      th.appendChild(typing);
      scrollDown();
      const timer = setInterval(() => { const b = typing.querySelector(".tt"); if (b) b.textContent = ((performance.now() - t0) / 1000).toFixed(1) + "s"; }, 100);
      const h = { q };
      try {
        h.res = await api("/api/ask", { json: { dataset_id: S.ds.id, question: q, lang: S.lang } });
      } catch (e) {
        clearInterval(timer); typing.remove(); um.remove();
        S.busy = false; setBusyUI();
        if (needsKey(e)) { $("#qInput").value = q; autoGrow(); setBusyUI(); throw e; }
        if (e.code === "DATASET_GONE") { toast(t("err_gone"), 5000); sessionStorage.removeItem(histKey()); sessionStorage.removeItem("ds_id"); S.ds = null; renderSidebar(); showHero(); return; }
        h.err = errText(e);
      }
      clearInterval(timer);
      typing.remove();
      S.history.push(h);
      saveHistory();
      th.appendChild(h.res ? answerCard(h) : errorCard(h));
      scrollDown();
      renderSidebar();
      S.busy = false;
      setBusyUI();
    };
    try { await withKey(doAsk); } catch (e) { toast(errText(e), 4000); }
  }

  // share
  function reportText() {
    const lines = [`${t("share_title")}: ${S.ds?.name || ""}${S.ds?.is_sample ? " (SAMPLE DATA)" : ""}`, ""];
    S.history.filter((h) => h.res && h.res.ok).forEach((h) => {
      lines.push("Q: " + h.q);
      lines.push("A: " + h.res[S.lang]);
      (h.res.caveats || []).forEach((c) => lines.push("Note: " + c[S.lang]));
      lines.push("");
    });
    lines.push("Made with DataLoad (Gemma 4)");
    return lines.join("\n");
  }

  // key modal
  function openKeyModal(invalid) {
    $("#keyInput").value = "";
    $("#keyModal").classList.remove("hidden");
    if (invalid) toast(t("err_key"), 4000);
    setTimeout(() => $("#keyInput").focus(), 50);
  }
  function updateKeyBtn() {
    const b = $("#settingsBtn");
    b.classList.toggle("warn", !hasKey());
    b.style.display = S.serverKey ? "none" : "";
  }
  async function saveKey() {
    const v = $("#keyInput").value.trim();
    if (!v) return;
    S.key = v;
    localStorage.setItem("ds_key", v);
    $("#keyModal").classList.add("hidden");
    updateKeyBtn();
    toast(t("key_saved"));
    const p = S.pending;
    S.pending = null;
    if (p) {
      try { await withKey(p); } catch (e) { toast(errText(e), 4000); }
    }
  }

  // misc ui
  function setBusyUI() {
    $("#sendBtn").disabled = S.busy || !$("#qInput").value.trim();
    document.querySelectorAll("#suggest .sugg").forEach((b) => (b.disabled = S.busy));
  }
  function copyText(txt) {
    const fallback = () => {
      const ta = el("textarea");
      ta.value = txt; ta.setAttribute("readonly", ""); ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      let ok = false;
      try { ok = document.execCommand("copy"); } catch (_) { ok = false; }
      ta.remove();
      toast(ok ? t("copied") : t("err_copy"), ok ? 1800 : 3500);
    };
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(txt).then(() => toast(t("copied")), fallback);
    else fallback();
  }
  let toastId = null;
  function toast(msg, ms = 1800) {
    const tt = $("#toast");
    tt.textContent = msg;
    tt.classList.remove("hidden");
    clearTimeout(toastId);
    toastId = setTimeout(() => tt.classList.add("hidden"), ms);
  }
  function hideToast() { $("#toast").classList.add("hidden"); }
  function closeModals() {
    document.querySelectorAll(".modal").forEach((m) => m.classList.add("hidden"));
    clearInterval(photoTimerId);
    if (S.pending) S.pending = null;
  }
  function autoGrow() {
    const ta = $("#qInput");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }

  // wire up
  function bind() {
    $("#settingsBtn").onclick = () => openKeyModal();
    $("#keySave").onclick = saveKey;
    $("#keyInput").addEventListener("keydown", (e) => { if (e.key === "Enter") saveKey(); });
    document.querySelectorAll("[data-close]").forEach((b) => (b.onclick = closeModals));
    document.querySelectorAll(".modal").forEach((m) => m.addEventListener("mousedown", (e) => { if (e.target === m) closeModals(); }));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModals(); });

    $("#fileInput").onchange = (e) => { loadFile(e.target.files[0]); e.target.value = ""; };
    $("#photoInput").onchange = (e) => { openPhoto(e.target.files[0]); e.target.value = ""; };
    $("#sampleBtn").onclick = openDemos;
    $("#addRow").onclick = addPhotoRow;
    $("#useTable").onclick = usePhotoTable;
    $("#changeBtn").onclick = () => { CHARTS.forEach((c) => c.destroy()); CHARTS = []; S.ds = null; S.history = []; sessionStorage.removeItem("ds_id"); renderSidebar(); showHero(); };
    $("#previewBtn").onclick = () => {
      $("#previewTitle").textContent = `${S.ds.name} · ${S.ds.n_rows} rows`;
      $("#previewTable").innerHTML = tableHTML(S.ds.preview, 100).replace(/^<table>|<\/table>$/g, "");
      $("#previewModal").classList.remove("hidden");
    };

    const dz = $("#dropZone");
    ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    dz.addEventListener("dragleave", (e) => { if (!dz.contains(e.relatedTarget)) dz.classList.remove("drag"); });
    dz.addEventListener("drop", (e) => { e.preventDefault(); dz.classList.remove("drag"); });
    dz.addEventListener("drop", (e) => {
      const f = e.dataTransfer.files[0];
      if (!f) return;
      if (f.type.startsWith("image/")) openPhoto(f); else loadFile(f);
    });

    const ta = $("#qInput");
    ta.addEventListener("input", () => { autoGrow(); setBusyUI(); });
    ta.addEventListener("keydown", (e) => {
      if (e.isComposing || e.keyCode === 229) return; // typing with a Hindi or other IME
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); }
    });
    $("#composer").onsubmit = (e) => { e.preventDefault(); ask(); };
    $("#sendBtn").disabled = true;

    $("#waBtn").onclick = () => window.open("https://wa.me/?text=" + encodeURIComponent(reportText().slice(0, 3000)), "_blank");
    $("#dlBtn").onclick = () => {
      const a = el("a");
      a.href = URL.createObjectURL(new Blob([reportText()], { type: "text/plain;charset=utf-8" }));
      a.download = "dataload_report.txt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    };
  }

  async function init() {
    bind();
    applyLang();
    renderSidebar();
    try {
      const cfg = await api("/api/config", { method: "GET" });
      S.serverKey = cfg.server_key;
      $("#modelName").textContent = "Gemma 4 · " + cfg.model.replace(/^gemma-4-/, "").replace(/-it$/, "").toUpperCase();
    } catch (_) { /* offline */ }
    updateKeyBtn();
    const want = location.hash.slice(1);
    if (want) history.replaceState(null, "", location.pathname);
    if (want === "sample" || want === "demos") { sessionStorage.removeItem("ds_id"); return openDemos(); }
    const saved = sessionStorage.getItem("ds_id");
    if (saved) {
      try { setDataset(await api(`/api/dataset/${saved}`, { method: "GET" }), true); } catch (_) { sessionStorage.removeItem("ds_id"); }
    }
  }
  init();
})();
