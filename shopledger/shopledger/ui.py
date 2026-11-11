"""The single-page interface served by shopledger.web (kept in Python so packaging is trivial)."""

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ShopLedger</title>
<style>
  :root { --bg:#f3f5fa; --card:#ffffff; --text:#1b2433; --muted:#667085; --line:#e3e8f0;
          --brand:#0f766e; --on-brand:#ffffff; --good:#15803d; --warn:#b45309; --bad:#b91c1c;
          --chip:#eef2f7; --r:14px; }
  @media (prefers-color-scheme: dark) {
    :root { --bg:#0e131b; --card:#161d29; --text:#e8edf5; --muted:#93a0b4; --line:#243044;
            --brand:#2dd4bf; --on-brand:#04201d; --good:#4ade80; --warn:#fbbf24; --bad:#f87171; --chip:#1e2837; }
  }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--text); font:15px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  header { background:var(--card); border-bottom:1px solid var(--line); position:sticky; top:0; z-index:5; }
  .bar { max-width:960px; margin:0 auto; padding:12px 16px 0; display:flex; align-items:center; justify-content:space-between; }
  .logo { font-weight:800; font-size:19px; letter-spacing:-.3px; }
  .logo span { color:var(--brand); }
  .cur { color:var(--muted); font-size:13px; }
  nav { max-width:960px; margin:0 auto; display:flex; gap:4px; padding:8px 12px 0; overflow-x:auto; }
  nav button { background:none; border:0; color:var(--muted); font:inherit; font-weight:600; padding:10px 14px;
               border-bottom:3px solid transparent; cursor:pointer; white-space:nowrap; }
  nav button.on { color:var(--brand); border-bottom-color:var(--brand); }
  main { max-width:960px; margin:0 auto; padding:16px; }
  .grid { display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }
  .card { background:var(--card); border:1px solid var(--line); border-radius:var(--r); padding:16px; margin-bottom:12px; }
  .card h3 { margin:0 0 10px; font-size:15px; }
  .kpi .l { color:var(--muted); font-size:13px; }
  .kpi .v { font-size:24px; font-weight:800; margin-top:2px; letter-spacing:-.4px; }
  .good { color:var(--good); } .bad { color:var(--bad); } .warn { color:var(--warn); } .muted { color:var(--muted); }
  label { display:block; font-size:13px; color:var(--muted); margin:10px 0 4px; font-weight:600; }
  input, select { width:100%; padding:11px 12px; border:1px solid var(--line); border-radius:10px; background:var(--bg);
                  color:var(--text); font:inherit; }
  input:focus, select:focus { outline:2px solid var(--brand); outline-offset:0; }
  .row { display:flex; gap:10px; } .row > * { flex:1; } .end { justify-content:flex-end; margin-top:16px; }
  .btn { background:var(--brand); color:var(--on-brand); border:0; border-radius:10px; padding:12px 18px; font:inherit;
         font-weight:700; cursor:pointer; }
  .btn.big { width:100%; padding:15px; font-size:16px; margin-top:16px; }
  .btn.small, .ghost.small { padding:7px 12px; font-size:13px; }
  .ghost { background:var(--chip); color:var(--text); border:0; border-radius:10px; padding:12px 18px; font:inherit; font-weight:600; cursor:pointer; }
  .item { display:flex; justify-content:space-between; gap:12px; padding:12px 0; border-top:1px solid var(--line); align-items:center; }
  .item:first-of-type { border-top:0; }
  .item .t { font-weight:700; } .item .s { color:var(--muted); font-size:13px; }
  .badge { display:inline-block; padding:2px 8px; border-radius:99px; font-size:12px; font-weight:700; background:var(--chip); }
  .badge.low { background:#fdecec; color:var(--bad); } .badge.soon { background:#fff4dd; color:var(--warn); }
  @media (prefers-color-scheme: dark) { .badge.low { background:#3a1b1f; } .badge.soon { background:#3a2c12; } }
  .total { font-size:26px; font-weight:800; text-align:center; margin:14px 0 0; }
  .empty { text-align:center; color:var(--muted); padding:26px 8px; }
  .actions { display:flex; gap:8px; flex-wrap:wrap; }
  .alert { padding:8px 0; border-top:1px solid var(--line); } .alert:first-of-type { border-top:0; }
  dialog { border:1px solid var(--line); border-radius:var(--r); background:var(--card); color:var(--text); width:min(440px,92vw); padding:20px; }
  dialog::backdrop { background:rgba(0,0,0,.5); }
  dialog h3 { margin:0 0 4px; }
  #toast { position:fixed; left:50%; bottom:22px; transform:translateX(-50%); background:var(--text); color:var(--bg);
           padding:12px 18px; border-radius:12px; font-weight:600; opacity:0; pointer-events:none; transition:opacity .2s;
           max-width:90vw; text-align:center; z-index:20; }
  #toast.show { opacity:1; } #toast.err { background:var(--bad); color:#fff; }
</style>
</head>
<body>
<header>
  <div class="bar"><div class="logo">Shop<span>Ledger</span></div><div class="cur" id="cur"></div></div>
  <nav id="nav"></nav>
</header>
<main id="view"><div class="empty">Loading…</div></main>
<dialog id="dlg"></dialog>
<div id="toast"></div>

<script>
const TABS = [["dash","Dashboard"],["sell","Sell"],["products","Products"],["expenses","Expenses"],["reports","Reports"]];
let S = null, tab = "dash", repData = null;

const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = n => String(Math.round(Number(n) * 1e6) / 1e6);
const money = v => { const d = S.decimals;
  return S.currency + " " + (v / 10 ** d).toLocaleString(undefined, {minimumFractionDigits:d, maximumFractionDigits:d}); };
const major = v => String(v / 10 ** S.decimals);

async function api(path, body) {
  const opt = body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {};
  const res = await fetch(path, opt);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || "Something went wrong");
  return data;
}
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.className = "", 3200);
}
async function load() { S = await api("/api/state"); render(); }

function renderNav() {
  $("#nav").innerHTML = TABS.map(([k, n]) => `<button class="${k === tab ? "on" : ""}" onclick="go('${k}')">${n}</button>`).join("");
  $("#cur").textContent = S ? S.currency : "";
}
function go(t) { tab = t; render(); window.scrollTo(0, 0); }
function render() { renderNav(); $("#view").innerHTML = ({dash, sell, products, expenses, reports}[tab])(); if (tab === "sell") calc(); }

/* ---------------- Dashboard ---------------- */
function kpi(l, v, cls = "") { return `<div class="card kpi"><div class="l">${l}</div><div class="v ${cls}">${v}</div></div>`; }
function dash() {
  const t = S.report_today, m = S.report_month, a = S.alerts;
  const issues = a.low_stock.length + a.expiring.length + a.expired.length;
  let alerts = "";
  a.expired.forEach(p => alerts += `<div class="alert"><span class="badge low">EXPIRED</span> <b>${esc(p.name)}</b> · ${num(p.stock)} ${esc(p.unit)} expired ${esc(p.expiry)}, remove from shelf</div>`);
  a.low_stock.forEach(p => alerts += `<div class="alert"><span class="badge low">${p.stock <= 0 ? "OUT" : "LOW"}</span> <b>${esc(p.name)}</b> · ${num(p.stock)} ${esc(p.unit)} left (reorder at ${num(p.reorder_level)})</div>`);
  a.expiring.forEach(p => alerts += `<div class="alert"><span class="badge soon">EXPIRING</span> <b>${esc(p.name)}</b> · ${num(p.stock)} ${esc(p.unit)} expires ${esc(p.expiry)}</div>`);
  const sales = S.sales.slice(0, 6).map(s => `<div class="item"><div><div class="t">${esc(s.name)}</div>
    <div class="s">${num(s.qty)} ${esc(s.unit)} · ${esc(s.sold_at.replace("T", " ").slice(0, 16))}</div></div>
    <div style="text-align:right"><div class="t">${money(s.total)}</div><div class="s good">+${money(s.profit)}</div></div></div>`).join("");
  return `
  <div class="grid">
    ${kpi("Sales today", money(t.revenue))}
    ${kpi("Profit today", money(t.gross_profit), t.gross_profit >= 0 ? "good" : "bad")}
    ${kpi("Net profit this month", money(m.net_profit), m.net_profit >= 0 ? "good" : "bad")}
    ${kpi("Stock on hand (at cost)", money(m.stock_value))}
  </div>
  <div class="card"><h3>${issues ? "Needs attention (" + issues + ")" : "Alerts"}</h3>
    ${alerts || `<div class="empty">All clear. Nothing is low or expiring.</div>`}</div>
  <div class="card"><h3>Recent sales</h3>${sales || `<div class="empty">No sales yet. Tap <b>Sell</b> to record your first one.</div>`}</div>`;
}

/* ---------------- Sell ---------------- */
function sell() {
  const ps = S.products;
  if (!ps.length) return `<div class="card empty">Add a product first (Products tab).<br><br><button class="btn" onclick="go('products')">Go to Products</button></div>`;
  return `<div class="card"><h3>Record a sale</h3>
    <label>Product</label>
    <select id="s_name" onchange="calc()">${ps.map((p, i) => `<option value="${i}">${esc(p.name)} (${num(p.stock)} ${esc(p.unit)} in stock)</option>`).join("")}</select>
    <div class="row"><div><label>Quantity</label><input id="s_qty" type="number" min="0" step="any" value="1" oninput="calc()"></div>
    <div><label>Price each (optional)</label><input id="s_price" type="number" min="0" step="any" placeholder="" oninput="calc()"></div></div>
    <div class="total" id="s_total"></div><div class="muted" id="s_hint" style="text-align:center"></div>
    <button class="btn big" onclick="doSell()">Record sale</button></div>`;
}
function calc() {
  const p = S.products[$("#s_name").value], qty = parseFloat($("#s_qty").value) || 0;
  $("#s_price").placeholder = major(p.price);
  const each = $("#s_price").value === "" ? p.price / 10 ** S.decimals : parseFloat($("#s_price").value) || 0;
  $("#s_total").textContent = S.currency + " " + (qty * each).toLocaleString(undefined, {maximumFractionDigits: S.decimals});
  const profit = qty * (each - p.cost / 10 ** S.decimals);
  $("#s_hint").innerHTML = qty > p.stock ? `<span class="bad">Only ${num(p.stock)} ${esc(p.unit)} in stock</span>` :
    `Profit on this sale: <b class="${profit >= 0 ? "good" : "bad"}">${S.currency} ${profit.toLocaleString(undefined, {maximumFractionDigits: S.decimals})}</b>`;
}
async function doSell() {
  const p = S.products[$("#s_name").value], q = $("#s_qty").value;
  try {
    const r = await api("/api/sell", {name: p.name, qty: q, price: $("#s_price").value});
    await load();
    toast(`Sold ${num(q || 0)} ${p.unit} of ${p.name} for ${money(r.total)}` + (r.low_stock ? " · low stock!" : ""));
  } catch (e) { toast(e.message, true); }
}

/* ---------------- Products ---------------- */
function modal(title, body, label, handler) {
  const d = $("#dlg");
  d.innerHTML = `<form id="mf"><h3>${title}</h3>${body}<div class="row end"><button type="button" class="ghost" onclick="closeDlg()">Cancel</button><button class="btn">${label}</button></div></form>`;
  $("#mf").onsubmit = async e => { e.preventDefault();
    try { await handler(Object.fromEntries(new FormData(e.target))); closeDlg(); await load(); }
    catch (err) { toast(err.message, true); } };
  d.showModal();
}
function closeDlg() { $("#dlg").close(); }
function products() {
  const list = S.products.map((p, i) => {
    const margin = p.price ? Math.round((p.price - p.cost) / p.price * 100) : 0;
    const low = p.stock <= p.reorder_level;
    return `<div class="item"><div><div class="t">${esc(p.name)} ${low ? '<span class="badge low">LOW</span>' : ""}</div>
      <div class="s">${num(p.stock)} ${esc(p.unit)} · cost ${money(p.cost)} · price ${money(p.price)} · ${margin}% margin${p.expiry ? " · exp " + esc(p.expiry) : ""}</div></div>
      <div class="actions"><button class="ghost small" onclick="restock(${i})">Restock</button><button class="ghost small" onclick="reprice(${i})">Price</button></div></div>`;
  }).join("");
  return `<div class="row" style="margin-bottom:12px"><button class="btn" onclick="addProduct()">+ Add product</button></div>
    <div class="card">${list || `<div class="empty">No products yet. Add your first one.</div>`}</div>`;
}
function addProduct() {
  modal("Add product", `
    <label>Name</label><input name="name" required placeholder="e.g. Tomatoes">
    <div class="row"><div><label>Unit</label><input name="unit" placeholder="kg, bag, piece" value="kg"></div>
    <div><label>Current stock</label><input name="stock" type="number" min="0" step="any" value="0"></div></div>
    <div class="row"><div><label>Cost per unit</label><input name="cost" type="number" min="0" step="any" required></div>
    <div><label>Selling price</label><input name="price" type="number" min="0" step="any" required></div></div>
    <div class="row"><div><label>Warn at stock</label><input name="reorder" type="number" min="0" step="any" value="0"></div>
    <div><label>Expiry (optional)</label><input name="expiry" type="date"></div></div>`,
    "Add product", f => api("/api/product", f).then(() => toast("Product added")));
}
function restock(i) {
  const p = S.products[i];
  modal("Restock " + esc(p.name), `
    <label>Quantity added (${esc(p.unit)})</label><input name="qty" type="number" min="0" step="any" required autofocus>
    <label>New cost per unit (optional)</label><input name="cost" type="number" min="0" step="any" placeholder="${major(p.cost)}">
    <label>Expiry of this batch (optional)</label><input name="expiry" type="date">`,
    "Add stock", f => api("/api/restock", {...f, name: p.name}).then(r => toast(`${p.name}: stock now ${num(r.stock)} ${p.unit}`)));
}
function reprice(i) {
  const p = S.products[i];
  modal("Selling price: " + esc(p.name), `<label>New price per ${esc(p.unit)}</label>
    <input name="price" type="number" min="0" step="any" value="${major(p.price)}" required>`,
    "Save price", f => api("/api/price", {...f, name: p.name}).then(() => toast("Price updated")));
}

/* ---------------- Expenses ---------------- */
function expenses() {
  const list = S.expenses.map(e => `<div class="item"><div><div class="t">${esc(e.category)}</div>
    <div class="s">${esc(e.note || "")} ${esc(e.spent_at.slice(0, 10))}</div></div><div class="t bad">−${money(e.amount)}</div></div>`).join("");
  return `<div class="card"><h3>Record an expense</h3>
    <label>Category</label><input id="e_cat" list="cats" placeholder="Rent, Transport, Wages, Electricity…">
    <datalist id="cats"><option>Rent</option><option>Transport</option><option>Wages</option><option>Electricity</option><option>Packaging</option></datalist>
    <div class="row"><div><label>Amount</label><input id="e_amt" type="number" min="0" step="any"></div>
    <div><label>Note (optional)</label><input id="e_note"></div></div>
    <button class="btn big" onclick="doExpense()">Save expense</button></div>
    <div class="card"><h3>Recent expenses</h3>${list || `<div class="empty">No expenses recorded.</div>`}</div>`;
}
async function doExpense() {
  try { await api("/api/expense", {category: $("#e_cat").value, amount: $("#e_amt").value, note: $("#e_note").value});
        await load(); toast("Expense saved"); } catch (e) { toast(e.message, true); }
}

/* ---------------- Reports ---------------- */
function reports() {
  const r = repData;
  let out = `<div class="empty">Choose a period and press Show report.</div>`;
  if (r) {
    const cats = r.expenses_by_category.map(c => `<div class="item"><div>${esc(c.category)}</div><div class="t">${money(c.total)}</div></div>`).join("");
    const top = r.top_products.map(t => `<div class="item"><div><div class="t">${esc(t.name)}</div><div class="s">${num(t.qty)} ${esc(t.unit)} sold</div></div>
      <div style="text-align:right"><div class="t">${money(t.revenue)}</div><div class="s good">+${money(t.profit)}</div></div></div>`).join("");
    out = `<div class="grid">${kpi("Revenue", money(r.revenue))}${kpi("Gross profit", money(r.gross_profit) + ` <span class="s muted" style="font-size:13px">${r.margin_pct.toFixed(1)}%</span>`, r.gross_profit >= 0 ? "good" : "bad")}
      ${kpi("Expenses", money(r.expenses))}${kpi("Net profit", money(r.net_profit), r.net_profit >= 0 ? "good" : "bad")}</div>
      ${top ? `<div class="card"><h3>Top products by profit</h3>${top}</div>` : ""}
      ${cats ? `<div class="card"><h3>Expenses by category</h3>${cats}</div>` : ""}`;
  }
  return `<div class="card"><h3>Profit report</h3><div class="row">
    <div><label>From</label><input id="r_from" type="date" value="${esc(repFrom)}"></div>
    <div><label>To</label><input id="r_to" type="date" value="${esc(repTo)}"></div></div>
    <div class="actions" style="margin-top:12px"><button class="ghost small" onclick="quick('today')">Today</button>
    <button class="ghost small" onclick="quick('month')">This month</button><button class="ghost small" onclick="quick('all')">All time</button></div>
    <div class="row" style="margin-top:12px"><button class="btn" onclick="showReport()">Show report</button>
    <button class="ghost" onclick="exportCsv()">Export CSV (Excel)</button></div></div>${out}`;
}
let repFrom = "", repTo = "";
function quick(k) {
  if (k === "today") { repFrom = repTo = S.today; } else if (k === "month") { repFrom = S.today.slice(0, 8) + "01"; repTo = S.today; } else { repFrom = repTo = ""; }
  showReport();
}
async function showReport() {
  if ($("#r_from")) { repFrom = $("#r_from").value; repTo = $("#r_to").value; }
  try { repData = await api(`/api/report?start=${encodeURIComponent(repFrom)}&end=${encodeURIComponent(repTo)}`); render(); }
  catch (e) { toast(e.message, true); }
}
function exportCsv() {
  if ($("#r_from")) { repFrom = $("#r_from").value; repTo = $("#r_to").value; }
  location.href = `/api/export.csv?start=${encodeURIComponent(repFrom)}&end=${encodeURIComponent(repTo)}`;
}

load().catch(e => { $("#view").innerHTML = `<div class="card empty bad">Could not load: ${esc(e.message)}</div>`; });
</script>
</body>
</html>
"""
