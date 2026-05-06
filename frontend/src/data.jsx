/* Sample data for fin. All in-memory. */

// Single source of truth for supported currencies — mirrors fin/config.py SUPPORTED_CURRENCIES.
const CURRENCIES = ["CNY", "USD", "HKD", "CAD"];
const CURRENCY_SYMBOL = { CNY: "¥", USD: "$", HKD: "HK$", CAD: "CA$" };
const CURRENCY_LABEL  = { CNY: "人民币 CNY", USD: "美元 USD", HKD: "港元 HKD", CAD: "加元 CAD" };
const CURRENCY_OPTIONS = CURRENCIES.map(c => ({ value: c, label: CURRENCY_LABEL[c] || c }));

const SYMBOLS = {
  "美股指数 US Index": [
    { code: "^GSPC", name: "S&P 500",    market: "US", currency: "USD" },
    { code: "^NDX",  name: "Nasdaq 100", market: "US", currency: "USD" },
    { code: "^DJI",  name: "Dow Jones",  market: "US", currency: "USD" },
    { code: "^VIX",  name: "VIX",        market: "US", currency: "USD" },
  ],
  "美股 ETF US ETF": [
    { code: "SPY", name: "S&P ETF",      market: "US", currency: "USD" },
    { code: "QQQ", name: "Nasdaq ETF",   market: "US", currency: "USD" },
    { code: "IWM", name: "Russell 2000", market: "US", currency: "USD" },
    { code: "GLD", name: "Gold",         market: "US", currency: "USD" },
    { code: "TLT", name: "20Y Treasury", market: "US", currency: "USD" },
  ],
  "Mag7": [
    { code: "NVDA",  name: "Nvidia",      market: "US", currency: "USD" },
    { code: "AAPL",  name: "Apple",       market: "US", currency: "USD" },
    { code: "MSFT",  name: "Microsoft",   market: "US", currency: "USD" },
    { code: "GOOGL", name: "Alphabet A",  market: "US", currency: "USD" },
    { code: "GOOG",  name: "Alphabet C",  market: "US", currency: "USD" },
    { code: "AMZN",  name: "Amazon",      market: "US", currency: "USD" },
    { code: "META",  name: "Meta",        market: "US", currency: "USD" },
    { code: "TSLA",  name: "Tesla",       market: "US", currency: "USD" },
    { code: "BRK-B", name: "Berkshire B", market: "US", currency: "USD" },
  ],
  "港股 HK Stocks": [
    { code: "^HSI",    name: "恒生指数",   market: "HK", currency: "HKD" },
    { code: "^HSTECH", name: "恒生科技",   market: "HK", currency: "HKD" },
    { code: "^HSCE",   name: "国企指数",   market: "HK", currency: "HKD" },
    { code: "0700.HK", name: "腾讯控股",   market: "HK", currency: "HKD" },
    { code: "9988.HK", name: "阿里巴巴",   market: "HK", currency: "HKD" },
    { code: "3690.HK", name: "美团",       market: "HK", currency: "HKD" },
    { code: "1810.HK", name: "小米集团",   market: "HK", currency: "HKD" },
  ],
  "A 股 A-Shares": [
    { code: "000300.SS", name: "沪深 300", market: "CN", currency: "CNY" },
    { code: "000001.SS", name: "上证指数", market: "CN", currency: "CNY" },
    { code: "399006.SZ", name: "创业板指", market: "CN", currency: "CNY" },
    { code: "600519.SS", name: "贵州茅台", market: "CN", currency: "CNY" },
    { code: "300750.SZ", name: "宁德时代", market: "CN", currency: "CNY" },
  ],
};

const FX = { USD: 7.24, HKD: 0.93, CNY: 1, EUR: 7.84, CAD: 5.3 };

const SYMBOL_INDEX = (() => {
  const out = {};
  Object.values(SYMBOLS).flat().forEach(s => { out[s.code] = s; });
  return out;
})();

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

const INITIAL_ALERTS = [];

const TRIGGER_HISTORY = [];

// ── Holdings API helpers ────────────────────────────────────────────────────

async function _apiFetch(url, opts = {}) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(err.detail || r.statusText);
  }
  return r.status === 204 ? null : r.json();
}

const _JSON = body => ({ method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const _PUT  = body => ({ method: "PUT",  headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
const _DEL  = ()   => ({ method: "DELETE" });

async function apiGetPrices(symbols)      { return _apiFetch(`/api/prices?symbols=${symbols.join(",")}`); }

async function apiGetHoldings()           { return _apiFetch("/api/holdings"); }
async function apiCreateHolding(data)     { return _apiFetch("/api/holdings", _JSON(data)); }
async function apiUpdateHolding(id, data) { return _apiFetch(`/api/holdings/${id}`, _PUT(data)); }
async function apiDeleteHolding(id)       { return _apiFetch(`/api/holdings/${id}`, _DEL()); }

async function apiGetTransactions()           { return _apiFetch("/api/transactions"); }
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

// Module 4 — Balance Sheet snapshots
// Each item is one row. `inSnapshot: ["s3","s4"]` says which historical snapshots include it.
const BS_CATEGORIES = {
  // (asset|liability) → list of subcats matching the user's reference image
  asset:     ["现金", "投资", "固定资产", "社保", "外债"],
  liability: ["信用消费", "贷款", "信用卡", "期权"],
};
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

const BS_SNAPSHOTS = [
  { id: "s1", date: "2025-01-15", label: "2025 Q1 初版", note: "首次梳理" },
  { id: "s2", date: "2025-04-30", label: "2025 Q2 复盘", note: "腾讯加仓后" },
  { id: "s3", date: "2025-09-21", label: "2025 Q3 复盘", note: "买房首付划走" },
  { id: "s4", date: "2026-01-12", label: "2026 元旦", note: "年初规划" },
  { id: "s5", date: "2026-05-01", label: "2026 五一 (最新)", note: "当前" },
];

const BS_ITEMS = [
  // Assets
  { id: "b01", side: "asset", category: "投资",     name: "IB 股票",        amount: 2980000, currency: "CNY", updated: "2026-05-01", note: "美股仓位",       inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b02", side: "asset", category: "投资",     name: "富途港股",        amount: 220000,  currency: "HKD", updated: "2026-05-01", note: "0700·9988",      inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b03", side: "asset", category: "投资",     name: "A 股账户",        amount: 95000,   currency: "CNY", updated: "2026-05-01", note: "茅台·宁德",      inSnapshot: ["s2","s3","s4","s5"] },
  { id: "b04", side: "asset", category: "投资",     name: "黄金 ETF",       amount: 78000,   currency: "CNY", updated: "2026-05-01", note: "GLD",           inSnapshot: ["s3","s4","s5"] },
  { id: "b05", side: "asset", category: "现金",     name: "招行存款",        amount: 675000,  currency: "CNY", updated: "2026-05-01", note: "活期 + 定期",   inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b06", side: "asset", category: "现金",     name: "微众存款",        amount: 402000,  currency: "CNY", updated: "2026-05-01", note: "智能存款",       inSnapshot: ["s2","s3","s4","s5"] },
  { id: "b07", side: "asset", category: "现金",     name: "BMO 加币户口",    amount: 250000,  currency: "CNY", updated: "2026-05-01", note: "约 47k CAD",    inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b08", side: "asset", category: "现金",     name: "陈兰现金存款",     amount: 140000,  currency: "CNY", updated: "2026-05-01", note: "家用",          inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b09", side: "asset", category: "现金",     name: "招商 HK 银行卡",   amount: 8000,    currency: "HKD", updated: "2026-05-01", note: "",              inSnapshot: ["s2","s3","s4","s5"] },
  { id: "b10", side: "asset", category: "现金",     name: "汇丰 HK 银行卡",   amount: 75000,   currency: "HKD", updated: "2026-05-01", note: "",              inSnapshot: ["s3","s4","s5"] },
  { id: "b11", side: "asset", category: "现金",     name: "QUEST 余额",      amount: 25000,   currency: "CNY", updated: "2026-05-01", note: "",              inSnapshot: ["s4","s5"] },
  { id: "b12", side: "asset", category: "固定资产", name: "中海房产 估值",    amount: 3200000, currency: "CNY", updated: "2026-05-01", note: "评估价",        inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b13", side: "asset", category: "社保",     name: "公司社保账户",     amount: 184000,  currency: "CNY", updated: "2026-05-01", note: "累计缴存",       inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b14", side: "asset", category: "外债",     name: "借出款项",        amount: 0,       currency: "CNY", updated: "2026-05-01", note: "已收回",         inSnapshot: ["s1","s2","s3","s4","s5"] },
  // Liabilities
  { id: "b20", side: "liability", category: "贷款",     name: "中海房贷余额",   amount: 2020000, currency: "CNY", updated: "2026-05-01", note: "月供 ¥10.4k",   inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b21", side: "liability", category: "信用卡",   name: "中信信用卡",     amount: 0,       currency: "CNY", updated: "2026-05-01", note: "已还清",         inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b22", side: "liability", category: "信用卡",   name: "招行信用卡",     amount: 0,       currency: "CNY", updated: "2026-05-01", note: "已还清",         inSnapshot: ["s1","s2","s3","s4","s5"] },
  { id: "b23", side: "liability", category: "信用消费", name: "蚂蚁花呗",       amount: 4200,    currency: "CNY", updated: "2026-05-01", note: "下月扣款",       inSnapshot: ["s3","s4","s5"] },
  { id: "b24", side: "liability", category: "期权",     name: "卖出 SPY put",   amount: 12000,   currency: "USD", updated: "2026-05-01", note: "保证金占用",     inSnapshot: ["s4","s5"] },
];

// Savings goals (kept; surfaced in BalanceSheet bottom)
// Module 3 — ledger entries
const LEDGER = [
  { date: "2026-05-01", category: "餐饮 Food",       amount: -86.50, note: "Sushi Yu" },
  { date: "2026-05-01", category: "工资 Salary",     amount: 12400, note: "April salary" },
  { date: "2026-04-30", category: "交通 Transit",    amount: -22.00, note: "Uber" },
  { date: "2026-04-30", category: "投资 Invest",     amount: -8200, note: "Buy NVDA x60" },
  { date: "2026-04-29", category: "购物 Shopping",   amount: -342.10, note: "Apple Store" },
  { date: "2026-04-28", category: "餐饮 Food",       amount: -54.20, note: "Tim Hortons" },
  { date: "2026-04-27", category: "房租 Rent",       amount: -2400, note: "Monthly" },
  { date: "2026-04-25", category: "订阅 Subs",       amount: -22.99, note: "Spotify · iCloud" },
];

// Module 4 — savings goals
const GOALS = [
  { name: "应急基金 Emergency",   target: 60000,  current: 42300, deadline: "2026-12-31", color: "#2D5BD9" },
  { name: "首付 Down Payment",   target: 800000, current: 312500, deadline: "2028-06-30", color: "#C8821F" },
  { name: "旅行 Japan trip",     target: 25000,  current: 18800, deadline: "2026-09-15", color: "#6B4FB8" },
  { name: "FIRE 储蓄 Annual",    target: 240000, current: 96400, deadline: "2026-12-31", color: "#1F8A4C" },
];

Object.assign(window, {
  SYMBOLS, SYMBOL_INDEX, FX, INITIAL_ALERTS, TRIGGER_HISTORY,
  BS_CATEGORIES, BS_CAT_COLORS, BS_SNAPSHOTS, BS_ITEMS,
  LEDGER, GOALS, genSpark,
  apiGetPrices,
  apiGetHoldings, apiCreateHolding, apiUpdateHolding, apiDeleteHolding,
  apiGetTransactions, apiCreateTransaction, apiUpdateTransaction, apiDeleteTransaction, apiImportTransactions,
  apiGetIncome, apiCreateIncome, apiUpdateIncome, apiDeleteIncome, apiImportIncome,
  apiGetAccounts, apiCreateAccount, apiUpdateAccount, apiDeleteAccount,
});
