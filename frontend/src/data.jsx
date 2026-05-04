/* Sample data for fin. All in-memory. */

const SYMBOLS = {
  "美股指数 US Index": [
    { code: "^GSPC", name: "S&P 500", market: "US", price: 5847.20, prevClose: 5821.40, currency: "USD" },
    { code: "^NDX",  name: "Nasdaq 100", market: "US", price: 20733.50, prevClose: 20612.10, currency: "USD" },
    { code: "^DJI",  name: "Dow Jones", market: "US", price: 42114.40, prevClose: 42233.05, currency: "USD" },
    { code: "^VIX",  name: "VIX", market: "US", price: 18.42, prevClose: 17.20, currency: "USD" },
  ],
  "美股 ETF US ETF": [
    { code: "SPY", name: "S&P ETF", market: "US", price: 581.10, prevClose: 578.42, currency: "USD" },
    { code: "QQQ", name: "Nasdaq ETF", market: "US", price: 504.20, prevClose: 501.80, currency: "USD" },
    { code: "IWM", name: "Russell 2000", market: "US", price: 226.30, prevClose: 228.10, currency: "USD" },
    { code: "GLD", name: "Gold", market: "US", price: 254.80, prevClose: 252.60, currency: "USD" },
    { code: "TLT", name: "20Y Treasury", market: "US", price: 88.34, prevClose: 88.92, currency: "USD" },
  ],
  "Mag7": [
    { code: "NVDA",  name: "Nvidia", market: "US", price: 144.20, prevClose: 138.50, currency: "USD" },
    { code: "AAPL",  name: "Apple", market: "US", price: 232.10, prevClose: 234.40, currency: "USD" },
    { code: "MSFT",  name: "Microsoft", market: "US", price: 425.30, prevClose: 421.80, currency: "USD" },
    { code: "GOOGL", name: "Alphabet", market: "US", price: 174.20, prevClose: 171.10, currency: "USD" },
    { code: "AMZN",  name: "Amazon", market: "US", price: 199.80, prevClose: 198.20, currency: "USD" },
    { code: "META",  name: "Meta", market: "US", price: 591.40, prevClose: 583.20, currency: "USD" },
    { code: "TSLA",  name: "Tesla", market: "US", price: 248.60, prevClose: 244.10, currency: "USD" },
  ],
  "港股 HK Stocks": [
    { code: "^HSI",   name: "恒生指数", market: "HK", price: 21134.80, prevClose: 20987.10, currency: "HKD" },
    { code: "0700.HK",name: "腾讯控股", market: "HK", price: 412.40, prevClose: 408.20, currency: "HKD" },
    { code: "9988.HK",name: "阿里巴巴", market: "HK", price: 102.30, prevClose: 100.60, currency: "HKD" },
    { code: "3690.HK",name: "美团", market: "HK", price: 184.20, prevClose: 181.50, currency: "HKD" },
    { code: "1810.HK",name: "小米集团", market: "HK", price: 28.45, prevClose: 28.10, currency: "HKD" },
  ],
  "A 股 A-Shares": [
    { code: "000300.SS", name: "沪深 300", market: "CN", price: 4012.30, prevClose: 4001.20, currency: "CNY" },
    { code: "000001.SS", name: "上证指数", market: "CN", price: 3287.40, prevClose: 3275.10, currency: "CNY" },
    { code: "399006.SZ", name: "创业板指", market: "CN", price: 2241.60, prevClose: 2232.40, currency: "CNY" },
    { code: "600519.SS", name: "贵州茅台", market: "CN", price: 1521.80, prevClose: 1508.20, currency: "CNY" },
    { code: "300750.SZ", name: "宁德时代", market: "CN", price: 263.40, prevClose: 261.10, currency: "CNY" },
  ],
};

const FX = { USD: 7.24, HKD: 0.93, CNY: 1, EUR: 7.84 };

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

// pre-generate sparklines for everything
Object.values(SYMBOLS).flat().forEach((s, i) => {
  s.spark = genSpark(s.code.charCodeAt(0) + i * 7, 30, s.price * 0.95, 0.022, 0.001);
  s.spark[s.spark.length - 1] = s.price;
});

const INITIAL_ALERTS = [];

const TRIGGER_HISTORY = [];

// Module 2 — holdings sample
const HOLDINGS = [
  { code: "NVDA",     shares: 320, cost: 92.4, market: "US" },
  { code: "GOOGL",    shares: 180, cost: 142.6, market: "US" },
  { code: "TSM",      shares: 240, cost: 168.2, market: "US", price: 198.4, prevClose: 195.2, currency: "USD" },
  { code: "QQQ",      shares: 60,  cost: 462.1, market: "US" },
  { code: "AAPL",     shares: 90,  cost: 198.2, market: "US" },
  { code: "0700.HK",  shares: 800, cost: 348.0, market: "HK" },
  { code: "600519.SS",shares: 40,  cost: 1612.0,market: "CN" },
];

// Module 2 extension — transaction log (买入/卖出)
// Average cost & realized PnL get computed from this in holdings.jsx.
const TRANSACTIONS = [
  // NVDA — accumulated 320 shares @ avg 92.4
  { id: "t1",  date: "2024-06-12", code: "NVDA",     side: "buy",  shares: 100, price: 78.40,   ccy: "USD" },
  { id: "t2",  date: "2024-09-04", code: "NVDA",     side: "buy",  shares: 120, price: 95.20,   ccy: "USD" },
  { id: "t3",  date: "2025-01-15", code: "NVDA",     side: "buy",  shares: 100, price: 102.10,  ccy: "USD" },
  // GOOGL
  { id: "t4",  date: "2024-08-02", code: "GOOGL",    side: "buy",  shares: 100, price: 138.20,  ccy: "USD" },
  { id: "t5",  date: "2025-02-18", code: "GOOGL",    side: "buy",  shares: 80,  price: 148.10,  ccy: "USD" },
  // TSM
  { id: "t6",  date: "2024-07-19", code: "TSM",      side: "buy",  shares: 140, price: 158.40,  ccy: "USD" },
  { id: "t7",  date: "2024-12-03", code: "TSM",      side: "buy",  shares: 100, price: 181.90,  ccy: "USD" },
  // QQQ
  { id: "t8",  date: "2025-03-21", code: "QQQ",      side: "buy",  shares: 60,  price: 462.10,  ccy: "USD" },
  // AAPL — partial trim
  { id: "t9",  date: "2024-04-10", code: "AAPL",     side: "buy",  shares: 120, price: 175.30,  ccy: "USD" },
  { id: "t10", date: "2025-01-09", code: "AAPL",     side: "sell", shares: 30,  price: 235.40,  ccy: "USD", realized: 1803 },
  { id: "t11", date: "2026-01-22", code: "AAPL",     side: "buy",  shares: 0,   price: 0,       ccy: "USD" }, // (placeholder kept consistent)
  // 0700.HK
  { id: "t12", date: "2024-05-08", code: "0700.HK",  side: "buy",  shares: 500, price: 332.40,  ccy: "HKD" },
  { id: "t13", date: "2024-11-14", code: "0700.HK",  side: "buy",  shares: 300, price: 374.00,  ccy: "HKD" },
  // 600519.SS
  { id: "t14", date: "2024-10-08", code: "600519.SS",side: "buy",  shares: 40,  price: 1612.00, ccy: "CNY" },
];
// remove the no-op placeholder for AAPL
TRANSACTIONS.splice(TRANSACTIONS.findIndex(t => t.id === "t11"), 1);

// Manual income / "外部利润" entries (e.g. 分红, 利息, 期权权利金, 套利收益)
const HOLDINGS_INCOME = [
  { id: "i1", date: "2024-12-15", source: "NVDA 分红",       category: "dividend", amount: 320,   ccy: "USD", note: "Q4 dividend" },
  { id: "i2", date: "2025-03-08", source: "0700.HK 分红",    category: "dividend", amount: 480,   ccy: "HKD", note: "腾讯派息" },
  { id: "i3", date: "2025-06-22", source: "卖出 SPY put",    category: "option",   amount: 820,   ccy: "USD", note: "Cash-secured put 权利金" },
  { id: "i4", date: "2025-11-04", source: "余额宝 利息",      category: "interest", amount: 612,   ccy: "CNY", note: "" },
  { id: "i5", date: "2026-02-19", source: "TSM 分红",        category: "dividend", amount: 156,   ccy: "USD", note: "" },
  { id: "i6", date: "2026-04-11", source: "卖出 NVDA call",  category: "option",   amount: 1240,  ccy: "USD", note: "Covered call 权利金" },
];

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
  HOLDINGS, TRANSACTIONS, HOLDINGS_INCOME,
  BS_CATEGORIES, BS_CAT_COLORS, BS_SNAPSHOTS, BS_ITEMS,
  LEDGER, GOALS, genSpark,
});
