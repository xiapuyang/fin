/* Sample data for fin. All in-memory. */

// Single source of truth for supported currencies — mirrors fin/config.py SUPPORTED_CURRENCIES.
const CURRENCIES = ["CNY", "USD", "HKD", "CAD"];
const CURRENCY_SYMBOL = { CNY: "¥", USD: "$", HKD: "HK$", CAD: "CA$" };
const CURRENCY_LABEL  = { CNY: "人民币 CNY", USD: "美元 USD", HKD: "港元 HKD", CAD: "加元 CAD" };
const CURRENCY_OPTIONS = CURRENCIES.map(c => ({ value: c, label: CURRENCY_LABEL[c] || c }));

const SYMBOLS = {};
const FX = { USD: 7.24, HKD: 0.93, CNY: 1, CAD: 5.3 };
const SYMBOL_INDEX = {};

const _rebuildSymbolIndex = () => {
  Object.keys(SYMBOL_INDEX).forEach(k => delete SYMBOL_INDEX[k]);
  Object.values(SYMBOLS).flat().forEach(s => { SYMBOL_INDEX[s.code] = s; });
};

function genSpark(seed, n = 30, base = 100, vol = 0.025, drift = 0) {
  let v = base;
  const arr = [];
  let s = seed;
  for (let i = 0; i < n; i++) {
    s = (s * 9301 + 49297) % 233280;
    const r = (s / 233280) - 0.5;
    v = v * (1 + r * vol + drift);
    arr.push(v);
  }
  return arr;
}

// pre-generate sparklines only for symbols with known prices (holdings etc.)
Object.values(SYMBOLS).flat().forEach((s, i) => {
  if (!s.price) return;
  s.spark = genSpark(s.code.charCodeAt(0) + i * 7, 30, s.price * 0.95, 0.022, 0.001);
  s.spark[s.spark.length - 1] = s.price;
});

// ── Holdings API helpers ────────────────────────────────────────────────────

async function _apiFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    const detail = Array.isArray(err.detail)
      ? err.detail.map(e => e.msg || JSON.stringify(e)).join("; ")
      : (err.detail || r.statusText);
    throw new Error(detail);
  }
  return r.status === 204 ? null : r.json();
}

const _JSON = body => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const _PUT  = body => ({ method: "PUT",  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const _DEL  = ()   => ({ method: "DELETE" });

async function apiGetPrices(symbols)      { return _apiFetch(`/api/prices?symbols=${symbols.join(",")}`); }
async function apiGetDividends(symbols)   { return _apiFetch(`/api/dividends?symbols=${symbols.join(",")}`); }

async function apiGetHoldings()           { return _apiFetch("/api/holdings"); }
async function apiCreateHolding(data)     { return _apiFetch("/api/holdings", _JSON(data)); }
async function apiUpdateHolding(id, data) { return _apiFetch(`/api/holdings/${id}`, _PUT(data)); }
async function apiDeleteHolding(id)       { return _apiFetch(`/api/holdings/${id}`, _DEL()); }

async function apiGetTransactions()           { return _apiFetch("/api/transactions"); }
async function apiGetTransactionsPaged({ page = 1, pageSize = 30, symbol = "", account = "" } = {}) {
  const p = new URLSearchParams({ page, page_size: pageSize });
  if (symbol)  p.set("symbol", symbol);
  if (account) p.set("account", account);
  return _apiFetch(`/api/transactions/paged?${p}`);
}
async function apiCreateTransaction(data)     { return _apiFetch("/api/transactions", _JSON(data)); }
async function apiUpdateTransaction(id, data) { return _apiFetch(`/api/transactions/${id}`, _PUT(data)); }
async function apiDeleteTransaction(id)       { return _apiFetch(`/api/transactions/${id}`, _DEL()); }
async function apiImportTransactions(file) {
  const fd = new FormData();
  fd.append("file", file);
  return _apiFetch("/api/transactions/import", { method: "POST", body: fd });
}

async function apiGetIncome()           { return _apiFetch("/api/income"); }
async function apiCreateIncome(data)    { return _apiFetch("/api/income", _JSON(data)); }
async function apiUpdateIncome(id,data) { return _apiFetch(`/api/income/${id}`, _PUT(data)); }
async function apiDeleteIncome(id)      { return _apiFetch(`/api/income/${id}`, _DEL()); }
async function apiImportIncome(file, account) {
  const fd = new FormData();
  fd.append("file", file);
  const qs = account ? `?account=${encodeURIComponent(account)}` : "";
  return _apiFetch(`/api/income/import${qs}`, { method: "POST", body: fd });
}

async function apiGetAccounts()           { return _apiFetch("/api/accounts"); }
async function apiCreateAccount(data)     { return _apiFetch("/api/accounts", _JSON(data)); }
async function apiUpdateAccount(id, data) { return _apiFetch(`/api/accounts/${id}`, _PUT(data)); }
async function apiDeleteAccount(id)       { return _apiFetch(`/api/accounts/${id}`, _DEL()); }

// Module 4 — Balance Sheet category colors (consumed by dashboard.jsx).
const BS_CAT_COLORS = {
  "现金":      "#1F8A4C",
  "投资":      "#1F4FE0",
  "固定资产":  "#6B4FB8",
  "社保":      "#B8447B",
  "外债":      "#C8821F",
  "信用消费":  "#C8460F",
  "贷款":      "#9A4D2E",
  "信用卡":    "#C03A3A",
  "期权":      "#7A1F4F",
};

// ── Balance Sheet API helpers ────────────────────────────────────────────────

async function apiGetBalanceAccounts()               { return _apiFetch("/api/balance/accounts"); }
async function apiCreateBalanceAccount(data)         { return _apiFetch("/api/balance/accounts", _JSON(data)); }
async function apiUpdateBalanceAccount(id, data)     { return _apiFetch(`/api/balance/accounts/${id}`, _PUT(data)); }
async function apiDeleteBalanceAccount(id)           { return _apiFetch(`/api/balance/accounts/${id}`, _DEL()); }

async function apiGetBalanceSnapshots()              { return _apiFetch("/api/balance/snapshots"); }
async function apiCreateBalanceSnapshot(data)        { return _apiFetch("/api/balance/snapshots", _JSON(data)); }
async function apiUpdateBalanceSnapshot(id, data)    { return _apiFetch(`/api/balance/snapshots/${id}`, _PUT(data)); }
async function apiDeleteBalanceSnapshot(id)          { return _apiFetch(`/api/balance/snapshots/${id}`, _DEL()); }
async function apiCopyBalanceSnapshot(id, opts = {}) { return _apiFetch(`/api/balance/snapshots/${id}/copy`, _JSON(opts)); }

async function apiGetBalanceItems(snapshotId)        { return _apiFetch(`/api/balance/snapshots/${snapshotId}/items`); }
async function apiGetAllBalanceItems()               { return _apiFetch("/api/balance/items"); }
async function apiCreateBalanceItem(data)            { return _apiFetch("/api/balance/items", _JSON(data)); }
async function apiCreateBalanceItemsBulk(items)      { return _apiFetch("/api/balance/items/bulk", _JSON(items)); }
async function apiUpdateBalanceItem(id, data)        { return _apiFetch(`/api/balance/items/${id}`, _PUT(data)); }
async function apiDeleteBalanceItem(id)              { return _apiFetch(`/api/balance/items/${id}`, _DEL()); }
Object.assign(window, {
  SYMBOLS, SYMBOL_INDEX, FX, BS_CAT_COLORS,
  apiGetPrices, apiGetDividends,
  apiGetHoldings, apiCreateHolding, apiUpdateHolding, apiDeleteHolding,
  apiGetTransactions, apiGetTransactionsPaged, apiCreateTransaction, apiUpdateTransaction, apiDeleteTransaction, apiImportTransactions,
  apiGetIncome, apiCreateIncome, apiUpdateIncome, apiDeleteIncome, apiImportIncome,
  apiGetAccounts, apiCreateAccount, apiUpdateAccount, apiDeleteAccount,
  apiGetBalanceAccounts, apiCreateBalanceAccount, apiUpdateBalanceAccount, apiDeleteBalanceAccount,
  apiGetBalanceSnapshots, apiCreateBalanceSnapshot, apiUpdateBalanceSnapshot, apiDeleteBalanceSnapshot, apiCopyBalanceSnapshot,
  apiGetBalanceItems, apiGetAllBalanceItems, apiCreateBalanceItem, apiCreateBalanceItemsBulk, apiUpdateBalanceItem, apiDeleteBalanceItem,
});
