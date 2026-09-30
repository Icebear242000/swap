"use strict";

// ---------- preferences (kept in this browser) ----------
const PREFS_KEY = "swap.prefs.v1";
let DEFS = null; // checkpoint definitions from the API

function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(PREFS_KEY)) || null; } catch { return null; }
}
function savePrefs(p) {
  try { localStorage.setItem(PREFS_KEY, JSON.stringify(p)); } catch { /* private mode */ }
}
function defaultPrefs() {
  const p = { required: [], importance: {}, sameOwner: false };
  for (const c of DEFS.checkpoints) {
    if (c.default_required) p.required.push(c.id);
    p.importance[c.id] = c.default_importance;
  }
  return p;
}
function prefs() { return loadPrefs() || defaultPrefs(); }
function prefQuery() {
  const p = prefs();
  const q = new URLSearchParams({
    required: p.required.join(","),
    importance: Object.entries(p.importance).map(([k, v]) => `${k}:${v}`).join(","),
    same_owner: p.sameOwner ? "true" : "false",
  });
  return q.toString();
}

// ---------- helpers ----------
const view = document.getElementById("view");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test(u || "") ? esc(u) : null);
const STATUS = { pass: "Passes", fail: "Fails", unknown: "Unknown" };

async function api(path) {
  const res = await fetch(path, { headers: { Accept: "application/json" } });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}
function setNav(name) {
  document.querySelectorAll("[data-nav]").forEach((a) => {
    if (a.dataset.nav === name) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
}
function render(html) { view.innerHTML = html; view.focus({ preventScroll: true }); }
function loading(text) { render(`<p class="muted">${esc(text)}</p>`); }
function sampleBadge(p) { return p.source === "demo" ? `<span class="tag sample-badge">Sample</span>` : ""; }
function mark(status) { return `<span class="mark ${esc(status)}">${STATUS[status] || esc(status)}</span>`; }

// ---------- barcode scanning ----------
let stopScan = null;

async function startScan(onCode) {
  const wrap = document.querySelector(".video-wrap");
  const video = wrap.querySelector("video");
  const status = document.getElementById("scan-status");
  wrap.classList.add("on");
  if ("BarcodeDetector" in window) {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      video.srcObject = stream;
      await video.play();
      const detector = new window.BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
      let live = true;
      stopScan = () => { live = false; stream.getTracks().forEach((t) => t.stop()); wrap.classList.remove("on"); };
      const tick = async () => {
        if (!live) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length) { stopScan(); onCode(codes[0].rawValue); return; }
        } catch { /* frame not ready */ }
        requestAnimationFrame(tick);
      };
      tick();
      return;
    } catch (e) {
      status.textContent = "Camera unavailable: " + e.message;
      wrap.classList.remove("on");
      return;
    }
  }
  // Fallback for browsers without BarcodeDetector (e.g. iOS Safari).
  try {
    await loadScript("https://cdn.jsdelivr.net/npm/@zxing/library@0.21.3/umd/index.min.js");
    const reader = new window.ZXing.BrowserMultiFormatReader();
    stopScan = () => { reader.reset(); wrap.classList.remove("on"); };
    reader.decodeFromVideoDevice(null, video, (result) => {
      if (result) { stopScan(); onCode(result.getText()); }
    });
  } catch (e) {
    status.textContent = "Scanning isn't supported here. Type the barcode instead.";
    wrap.classList.remove("on");
  }
}
function loadScript(src) {
  return new Promise((resolve, reject) => {
    if ([...document.scripts].some((s) => s.src === src)) return resolve();
    const s = document.createElement("script");
    s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("script failed"));
    document.head.appendChild(s);
  });
}

// ---------- views ----------
async function scanView() {
  setNav("scan");
  let samples = [];
  try { samples = (await api("/api/samples")).samples; } catch { /* optional */ }
  render(`
    <h1>What's in your cart?</h1>
    <p class="lede">Scan a toothpaste to see who really owns it, what the public record says,
      and which swaps pass the checkpoints you care about.</p>
    <section class="scanner" aria-label="Find a product">
      <div class="video-wrap"><video playsinline muted></video></div>
      <button class="btn block" id="scan-btn">Scan a barcode</button>
      <p id="scan-status" class="small muted" role="status"></p>
      <div class="or">or type it</div>
      <form class="row" id="code-form">
        <input class="field" id="code" inputmode="numeric" autocomplete="off"
          placeholder="Barcode, e.g. 0035000xxxxx" aria-label="Barcode">
        <button class="btn" type="submit">Look up</button>
      </form>
      <div class="or">or search products we've already checked</div>
      <input class="field" style="width:100%" id="q" type="search" placeholder="Brand or product name"
        aria-label="Search products">
      <ul class="list" id="results"></ul>
    </section>
    ${samples.length ? `
      <h2>Try a sample</h2>
      <p class="small muted">Fictional products and records, so you can see every kind of result.</p>
      <ul class="list">${samples.map((s) => `
        <li><a href="#/p/${esc(s.barcode)}"><span class="name">${esc(s.name)}</span>
          <span class="tag">Sample</span></a></li>`).join("")}
      </ul>` : ""}
  `);
  const go = (code) => { location.hash = `#/p/${encodeURIComponent(code.trim())}`; };
  document.getElementById("scan-btn").onclick = () => startScan(go);
  document.getElementById("code-form").onsubmit = (e) => {
    e.preventDefault();
    const code = document.getElementById("code").value.replace(/\D/g, "");
    if (code.length >= 6) go(code);
  };
  let t;
  document.getElementById("q").oninput = (e) => {
    clearTimeout(t);
    const q = e.target.value.trim();
    const out = document.getElementById("results");
    if (q.length < 2) { out.innerHTML = ""; return; }
    t = setTimeout(async () => {
      try {
        const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
        out.innerHTML = results.length ? results.map((r) => `
          <li><a href="#/p/${esc(r.barcode)}"><span><span class="name">${esc(r.name)}</span>
            <span class="meta"> ${esc(r.brand || "")}</span></span>${sampleBadge(r)}</a></li>`).join("")
          : `<li class="small muted" style="padding:.7rem 0">No matches. Scan it to add it.</li>`;
      } catch (err) { out.innerHTML = `<li class="msg error">${esc(err.message)}</li>`; }
    }, 200);
  };
}

function priceLine(price) {
  if (!price) return "Price unknown";
  if (price.per_oz != null) return `$${price.per_oz.toFixed(2)} per ${esc(price.unit)}`;
  return `$${price.price.toFixed(2)}`;
}

async function productView(barcode) {
  setNav("");
  loading("Checking the records…");
  let r;
  try { r = await api(`/api/products/${encodeURIComponent(barcode)}?${prefQuery()}`); }
  catch (e) {
    render(`<div class="msg error">${esc(e.message)}</div>
      <p class="small muted">Open Beauty Facts is built by volunteers. You can
      <a href="https://world.openbeautyfacts.org/" rel="noopener">add this product there</a>,
      and it will show up here on the next scan.</p>
      <p><a class="btn ghost" href="#/">Scan something else</a></p>`);
    return;
  }
  const p = r.product;
  const img = safeUrl(p.image_url);
  const failed = r.failed_required;
  const unverified = r.unverified_required;
  const banner = failed.length
    ? `<div class="banner fail" role="alert"><strong>Fails ${failed.length} of your required checkpoints</strong>
       ${failed.map(esc).join("<br>")}</div>`
    : unverified.length
      ? `<div class="banner recall"><strong>Couldn't verify: ${unverified.map(esc).join(", ")}</strong>
         Missing data counts as unknown, never as a pass.</div>`
      : `<div class="banner good"><strong>Passes all your required checkpoints</strong>
         There may still be a better swap below.</div>`;
  const recall = r.recall ? `
    <div class="banner recall"><strong>${r.recall.level === "product" ? "Recall for this brand" : "Recall at the parent company"}
      (${esc(r.recall.classification || "unclassified")}, ${esc(fmtDate(r.recall.date))})</strong>
      ${esc(r.recall.reason || "")} ${safeUrl(r.recall.url) ? `<a href="${safeUrl(r.recall.url)}" rel="noopener">FDA record</a>` : ""}</div>` : "";
  const own = r.ownership;
  render(`
    <div class="product">
      ${img ? `<img class="thumb" src="${img}" alt="">` : `<div class="thumb" aria-hidden="true">🪥</div>`}
      <div>
        <h1>${esc(p.name)}${sampleBadge(p)}</h1>
        <div class="meta">${esc(p.brand || "Unknown brand")}${p.quantity_text ? `, ${esc(p.quantity_text)}` : ""}</div>
        <div class="meta">${priceLine(r.price)}${r.price && r.price.source === "openprices" ? ` (${r.price.reports} price reports)` : ""}</div>
      </div>
    </div>
    ${r.supported_category ? "" : `<div class="msg">This isn't a toothpaste, so only the general checkpoints apply and we can't suggest swaps yet.</div>`}
    ${banner}
    ${recall}
    <section class="facts" aria-labelledby="facts-title">
      <h2 class="facts-title" id="facts-title">Swap Facts</h2>
      <div class="facts-head"><span>Checkpoint</span><span>Result</span></div>
      ${r.checkpoints.map((c) => `
        <details class="fact">
          <summary>
            <span class="fact-name">${esc(c.label)}${prefs().required.includes(c.id) ? " (required)" : ""}
              <span class="fact-sum">${esc(c.summary)}</span></span>
            ${mark(c.status)}
          </summary>
          ${c.evidence.length ? `<ul class="evidence">${c.evidence.map((e) => `
            <li>${esc(e.text)} ${e.source ? `<span class="src">(${safeUrl(e.url) ? `<a href="${safeUrl(e.url)}" rel="noopener">${esc(e.source)}</a>` : esc(e.source)})</span>` : ""}</li>`).join("")}</ul>`
            : `<p class="evidence muted">No further records.</p>`}
        </details>`).join("")}
      <div class="facts-foot">Tap a checkpoint to see the records behind it.
        ${safeUrl(p.source_url) ? `Product data from <a href="${safeUrl(p.source_url)}" rel="noopener">Open Beauty Facts</a>.` : ""}</div>
    </section>
    <section class="owners">
      <h2>Who owns this</h2>
      ${own.known ? `<ol>${own.chain.map((l, i) => `
        <li><strong>${esc(l.name)}</strong> <span class="kind">${i === 0 ? "brand" : "owned by"}
          ${i > 0 && l.source ? ` (${safeUrl(l.url) ? `<a href="${safeUrl(l.url)}" rel="noopener">${esc(sourceName(l.source))}</a>` : esc(sourceName(l.source))})` : ""}</span></li>`).join("")}</ol>
        ${own.note ? `<p class="small muted">${esc(own.note)}</p>` : ""}
        ${own.siblings.length ? `<p class="small">Also owned by ${esc(own.chain[own.chain.length - 1].name)}:
          ${own.siblings.map(esc).join(", ")}. Switching to these keeps your money with the same company.</p>` : ""}`
      : `<p class="muted">We don't have ownership records for this brand yet.</p>`}
    </section>
    <p style="margin-top:1.6rem"><a class="btn block" href="#/p/${esc(p.barcode)}/swaps">See better swaps</a></p>
    ${p.ingredients_text ? `<details style="margin-top:1rem"><summary class="small">Full ingredient list</summary>
      <p class="small muted">${esc(p.ingredients_text)}</p></details>` : ""}
  `);
}

function sourceName(s) {
  if (s.startsWith("override")) return s.replace(/^override:\s*/, "");
  if (s === "demo") return "sample data";
  if (s === "wikidata") return "Wikidata";
  return s;
}

function fmtDate(d) {
  if (!d) return "date unknown";
  const s = String(d);
  return /^\d{8}$/.test(s) ? `${s.slice(0, 4)}-${s.slice(4, 6)}-${s.slice(6)}` : s;
}

async function swapsView(barcode) {
  setNav("");
  loading("Ranking alternatives…");
  let r;
  try { r = await api(`/api/products/${encodeURIComponent(barcode)}/alternatives?${prefQuery()}`); }
  catch (e) { render(`<div class="msg error">${esc(e.message)}</div>`); return; }
  if (!r.category) {
    render(`<h1>Better swaps</h1><div class="msg">We only compare toothpastes so far.</div>
      <p><a href="#/p/${esc(barcode)}">Back to the product</a></p>`);
    return;
  }
  render(`
    <p class="small"><a href="#/p/${esc(barcode)}">Back to your product</a></p>
    <h1>Better swaps</h1>
    <p class="lede">Ranked by how well each does on the checkpoints you weight most.
      <a href="#/checkpoints">Change your checkpoints</a></p>
    ${r.shown.length ? r.shown.map((a, i) => `
      <article class="swap">
        <div class="swap-top">
          <span class="rank">${i + 1}</span>
          <div style="flex:1">
            <a class="swap-name" href="#/p/${esc(a.product.barcode)}">${esc(a.product.name)}</a>${sampleBadge(a.product)}
            <div class="meta">${esc(a.owner && a.owner !== a.product.brand ? `${a.product.brand}, owned by ${a.owner}` : a.product.brand || "")}
              ${a.better ? "" : " (no better than yours)"}</div>
          </div>
          <div class="price">${a.price && a.price.per_oz != null ? `$${a.price.per_oz.toFixed(2)}<small>per ${esc(a.price.unit)}</small>` : `<small>Price unknown</small>`}</div>
        </div>
        <div class="marks">${a.checkpoints.map((c) => `<span class="mark ${esc(c.status)}" title="${esc(c.summary)}">${esc(c.label)}: ${STATUS[c.status]}</span>`).join("")}</div>
        ${a.recall ? `<p class="small" style="margin:.5rem 0 0"><span class="mark unknown">Recall</span> ${esc(a.recall.classification || "")} recall, ${esc(fmtDate(a.recall.date))}</p>` : ""}
        ${a.unverified.length ? `<p class="small muted" style="margin:.5rem 0 0">Couldn't verify: ${a.unverified.map(esc).join(", ")}</p>` : ""}
      </article>`).join("")
      : `<div class="msg">Nothing passes all your required checkpoints yet. Try making one optional, or load more products.</div>`}
    ${r.hidden.length ? `
      <h2>Hidden by your checkpoints</h2>
      ${r.hidden.map((h) => `
        <div class="hidden-item">
          <a class="swap-name" href="#/p/${esc(h.product.barcode)}">${esc(h.product.name)}</a>${sampleBadge(h.product)}
          <ul>${h.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
        </div>`).join("")}` : ""}
  `);
}

function checkpointsView() {
  setNav("checkpoints");
  const p = prefs();
  const levels = DEFS.importance_levels;
  render(`
    <h1>Your checkpoints</h1>
    <p class="lede">Required checkpoints hide any product that fails them. Importance decides the
      order of everything else. Saved on this device.</p>
    <form id="cp-form">
      ${DEFS.checkpoints.map((c) => `
        <div class="cp">
          <h3>${esc(c.label)}</h3>
          <p>${esc(c.question)}${c.categories ? ` Applies to ${esc(c.categories.join(", "))}.` : ""}</p>
          <div class="cp-controls">
            <label class="switch"><input type="checkbox" name="req-${esc(c.id)}" ${p.required.includes(c.id) ? "checked" : ""}> Required</label>
            <fieldset class="seg"><legend class="sr">Importance</legend>
              ${levels.map((l) => `<label><input type="radio" name="imp-${esc(c.id)}" value="${esc(l)}" ${p.importance[c.id] === l ? "checked" : ""}><span>${esc(l[0].toUpperCase() + l.slice(1))}</span></label>`).join("")}
            </fieldset>
          </div>
        </div>`).join("")}
      <div class="cp">
        <label class="switch"><input type="checkbox" name="same-owner" ${p.sameOwner ? "checked" : ""}>
          Show swaps owned by the same parent company as my product</label>
      </div>
      <p class="small muted" id="saved" role="status"></p>
      <button type="button" class="btn ghost" id="reset">Reset to defaults</button>
    </form>
  `);
  const form = document.getElementById("cp-form");
  form.onchange = () => {
    const next = { required: [], importance: {}, sameOwner: form["same-owner"].checked };
    for (const c of DEFS.checkpoints) {
      if (form[`req-${c.id}`].checked) next.required.push(c.id);
      next.importance[c.id] = form[`imp-${c.id}`].value;
    }
    savePrefs(next);
    document.getElementById("saved").textContent = "Saved.";
  };
  document.getElementById("reset").onclick = () => { savePrefs(defaultPrefs()); checkpointsView(); };
}

// ---------- router ----------
async function route() {
  if (stopScan) { stopScan(); stopScan = null; }
  if (!DEFS) DEFS = await api("/api/checkpoints");
  const h = location.hash.replace(/^#/, "") || "/";
  let m;
  if ((m = h.match(/^\/p\/(\d{6,14})\/swaps$/))) return swapsView(m[1]);
  if ((m = h.match(/^\/p\/(\d{6,14})$/))) return productView(m[1]);
  if (h === "/checkpoints") return checkpointsView();
  return scanView();
}
window.addEventListener("hashchange", route);
route().catch((e) => render(`<div class="msg error">${esc(e.message)}</div>`));
