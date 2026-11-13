"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
const store = {
  get: (k, d) => { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set: (k, v) => { try { localStorage.setItem(k, v); } catch {} },
};
const S = {view: "products", page: 1, sort: "-updated_at", status: "", stats: null, stock: null, editing: null, cats: [], renaming: null, actBefore: null};
let currency = store.get("stockly.currency", "USD"), reqId = 0;
const money = n => { try { return new Intl.NumberFormat(undefined, {style: "currency", currency}).format(n); } catch { return Number(n).toFixed(2); } };
const num = n => new Intl.NumberFormat().format(n);
const rtf = new Intl.RelativeTimeFormat(undefined, {numeric: "auto"});
const STATUS = {ok: "In stock", low: "Low", out: "Out"};
const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function ago(iso) {
  const d = (new Date(iso) - Date.now()) / 1000, a = Math.abs(d);
  if (a < 45) return "just now";
  if (a < 3600) return rtf.format(Math.round(d / 60), "minute");
  if (a < 86400) return rtf.format(Math.round(d / 3600), "hour");
  if (a < 2592000) return rtf.format(Math.round(d / 86400), "day");
  return new Date(iso).toLocaleDateString();
}
const timeTag = iso => `<time datetime="${esc(iso)}" title="${esc(new Date(iso).toLocaleString())}">${ago(iso)}</time>`;

function toast(msg, type = "") {
  const t = $("#toast");
  t.textContent = msg; t.className = "show " + type;
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), type === "err" ? 4000 : 2200);
}

class ApiErr extends Error { constructor(m, details) { super(m); this.details = details; } }
async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch("/api" + path, {headers: {"Content-Type": "application/json"}, ...opts, body: opts.body ? JSON.stringify(opts.body) : undefined});
  } catch { throw new ApiErr("Network error — is the server running?"); }
  if (res.status === 204) return null;
  let data;
  try { data = await res.json(); } catch { throw new ApiErr(`Server error (${res.status}) — check the server logs`); }
  if (!res.ok) throw new ApiErr(data.error || "Request failed", data.details);
  return data;
}
const busy = async (btn, fn) => { if (btn) btn.disabled = true; try { return await fn(); } finally { if (btn) btn.disabled = false; } };

function clearErrors(form) { $$(".ferr", form).forEach(e => e.textContent = ""); const g = $(".err", form); if (g) g.textContent = ""; }
function showErrors(form, err) {
  clearErrors(form);
  let msg = err.message, any = false;
  for (const [k, v] of Object.entries(err.details || {})) {
    const el = $(`[data-err="${k}"]`, form);
    if (el) { el.textContent = v; any = true; }
  }
  if (any) msg = "Please fix the highlighted fields.";
  const g = $(".err", form); if (g) g.textContent = msg;
}

function confirmBox(title, message, okText = "Delete") {
  return new Promise(resolve => {
    $("#cfTitle").textContent = title; $("#cfMsg").textContent = message; $("#cfOk").textContent = okText;
    const d = $("#dlgConfirm"); d.returnValue = "";
    d.addEventListener("close", () => resolve(d.returnValue === "ok"), {once: true});
    d.showModal();
  });
}

/* ---------------------------------------------------------------- theme / currency / views */
const THEMES = ["auto", "light", "dark"];
function applyTheme(t) {
  if (t === "auto") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  const b = $("#btnTheme"); b.textContent = {auto: "◐", light: "☀", dark: "☾"}[t]; b.title = `Theme: ${t}`; b.dataset.t = t;
}
$("#btnTheme").onclick = e => {
  const t = THEMES[(THEMES.indexOf(e.currentTarget.dataset.t) + 1) % 3];
  store.set("stockly.theme", t); applyTheme(t);
};
$("#currency").onchange = e => { currency = e.target.value; store.set("stockly.currency", currency); renderStats(); loadProducts(); };

function switchView(v) {
  S.view = v;
  $("#viewProducts").hidden = v !== "products"; $("#viewActivity").hidden = v !== "activity";
  $$(".tab").forEach(t => t.setAttribute("aria-selected", t.dataset.view === v));
  history.replaceState(null, "", "#" + v);
  if (v === "activity") loadActivity().catch(e => toast(e.message, "err"));
}
$$(".tab").forEach(t => t.onclick = () => switchView(t.dataset.view));

/* ---------------------------------------------------------------- stats */
async function loadStats() { S.stats = await api("/stats"); renderStats(); }
function renderStats() {
  const s = S.stats; if (!s) return;
  const cards = [
    ["all", "Products", num(s.products), ""], [null, "Inventory value", money(s.inventory_value), ""],
    ["low", "Low stock", num(s.low_stock), s.low_stock ? "warn" : ""], ["out", "Out of stock", num(s.out_of_stock), s.out_of_stock ? "bad" : ""],
  ];
  $("#stats").innerHTML = cards.map(([f, l, v, c]) => {
    const body = `<small>${l}</small><b>${v}</b>`;
    if (f === null) return `<div class="stat">${body}</div>`;
    const active = (S.status || "all") === f ? " active" : "";
    return `<button class="stat ${c}${active}" data-act="stat" data-f="${f}">${body}</button>`;
  }).join("");
}

/* ---------------------------------------------------------------- categories */
async function loadCats() { S.cats = await api("/categories"); fillCatSelects(); renderCats(); }
function fillCatSelects() {
  const opts = S.cats.map(c => `<option value="${c.id}">${esc(c.name)}</option>`).join("");
  const cf = $("#catFilter"), cur = cf.value;
  cf.innerHTML = `<option value="">All categories</option><option value="0">Uncategorized</option>${opts}`;
  cf.value = [...cf.options].some(o => o.value === cur) ? cur : "";
  const pc = $("#fProduct [name=category_id]"), pcur = pc.value;
  pc.innerHTML = `<option value="">No category</option>${opts}`; pc.value = pcur;
}
function renderCats() {
  $("#catList").innerHTML = S.cats.length ? S.cats.map(c => S.renaming === c.id
    ? `<li><input class="rn" data-rn="${c.id}" value="${esc(c.name)}" maxlength="80" aria-label="Category name"><span class="row"><button type="button" class="btn primary sm" data-act="rn-save" data-id="${c.id}">Save</button><button type="button" class="btn ghost sm" data-act="rn-cancel">Cancel</button></span></li>`
    : `<li><span>${esc(c.name)}<small title="Products in this category">${c.product_count}</small></span><span class="row"><button type="button" class="btn ghost sm" data-act="rn-start" data-id="${c.id}">Rename</button><button type="button" class="btn ghost sm danger" data-act="cat-del" data-id="${c.id}" data-name="${esc(c.name)}" data-count="${c.product_count}">Delete</button></span></li>`
  ).join("") : `<li class="muted">No categories yet — add your first below.</li>`;
  $(".rn", $("#catList"))?.focus();
}
$("#fCat").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target;
  try {
    await busy(e.submitter, () => api("/categories", {method: "POST", body: {name: f.name.value}}));
    f.reset(); $("#cErr").textContent = ""; await loadCats();
  } catch (err) { $("#cErr").textContent = err.details?.name ? `Name ${err.details.name}` : err.message; }
});
$("#catList").addEventListener("keydown", e => {
  if (!e.target.classList.contains("rn")) return;
  if (e.key === "Enter") { e.preventDefault(); saveRename(e.target.dataset.rn, e.target.value); }
  if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); S.renaming = null; renderCats(); }
});
async function saveRename(id, name) {
  try { await api(`/categories/${id}`, {method: "PUT", body: {name}}); S.renaming = null; $("#cErr").textContent = ""; await loadCats(); refresh(); }
  catch (err) { $("#cErr").textContent = err.details?.name ? `Name ${err.details.name}` : err.message; }
}

/* ---------------------------------------------------------------- products */
function filterParams() {
  const p = new URLSearchParams();
  const q = $("#q").value.trim(); if (q) p.set("q", q);
  if ($("#catFilter").value !== "") p.set("category_id", $("#catFilter").value);
  if (S.status) p.set("status", S.status);
  p.set("sort", S.sort);
  return p;
}
function renderSortHeaders() {
  $$("th[data-sort]").forEach(th => th.setAttribute("aria-sort",
    S.sort.replace("-", "") !== th.dataset.sort ? "none" : S.sort.startsWith("-") ? "descending" : "ascending"));
}
const skeleton = n => Array.from({length: n}, () => `<tr class="sk"><td colspan="6"><div class="bar"></div></td></tr>`).join("");
function rowHtml(i) {
  return `<tr>
    <td class="prod"><div class="pname">${esc(i.name)}</div><div class="sku">${esc(i.sku)}</div></td>
    <td data-label="Category">${i.category ? `<span class="pill">${esc(i.category.name)}</span>` : `<span class="muted">—</span>`}</td>
    <td data-label="Stock" class="num"><span class="qty">${num(i.quantity)}</span><span class="badge ${i.status}">${STATUS[i.status]}</span></td>
    <td data-label="Price" class="num">${money(i.price)}</td>
    <td data-label="Value" class="num">${money(i.value)}</td>
    <td class="acts"><div class="row">
      <button class="btn ghost sm" data-act="stock" data-id="${i.id}">Stock</button>
      <button class="btn ghost sm" data-act="edit" data-id="${i.id}">Edit</button>
      <button class="btn ghost sm danger" data-act="del" data-id="${i.id}" data-name="${esc(i.name)}">Delete</button>
    </div></td></tr>`;
}
async function loadProducts() {
  const id = ++reqId, p = filterParams();
  p.set("page", S.page); p.set("per_page", 15);
  $("#btnExport").href = "/api/products/export.csv?" + filterParams();
  renderSortHeaders();
  if (!$("#rows").children.length) $("#rows").innerHTML = skeleton(6);
  let d;
  try { d = await api("/products?" + p); }
  catch (err) {
    if (id !== reqId) return;
    $("#rows").innerHTML = ""; $("#empty").hidden = false;
    $("#empty").innerHTML = `${esc(err.message)}<br><button class="btn ghost" data-act="retry">Retry</button>`;
    return;
  }
  if (id !== reqId) return;
  if (d.pages > 0 && d.page > d.pages) { S.page = d.pages; return loadProducts(); }
  $("#rows").innerHTML = d.items.map(rowHtml).join("");
  const filtered = $("#q").value.trim() || $("#catFilter").value !== "" || S.status;
  $("#empty").hidden = d.items.length > 0;
  if (!d.items.length) $("#empty").innerHTML = filtered
    ? `No products match your filters.<br><button class="btn ghost" data-act="clear">Clear filters</button>`
    : `No products yet.<br><button class="btn primary" data-act="new">+ Add your first product</button>`;
  $("#pageInfo").textContent = d.total ? `Page ${d.page} of ${d.pages} · ${num(d.total)} item${d.total === 1 ? "" : "s"}` : "";
  $("#prev").disabled = d.page <= 1; $("#next").disabled = d.page >= d.pages;
}
const refresh = () => Promise.all([loadStats(), loadProducts(), loadCats()]).catch(e => toast(e.message, "err"));
const resetPage = () => { S.page = 1; loadProducts(); renderStats(); };

$("#q").addEventListener("input", debounce(resetPage));
$("#catFilter").onchange = resetPage;
$("#statusFilter").onchange = e => { S.status = e.target.value; resetPage(); };
$("#prev").onclick = () => { S.page--; loadProducts(); };
$("#next").onclick = () => { S.page++; loadProducts(); };
$$("th[data-sort]").forEach(th => th.onclick = () => {
  const k = th.dataset.sort; S.sort = S.sort === k ? "-" + k : k; resetPage();
});

/* ---------------------------------------------------------------- product dialog */
function openProduct(p = null) {
  S.editing = p?.id ?? null;
  const f = $("#fProduct"); f.reset(); clearErrors(f);
  $("#dlgTitle").textContent = p ? "Edit product" : "New product";
  $("#qtyWrap").hidden = !!p; $("#qtyHint").hidden = !p;
  if (p) {
    f.sku.value = p.sku; f.name.value = p.name; f.description.value = p.description || "";
    f.category_id.value = p.category?.id ?? ""; f.price.value = p.price; f.reorder_level.value = p.reorder_level;
  }
  $("#dlgProduct").showModal(); f.sku.focus();
}
$("#fProduct").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target, editing = S.editing;
  const body = {sku: f.sku.value, name: f.name.value, description: f.description.value,
    category_id: f.category_id.value ? +f.category_id.value : null, price: f.price.value, reorder_level: f.reorder_level.value};
  if (editing === null) body.quantity = f.quantity.value;
  try {
    await busy(e.submitter, () => api(editing ? `/products/${editing}` : "/products", {method: editing ? "PUT" : "POST", body}));
    $("#dlgProduct").close(); toast(editing ? "Product updated" : "Product added"); refresh();
  } catch (err) { showErrors(f, err); }
});

/* ---------------------------------------------------------------- stock dialog */
function stockPlan() {
  const f = $("#fStock"), mode = f.mode.value, raw = f.amount.value.trim(), n = Number(raw), cur = S.stock.quantity;
  if (raw === "") return {valid: false, msg: ""};
  if (!Number.isInteger(n) || n < 0) return {valid: false, msg: "Enter a whole number."};
  if (mode !== "set" && n === 0) return {valid: false, msg: "Enter a quantity above 0."};
  const after = mode === "add" ? cur + n : mode === "remove" ? cur - n : n;
  if (after < 0) return {valid: false, msg: `Not enough stock — only ${num(cur)} available.`};
  if (after > 1e9) return {valid: false, msg: "Quantity too large."};
  if (after === cur) return {valid: false, msg: "That matches the current stock."};
  return {valid: true, msg: `${num(cur)} → ${num(after)}`};
}
function updatePlan() {
  const p = stockPlan(), el = $("#preview");
  el.textContent = p.msg; el.classList.toggle("bad", !p.valid && !!p.msg); $("#sApply").disabled = !p.valid;
}
function paintStock() {
  const p = S.stock;
  $("#curQty").textContent = num(p.quantity);
  const b = $("#curBadge"); b.className = "badge " + p.status; b.textContent = STATUS[p.status];
}
async function openStock(id) {
  const f = $("#fStock"); f.reset(); $("#sErr").textContent = ""; $("#preview").textContent = ""; $("#sApply").disabled = true;
  S.stock = await api(`/products/${id}`);
  $("#stockTitle").textContent = S.stock.name; paintStock();
  $("#dlgStock").showModal(); f.amount.focus();
  loadMoves();
}
async function loadMoves() {
  try {
    const m = await api(`/products/${S.stock.id}/movements?limit=30`);
    $("#moves").innerHTML = m.map(x => `<li><span class="chg ${x.change > 0 ? "pos" : "neg"}">${x.change > 0 ? "+" : ""}${num(x.change)}</span><span class="why">${esc(x.reason) || "—"}</span><span>→ ${num(x.quantity_after)}</span>${timeTag(x.created_at)}</li>`).join("")
      || `<li class="muted">No movements yet</li>`;
  } catch (err) { $("#moves").innerHTML = `<li class="muted">${esc(err.message)}</li>`; }
}
$("#fStock").addEventListener("input", updatePlan);
$("#fStock").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target, p = stockPlan(); if (!p.valid) return;
  const n = Number(f.amount.value), mode = f.mode.value;
  const body = {reason: f.reason.value, ...(mode === "set" ? {set: n} : {change: mode === "add" ? n : -n})};
  try {
    S.stock = await busy(e.submitter, () => api(`/products/${S.stock.id}/adjust`, {method: "POST", body}));
    paintStock(); f.amount.value = ""; f.reason.value = ""; updatePlan(); $("#sErr").textContent = "";
    toast("Stock updated"); loadMoves(); refresh();
  } catch (err) {
    $("#sErr").textContent = err.message;
    if (err.message.startsWith("Insufficient")) { S.stock = await api(`/products/${S.stock.id}`); paintStock(); updatePlan(); }
  }
});

/* ---------------------------------------------------------------- activity */
const feedItem = m => `<li><span class="chg ${m.change > 0 ? "pos" : "neg"}">${m.change > 0 ? "+" : ""}${num(m.change)}</span>
  <div class="fmain"><b>${esc(m.product_name)}</b> <span class="sku">${esc(m.product_sku)}</span><div class="muted">${esc(m.reason) || "No reason given"} · now ${num(m.quantity_after)}</div></div>${timeTag(m.created_at)}</li>`;
async function loadActivity(more = false) {
  const feed = $("#feed"), p = new URLSearchParams({limit: 30});
  if (more && S.actBefore) p.set("before", S.actBefore);
  const btn = $("#moreAct");
  const d = await busy(btn, () => api("/movements?" + p));
  const html = d.items.map(feedItem).join("");
  if (more) feed.insertAdjacentHTML("beforeend", html); else feed.innerHTML = html;
  S.actBefore = d.next_before; btn.hidden = !d.has_more; $("#feedEmpty").hidden = feed.children.length > 0;
}
$("#moreAct").onclick = () => loadActivity(true).catch(e => toast(e.message, "err"));

/* ---------------------------------------------------------------- actions */
document.addEventListener("click", async e => {
  const t = e.target.closest("button[data-act], button[data-close]"); if (!t) return;
  if (t.dataset.close !== undefined) return t.closest("dialog").close();
  const {act, id, name} = t.dataset;
  try {
    if (act === "edit") openProduct(await api(`/products/${id}`));
    else if (act === "stock") await openStock(id);
    else if (act === "new") openProduct();
    else if (act === "retry") loadProducts();
    else if (act === "chip") { const f = $("#fStock"); f.amount.value = t.dataset.n; updatePlan(); f.amount.focus(); }
    else if (act === "clear") { $("#q").value = ""; $("#catFilter").value = ""; $("#statusFilter").value = ""; S.status = ""; resetPage(); }
    else if (act === "stat") { S.status = t.dataset.f === "all" ? "" : t.dataset.f; $("#statusFilter").value = S.status; switchView("products"); resetPage(); }
    else if (act === "del" && await confirmBox(`Delete “${name}”?`, "This also removes its stock history and cannot be undone.")) {
      await api(`/products/${id}`, {method: "DELETE"}); toast("Product deleted"); refresh();
    } else if (act === "cat-del" && await confirmBox(`Delete category “${name}”?`,
      +t.dataset.count ? `${t.dataset.count} product(s) will become uncategorized. The products themselves are kept.` : "This category is empty.")) {
      await api(`/categories/${id}`, {method: "DELETE"}); toast("Category deleted"); refresh();
    } else if (act === "rn-start") { S.renaming = +id; renderCats(); }
    else if (act === "rn-cancel") { S.renaming = null; renderCats(); }
    else if (act === "rn-save") saveRename(id, $(`[data-rn="${id}"]`).value);
  } catch (err) { toast(err.message, "err"); }
});
$("#btnNew").onclick = () => openProduct();
$("#btnCats").onclick = () => { S.renaming = null; renderCats(); $("#cErr").textContent = ""; $("#dlgCats").showModal(); };
$$("dialog[data-backdrop]").forEach(d => d.addEventListener("click", e => { if (e.target === d) d.close(); }));
document.addEventListener("keydown", e => {
  if (e.target.matches("input,textarea,select") || e.metaKey || e.ctrlKey || e.altKey || $("dialog[open]")) return;
  if (e.key === "/") { e.preventDefault(); switchView("products"); $("#q").focus(); }
  else if (e.key === "n") { e.preventDefault(); openProduct(); }
});

/* ---------------------------------------------------------------- init */
(async () => {
  applyTheme(store.get("stockly.theme", "auto"));
  if (![...$("#currency").options].some(o => o.value === currency)) currency = "USD";
  $("#currency").value = currency;
  await Promise.all([loadCats(), loadStats()]);
  if (location.hash === "#activity") switchView("activity");
  await loadProducts();
})().catch(e => toast(e.message, "err"));
