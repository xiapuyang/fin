/* Module 03 — 收入支出 */

const RECURRING_LABEL = {
  monthly:       "每月",
  annual:        "每年",
  semi_annual:   "每半年",
  every_4months: "每四个月",
};

const RECURRING_ORDER = ["monthly", "every_4months", "semi_annual", "annual"];

const RECURRING_FREQ_COLORS = {
  monthly:       { bg: "#EBF0FF", text: "#1F4FE0" },
  every_4months: { bg: "#FFF3E0", text: "#C8821F" },
  semi_annual:   { bg: "#F3EEFF", text: "#6B4FB8" },
  annual:        { bg: "#E8F5EE", text: "#1F8A4C" },
};

// Fallback when a row references a category that no longer exists.
const CATEGORY_FALLBACK = { bg: "#ECEDEF", text: "#6B7280" };

// Picker palette shown in the category manager UI when creating/editing a
// custom category. Has nothing to do with how built-in pills are colored —
// each category persists its own bg/text colors via the API, so name→color
// stays deterministic. Order spreads hues for visual choice.
const COLOR_PICKER_PRESETS = [
  { bg: "#FBE3D6", text: "#E85D2C" }, // orange
  { bg: "#D6F0F2", text: "#14959E" }, // teal
  { bg: "#DDE7FA", text: "#2964D9" }, // blue
  { bg: "#FAD9E7", text: "#D9347A" }, // pink
  { bg: "#FBDADA", text: "#D62828" }, // red
  { bg: "#DEE1EE", text: "#4F5B8C" }, // slate
  { bg: "#FAEDD2", text: "#C8821F" }, // gold
  { bg: "#D8DDE3", text: "#2C3E50" }, // charcoal
  { bg: "#E8DEF6", text: "#7A4FC8" }, // violet
  { bg: "#ECF1D2", text: "#8DA82A" }, // olive
  { bg: "#D6EEDF", text: "#1F8A4C" }, // emerald
  { bg: "#EBDDD0", text: "#8E4A1B" }, // sienna
];

// Categories are fetched from /api/categories and broadcast via Context so
// CategoryPill (used in dozens of nested rows) can look up colors without
// prop-drilling. Built-ins live in code on the backend; custom categories
// live in data/ledger_categories.json.
const CategoryContext = React.createContext({
  list: [], byName: {}, expense: [], income: [],
});

const CategoryPill = ({ category, categoryName }) => {
  const { byName, byId } = React.useContext(CategoryContext);
  const rec = byId[category] || byName[category] || CATEGORY_FALLBACK;
  const label = categoryName || rec.name || category;
  return (
    <span style={{
      background: rec.bg, color: rec.text,
      padding: "2px 8px", fontSize: 11, fontWeight: 600, borderRadius: 999,
      lineHeight: 1.5, whiteSpace: "nowrap",
    }}>{label}</span>
  );
};

// ── API ──────────────────────────────────────────────────────────────────────

async function fetchLedgerList({ direction, startDate, endDate, category, search, page = 1, pageSize = 20 } = {}) {
  const p = new URLSearchParams({ page, page_size: pageSize });
  if (direction && direction !== "all") p.set("direction", direction);
  if (startDate) p.set("start_date", startDate);
  if (endDate) p.set("end_date", endDate);
  if (category) p.set("category", category);
  if (search) p.set("search", search);
  const res = await fetch(`/api/ledger?${p}`);
  if (!res.ok) throw new Error("fetch failed");
  return res.json();
}

async function fetchLedgerStats({ timeRange, startDate, endDate, fxRates, currency } = {}) {
  const p = new URLSearchParams();
  if (timeRange) p.set("time_range", timeRange);
  if (startDate) p.set("start_date", startDate);
  if (endDate) p.set("end_date", endDate);
  if (fxRates) p.set("fx_rates", JSON.stringify(fxRates));
  if (currency) p.set("display_currency", currency);
  const res = await fetch(`/api/ledger/stats?${p}`);
  if (!res.ok) throw new Error("fetch failed");
  return res.json();
}

async function fetchLedgerRecurring(includeExpired = false) {
  const res = await fetch(`/api/ledger/recurring${includeExpired ? "?include_expired=true" : ""}`);
  if (!res.ok) throw new Error("fetch failed");
  return res.json();
}

async function fetchLedgerSeries({ recurring_type, category, subcategory }) {
  const p = new URLSearchParams({ recurring_type, category, subcategory });
  const res = await fetch(`/api/ledger/recurring/series?${p}`);
  if (!res.ok) throw new Error("fetch failed");
  return res.json();
}

async function deleteLedgerEntry(id) {
  const res = await fetch(`/api/ledger/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error("delete failed");
}

async function updateLedgerEntry(id, body) {
  const res = await fetch(`/api/ledger/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("update failed");
  return res.json();
}

async function fetchCategories() {
  const res = await fetch("/api/categories");
  if (!res.ok) throw new Error("fetch categories failed");
  return res.json();
}

async function createCategory(body) {
  const res = await fetch("/api/categories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "create category failed");
  }
  return res.json();
}

async function updateCategory(id, body) {
  const res = await fetch(`/api/categories/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "update category failed");
  }
  return res.json();
}

async function deleteCategory(id) {
  const res = await fetch(`/api/categories/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    const d = await res.json().catch(() => ({}));
    throw new Error(d.detail || "delete category failed");
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function yearRange(year) {
  return year ? { startDate: `${year}-01-01`, endDate: `${year}-12-31` } : {};
}

function todayStr() {
  return new Date().toISOString().slice(0, 10);
}

// Returns the next occurrence of a recurring payment on or after today
function nextPaymentDate(dateStr, recurringType) {
  const months = { monthly: 1, every_4months: 4, semi_annual: 6, annual: 12 }[recurringType] || 1;
  const d = new Date(dateStr + "T00:00:00");
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  while (d < today) d.setMonth(d.getMonth() + months);
  return d;
}

// ── Main ─────────────────────────────────────────────────────────────────────

const Ledger = ({ fxRates = {}, currency = "CNY" }) => {
  usePrivacyMasked(); // re-render summary tiles on privacy toggle
  const currentYear = new Date().getFullYear();

  const [years, setYears] = React.useState([]);
  const [activeYear, setActiveYear] = React.useState(currentYear);
  const [direction, setDirection] = React.useState("expense");
  const [category, setCategory] = React.useState(null);
  const [search, setSearch] = React.useState("");
  const [searchInput, setSearchInput] = React.useState("");
  const [page, setPage] = React.useState(1);

  const [listData, setListData] = React.useState({ items: [], total: 0, pages: 1 });
  const [chartData, setChartData] = React.useState({ bars: [], pie: [] });
  const [summary, setSummary] = React.useState({ income: 0, expense: 0, net: 0, max_expense: 0 });
  const [recurring, setRecurring] = React.useState([]);
  const [recurringExpired, setRecurringExpired] = React.useState([]);
  const [loading, setLoading] = React.useState(true);

  const [showImport, setShowImport] = React.useState(false);
  const [editItem, setEditItem] = React.useState(null);
  const [deleteTarget, setDeleteTarget] = React.useState(null);
  const [duplicateItem, setDuplicateItem] = React.useState(null);
  const [seriesItem, setSeriesItem] = React.useState(null);
  const [endTarget, setEndTarget] = React.useState(null);
  const [showCategoryManager, setShowCategoryManager] = React.useState(false);

  const [categories, setCategories] = React.useState([]);

  const reloadCategories = React.useCallback(() => {
    fetchCategories()
      .then(setCategories)
      .catch((e) => console.error("Failed to fetch categories — restart serve.py?", e));
  }, []);

  React.useEffect(() => { reloadCategories(); }, [reloadCategories]);

  const categoryCtx = React.useMemo(() => {
    const byName = {};
    const byId = {};
    const expense = [];
    const income = [];
    for (const c of categories) {
      byName[c.name] = { bg: c.bg_color, text: c.text_color, id: c.id };
      byId[c.id] = { name: c.name, bg: c.bg_color, text: c.text_color };
      if (c.direction === "expense") expense.push(c);
      else if (c.direction === "income") income.push(c);
    }
    return { list: categories, byName, byId, expense, income };
  }, [categories]);

  const colorOf = (name) => categoryCtx.byName[name] || CATEGORY_FALLBACK;
  const colorOfId = (id) => categoryCtx.byId[id] || CATEGORY_FALLBACK;

  // Convert any amount from its source currency to the display currency
  const convertAmount = (amount, fromCurrency) => {
    const from = fromCurrency || "CNY";
    if (from === currency) return amount;
    const fromRate = fxRates[from] || 1;
    const toRate = fxRates[currency] || 1;
    return amount * fromRate / toRate;
  };
  const sym = CURRENCY_SYMBOL[currency] || "¥";
  // disp(amount, decimals, sign): converts from CNY to currency. For aggregated/summary values.
  // Prefixes currency code for non-CNY so $-amounts disambiguate (CAD vs USD).
  // Sign goes between the code and the symbol — e.g. "USD −$1,234".
  const disp = (amount, decimals = 0, sign = "") => {
    const body = `${sign}${sym}${fmtNum(convertAmount(amount, "CNY"), decimals)}`;
    return currency === "CNY" ? body : `${currency} ${body}`;
  };
  // dispStat(amount, decimals, sign): formats an amount already in currency
  // (returned directly from the stats API). No conversion applied.
  const dispStat = (amount, decimals = 0, sign = "") => {
    const body = `${sign}${sym}${fmtNum(amount, decimals)}`;
    return currency === "CNY" ? body : `${currency} ${body}`;
  };
  // nativeFmt(amount, currency): renders an amount in its stored currency. For per-row display.
  const nativeFmt = (amount, currency = "CNY", decimals = 0) =>
    `${CURRENCY_SYMBOL[currency] || "¥"}${fmtNum(amount, decimals)}`;

  // Backfill amounts_json for existing rows on mount (idempotent — only fills missing entries)
  React.useEffect(() => {
    if (Object.keys(fxRates).length > 0) {
      fetch("/api/ledger/backfill-amounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ fx_rates: fxRates }),
      }).catch(() => {});
    }
  }, []);

  // Discover available years via dedicated endpoint
  React.useEffect(() => {
    fetch("/api/ledger/years")
      .then(r => r.json())
      .then(ys => {
        setYears(ys);
        if (!ys.includes(currentYear) && ys.length > 0) setActiveYear(ys[0]);
      })
      .catch(() => {});
  }, []);

  // Reload list + summary + recurring when filters change
  React.useEffect(() => {
    const { startDate, endDate } = yearRange(activeYear === 0 ? null : activeYear);
    setLoading(true);
    Promise.all([
      fetchLedgerList({ direction, startDate, endDate, category, search, page }),
      fetchLedgerStats({ startDate, endDate, fxRates, currency }),
      fetchLedgerRecurring(false),
      fetchLedgerRecurring(true),
    ]).then(([list, stats, rec, recExpired]) => {
      setListData(list);
      setSummary(stats.summary);
      setRecurring(rec);
      setRecurringExpired(recExpired);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [activeYear, direction, category, search, page, fxRates, currency]);

  // Chart: yearly bars for 全部年, monthly bars for specific year
  React.useEffect(() => {
    const opts = (activeYear && activeYear !== 0)
      ? { ...yearRange(activeYear), fxRates, currency }
      : { timeRange: "all", fxRates, currency };
    fetchLedgerStats(opts).then(d => setChartData(d)).catch(() => {});
  }, [activeYear, fxRates, currency]);

  const handleYearChange = (y) => { setActiveYear(Number(y)); setPage(1); };
  const handleDirectionChange = (d) => { setDirection(d); setCategory(null); setPage(1); };
  const handleCategoryClick = (c) => { setCategory(prev => prev === c ? null : c); setPage(1); };
  const handleSearch = (e) => { e.preventDefault(); setSearch(searchInput); setPage(1); };

  const refresh = () => {
    const { startDate, endDate } = yearRange(activeYear === 0 ? null : activeYear);
    return Promise.all([
      fetchLedgerList({ direction, startDate, endDate, category, search, page }),
      fetchLedgerStats({ startDate, endDate, fxRates, currency }),
      fetchLedgerRecurring(false),
      fetchLedgerRecurring(true),
    ]).then(([list, stats, rec, recExpired]) => {
      setListData(list);
      setSummary(stats.summary);
      setRecurring(rec);
      setRecurringExpired(recExpired);
    });
  };

  const handleEndConfirm = async (expiryDate) => {
    if (!endTarget) return;
    try {
      await updateLedgerEntry(endTarget.id, { is_expired: true, expiry_date: expiryDate });
      setEndTarget(null);
      await refresh();
    } catch (e) {}
  };

  const handleResumeRecurring = async (id) => {
    try {
      await updateLedgerEntry(id, { is_expired: false });
      await refresh();
    } catch (e) {}
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    try {
      await deleteLedgerEntry(deleteTarget.id);
      setDeleteTarget(null);
      await refresh();
    } catch (e) {}
  };

  const handleEditDone = () => { setEditItem(null); refresh(); };

  // Group recurring by frequency and sort each group by next payment date
  const groupRecurring = (items, sortByNextDate) => {
    const by = {};
    items.forEach(r => {
      const k = r.recurring_type || "monthly";
      (by[k] = by[k] || []).push(r);
    });
    if (sortByNextDate) {
      RECURRING_ORDER.forEach(k => {
        if (by[k]) by[k].sort((a, b) => nextPaymentDate(a.date, k) - nextPaymentDate(b.date, k));
      });
    } else {
      RECURRING_ORDER.forEach(k => {
        if (by[k]) by[k].sort((a, b) => (a.date < b.date ? 1 : -1));
      });
    }
    return by;
  };
  const recurringByType = groupRecurring(recurring, true);
  const recurringExpiredByType = groupRecurring(recurringExpired, false);

  // Compute monthly equivalent in currency:
  // prefer amounts_json[currency] (historically accurate), fall back to FX conversion
  const toDisplayAmt = (r) => {
    if (r.amounts_json) {
      try {
        const aj = JSON.parse(r.amounts_json);
        if (currency in aj) return aj[currency];
        // partial amounts_json — go through CNY
        const cny = aj.CNY ?? r.amount * (fxRates[r.currency || "CNY"] || 1);
        return cny / (fxRates[currency] || 1);
      } catch (_) {}
    }
    const cny = r.amount * (fxRates[r.currency || "CNY"] || 1);
    return cny / (fxRates[currency] || 1);
  };

  const monthlyEquiv = recurring.reduce((s, r) => {
    const f = { monthly: 1, annual: 1/12, semi_annual: 1/6, every_4months: 1/4 }[r.recurring_type] || 1;
    return s + toDisplayAmt(r) * f;
  }, 0);

  const yearOpts = [
    { value: "0", label: "全部年" },
    ...years.map(y => ({ value: String(y), label: String(y) })),
  ];

  return (
    <CategoryContext.Provider value={categoryCtx}>
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 03 · 收入支出"
        title="收入支出"
        subtitle="Personal Cashflow · 自动分类 · 年度报表"
        right={
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Select
              value={String(activeYear || 0)}
              onChange={handleYearChange}
              options={yearOpts}
              style={{ width: 110 }}
            />
            <Button variant="secondary" icon="settings" onClick={() => setShowCategoryManager(true)}>分类</Button>
            <Button variant="primary" icon="plus" onClick={() => setEditItem({})}>添加记录</Button>
          </div>
        }
      />

      {/* Summary tiles */}
      {(() => {
        const allYears = !activeYear || activeYear === 0;
        const avgVal = allYears
          ? summary.expense / Math.max(years.length, 1)
          : summary.expense / 12;
        return (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 22 }}>
            <LedgerTile label={allYears ? "总收入 TOTAL"   : "年度收入 INCOME"}  value={PRIVACY.masked ? "•••" : dispStat(summary.income, 0, "+")}                                       tone="up" />
            <LedgerTile label={allYears ? "总支出 TOTAL"   : "年度支出 EXPENSE"} value={PRIVACY.masked ? "•••" : dispStat(summary.expense, 0, "−")}                                      tone="up" />
            <LedgerTile label="净结余 NET"                                        value={PRIVACY.masked ? "•••" : dispStat(Math.abs(summary.net), 0, summary.net >= 0 ? "+" : "−")}      tone="up" />
            <LedgerTile label={allYears ? "年均支出 AVG/YR" : "月均支出 AVG/MO"} value={PRIVACY.masked ? "•••" : dispStat(avgVal)}                                                     tone="neutral" />
            <LedgerTile label="最大单笔 MAX TXN"                                  value={PRIVACY.masked ? "•••" : dispStat(summary.max_expense)}                                        tone="neutral"
              sub={summary.max_expense_date ? `${summary.max_expense_date} · ${summary.max_expense_name || ""}` : undefined}
            />
          </div>
        );
      })()}

      {/* Charts */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ marginBottom: 14 }}>
            <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>支出趋势</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
              {(activeYear && activeYear !== 0) ? `${activeYear}年 · 月度` : "全部 · 年度"}
            </div>
          </div>
          {chartData.bars.length > 0
            ? <BarChart
                data={chartData.bars.map(b => ({
                  label: b.date.length === 4 ? b.date : b.date.slice(5),
                  value: b.amount,
                }))}
                width={700} height={180}
              />
            : <Empty icon="circle" title="暂无数据" hint="选择有数据的年份" />
          }
        </Card>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>分类占比</div>
          {chartData.pie.length > 0 ? (
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <Donut
                data={chartData.pie.slice(0, 10).map((p) => ({
                  label: p.category,
                  value: p.amount,
                  color: colorOf(p.category).text,
                }))}
                size={140} thickness={20}
                centerValue={dispStat(chartData.pie.reduce((s, p) => s + p.amount, 0), 2)}
                centerSub="total"
              />
              <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 12, flex: 1, overflow: "hidden" }}>
                {chartData.pie.slice(0, 8).map((p) => (
                  <div key={p.category} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: colorOf(p.category).text, flexShrink: 0 }} />
                    <span style={{ flex: 1, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.category}</span>
                    <span className="mono" style={{ color: "var(--ink-3)", flexShrink: 0 }}>{dispStat(p.amount, 2)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <Empty icon="circle" title="暂无数据" />
          )}
        </Card>
      </div>

      {/* Transaction list */}
      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
            <Tabs
              variant="pill"
              value={direction}
              onChange={handleDirectionChange}
              tabs={[
                { id: "all", label: "全部" },
                { id: "income", label: "收入" },
                { id: "expense", label: "支出" },
              ]}
            />
            <form onSubmit={handleSearch} style={{ display: "flex", gap: 6, flex: 1, maxWidth: 320 }}>
              <Input
                value={searchInput}
                onChange={v => { setSearchInput(v); if (!v) { setSearch(""); setPage(1); } }}
                placeholder="搜索名称、备注、分类…"
                prefix={<Icon name="search" size={13} />}
                style={{ flex: 1, height: 30 }}
              />
            </form>
            <div style={{ fontSize: 12, color: "var(--ink-4)", flexShrink: 0 }}>共 {listData.total} 条</div>
          </div>
          {(direction === "expense" || direction === "income") && (
            <div style={{ marginTop: 10, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(direction === "income" ? categoryCtx.income : categoryCtx.expense).map(({ id, name }) => {
                const col = colorOf(name);
                const active = category === id;
                return (
                  <button
                    key={id}
                    onClick={() => handleCategoryClick(id)}
                    style={{
                      padding: "3px 10px", fontSize: 12, fontWeight: 600, borderRadius: 999, border: "none",
                      background: active ? col.text : col.bg,
                      color: active ? "#fff" : col.text,
                      cursor: "pointer", transition: "background .12s, color .12s",
                    }}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {loading ? (
          <div style={{ padding: 32, textAlign: "center", color: "var(--ink-4)", fontSize: 13 }}>加载中…</div>
        ) : listData.items.length === 0 ? (
          <Empty icon="book" title="暂无记录" hint="导入 Notion 数据或手动添加" />
        ) : (
          listData.items.map((item, i) => (
            <LedgerRow
              key={item.id}
              item={item}
              last={i === listData.items.length - 1}
              fmt={nativeFmt}
              onEdit={() => setEditItem(item)}
              onDelete={() => setDeleteTarget({ id: item.id, name: item.name })}
            />
          ))
        )}

        {listData.pages > 1 && (
          <div style={{ padding: "12px 18px", borderTop: "1px solid var(--line)", display: "flex", justifyContent: "center", gap: 4 }}>
            <PagerButton label="‹" disabled={page === 1} onClick={() => setPage(p => p - 1)} />
            {pagerRange(page, listData.pages).map((p, i) =>
              p === "…"
                ? <span key={`dot-${i}`} style={{ padding: "5px 8px", color: "var(--ink-4)", fontSize: 13 }}>…</span>
                : <PagerButton key={p} label={String(p)} active={p === page} onClick={() => setPage(p)} />
            )}
            <PagerButton label="›" disabled={page === listData.pages} onClick={() => setPage(p => p + 1)} />
          </div>
        )}
      </Card>

      {/* Recurring — active 4 columns, sorted by next payment date */}
      {recurring.length > 0 && (
        <div style={{ marginTop: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-3)", letterSpacing: ".1em", textTransform: "uppercase", marginBottom: 14 }}>
            定期消费 · {recurring.length} 项 · 月均 {dispStat(monthlyEquiv)} · 年均 {dispStat(monthlyEquiv * 12)}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {RECURRING_ORDER.map(k => {
              const items = recurringByType[k] || [];
              const col = RECURRING_FREQ_COLORS[k];
              const freqToMonths = { monthly: 1, every_4months: 4, semi_annual: 6, annual: 12 };
              const groupMonthly = items.reduce((s, r) => s + toDisplayAmt(r) / (freqToMonths[k] || 1), 0);
              const groupAnnual = groupMonthly * 12;
              return (
                <div key={k} style={{ border: "1px solid var(--line)", borderRadius: 10, overflow: "hidden" }}>
                  <div style={{
                    background: col.bg, color: col.text,
                    padding: "8px 14px", fontSize: 12, fontWeight: 700,
                  }}>
                    <div>{RECURRING_LABEL[k]} · {items.length} 项</div>
                    {items.length > 0 && (
                      <div style={{ fontWeight: 500, fontSize: 11, marginTop: 2, opacity: 0.85 }}>
                        月均 {dispStat(groupMonthly)} · 年 {dispStat(groupAnnual)}
                      </div>
                    )}
                  </div>
                  {items.length === 0
                    ? <div style={{ padding: "14px", fontSize: 12, color: "var(--ink-4)" }}>暂无</div>
                    : items.map((r, idx) => (
                        <RecurringCard
                          key={r.id}
                          item={r}
                          nextDate={nextPaymentDate(r.date, r.recurring_type || k)}
                          last={idx === items.length - 1}
                          fmt={nativeFmt}
                          onEdit={() => setEditItem(r)}
                          onDelete={() => setDeleteTarget({ id: r.id, name: r.name })}
                          onDuplicate={() => setDuplicateItem(r)}
                          onEnd={() => setEndTarget({ id: r.id, name: r.name })}
                          onExpand={() => setSeriesItem(r)}
                        />
                      ))
                  }
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Recurring — ended */}
      {recurringExpired.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".1em", textTransform: "uppercase", marginBottom: 14 }}>
            已结束 · {recurringExpired.length} 项
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, opacity: 0.62 }}>
            {RECURRING_ORDER.map(k => {
              const items = recurringExpiredByType[k] || [];
              return (
                <div key={k} style={{ border: "1px dashed var(--line-2)", borderRadius: 10, overflow: "hidden", background: "var(--bg-deep)" }}>
                  <div style={{ background: "var(--bg-deep)", color: "var(--ink-4)", padding: "8px 14px", fontSize: 12, fontWeight: 700 }}>
                    {RECURRING_LABEL[k]} · {items.length} 项
                  </div>
                  {items.length === 0
                    ? <div style={{ padding: "14px", fontSize: 12, color: "var(--ink-5)" }}>暂无</div>
                    : items.map((r, idx) => (
                        <RecurringCard
                          key={r.id}
                          item={r}
                          nextDate={null}
                          last={idx === items.length - 1}
                          fmt={nativeFmt}
                          ended
                          onEdit={() => setEditItem(r)}
                          onDelete={() => setDeleteTarget({ id: r.id, name: r.name })}
                          onResume={() => handleResumeRecurring(r.id)}
                          onExpand={() => setSeriesItem(r)}
                        />
                      ))
                  }
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Modals */}
      {showImport && (
        <ImportModal
          onClose={() => setShowImport(false)}
          onDone={() => { setShowImport(false); setPage(1); }}
        />
      )}
      {editItem !== null && (
        <EntryModal
          item={Object.keys(editItem).length === 0 ? null : editItem}
          fxRates={fxRates}
          onClose={() => setEditItem(null)}
          onDone={handleEditDone}
        />
      )}
      {deleteTarget && (
        <ConfirmModal
          message={`确认删除「${deleteTarget.name}」？此操作不可撤销。`}
          onClose={() => setDeleteTarget(null)}
          onConfirm={handleDeleteConfirm}
        />
      )}
      {endTarget && (
        <EndRecurringModal
          name={endTarget.name}
          onClose={() => setEndTarget(null)}
          onConfirm={handleEndConfirm}
        />
      )}
      {duplicateItem && (
        <DuplicateModal
          item={duplicateItem}
          fmt={nativeFmt}
          fxRates={fxRates}
          onClose={() => setDuplicateItem(null)}
          onDone={() => { setDuplicateItem(null); refresh(); }}
        />
      )}
      {seriesItem && (
        <SeriesModal
          item={seriesItem}
          fmt={nativeFmt}
          onClose={() => setSeriesItem(null)}
          onEdit={(r) => { setSeriesItem(null); setEditItem(r); }}
          onDelete={(r) => { setSeriesItem(null); setDeleteTarget({ id: r.id, name: r.name }); }}
        />
      )}
      {showCategoryManager && (
        <CategoryManagerModal
          onClose={() => setShowCategoryManager(false)}
          onChange={reloadCategories}
        />
      )}
    </div>
    </CategoryContext.Provider>
  );
};

// ── Sub-components ────────────────────────────────────────────────────────────

const LedgerTile = ({ label, value, tone, sub }) => {
  const c = { up: "var(--up)", down: "var(--down)", neutral: "var(--ink)" }[tone] || "var(--ink)";
  return (
    <Card padding={16}>
      <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".12em" }}>{label}</div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, marginTop: 6, color: c }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{sub}</div>}
    </Card>
  );
};

const iconBtnStyle = {
  background: "transparent", border: "none", cursor: "pointer",
  color: "var(--ink-4)", padding: "2px 3px", borderRadius: 4, display: "inline-flex", alignItems: "center",
};

const RecurringCard = ({ item, nextDate, last, fmt, ended, onEdit, onDelete, onDuplicate, onEnd, onResume, onExpand }) => {
  const count = item.count || 0;
  const dateLabel = ended
    ? (item.date ? `截至 ${item.date.slice(5)}` : "已结束")
    : (nextDate ? `下次 ${nextDate.getMonth() + 1}/${nextDate.getDate()}` : "");
  const stop = (e, fn) => { e.stopPropagation(); fn && fn(); };
  return (
    <div
      onClick={onExpand}
      style={{
        padding: "10px 14px",
        borderBottom: last ? "none" : "1px solid var(--line)",
        cursor: onExpand ? "pointer" : "default",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, flex: 1, overflow: "hidden" }}>
          <span style={{
            fontSize: 13, fontWeight: 600, color: ended ? "var(--ink-4)" : "var(--ink)",
            textDecoration: ended ? "line-through" : "none",
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }} title={item.name}>
            {item.name}
          </span>
          {count > 1 && (
            <span style={{
              fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", background: "var(--bg-deep)",
              padding: "1px 6px", borderRadius: 999, flexShrink: 0,
            }}>{count}次</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 2, flexShrink: 0 }}>
          {onDuplicate && (
            <button onClick={(e) => stop(e, onDuplicate)} style={iconBtnStyle} title="快速记录"><Icon name="copy" size={13} /></button>
          )}
          {onEnd && (
            <button onClick={(e) => stop(e, onEnd)} style={iconBtnStyle} title="结束定期"><Icon name="pause" size={13} /></button>
          )}
          {onResume && (
            <button onClick={(e) => stop(e, onResume)} style={{ ...iconBtnStyle, color: "var(--down)" }} title="恢复定期"><Icon name="play" size={13} /></button>
          )}
          <button onClick={(e) => stop(e, onEdit)} style={iconBtnStyle} title="编辑"><Icon name="edit" size={13} /></button>
          <button onClick={(e) => stop(e, onDelete)} style={{ ...iconBtnStyle, color: "var(--up)" }} title="删除"><Icon name="trash" size={13} /></button>
        </div>
      </div>
      <div style={{ marginTop: 5, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <CategoryPill category={item.category} categoryName={item.category_name} />
          {dateLabel && <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{dateLabel}</span>}
        </div>
        <span className="mono" style={{ fontSize: 13, fontWeight: 700, color: ended ? "var(--ink-4)" : "var(--up)" }}>
          {item.currency && item.currency !== "CNY" && (
            <span style={{ fontSize: 9.5, fontWeight: 500, color: "var(--ink-4)", marginRight: 3 }}>{item.currency}</span>
          )}
          {fmt(item.amount, item.currency, 2)}
        </span>
      </div>
    </div>
  );
};

const LedgerRow = ({ item, last, fmt, onEdit, onDelete }) => {
  const isIncome = item.direction === "income";
  const recCol = item.recurring_type ? RECURRING_FREQ_COLORS[item.recurring_type] : null;
  return (
    <div style={{
      padding: "10px 18px",
      display: "grid",
      gridTemplateColumns: "86px 80px 1fr 160px auto",
      gap: 10,
      alignItems: "center",
      borderBottom: last ? "none" : "1px solid var(--line)",
    }}>
      <span className="mono" style={{ color: "var(--ink-4)", fontSize: 12 }}>{item.date}</span>
      <Badge tone="neutral" size="sm" style={{ overflow: "hidden", textOverflow: "ellipsis", maxWidth: 80 }}>
        {item.category_name || item.category}
      </Badge>
      <div style={{ overflow: "hidden" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, overflow: "hidden" }}>
          <span style={{ fontSize: 13, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.name}
          </span>
          {recCol && (
            <span style={{
              flexShrink: 0, fontSize: 10, fontWeight: 600, padding: "1px 6px", borderRadius: 999,
              background: recCol.bg, color: recCol.text,
            }}>
              {RECURRING_LABEL[item.recurring_type]}
            </span>
          )}
          {item.is_expired && item.recurring_type && (
            <span style={{
              flexShrink: 0, fontSize: 10, fontWeight: 500, padding: "1px 6px", borderRadius: 999,
              background: "var(--line-2)", color: "var(--ink-4)",
            }}>
              已结束
            </span>
          )}
        </div>
        {item.note && (
          <div style={{ fontSize: 11, color: "var(--ink-4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {item.note}
          </div>
        )}
      </div>
      <span className="mono" style={{ textAlign: "right", fontSize: 14, fontWeight: 600, color: "var(--up)" }}>
        {item.currency && item.currency !== "CNY" && (
          <span style={{ fontSize: 10, fontWeight: 500, color: "var(--ink-4)", marginRight: 4 }}>{item.currency}</span>
        )}
        {isIncome ? "+" : "−"}{fmt(item.amount, item.currency, 2)}
      </span>
      <div style={{ display: "flex", gap: 2 }}>
        <button onClick={onEdit} style={iconBtnStyle} title="编辑"><Icon name="edit" size={13} /></button>
        <button onClick={onDelete} style={{ ...iconBtnStyle, color: "var(--up)" }} title="删除"><Icon name="trash" size={13} /></button>
      </div>
    </div>
  );
};

const PagerButton = ({ label, onClick, disabled, active }) => (
  <button
    onClick={onClick}
    disabled={disabled}
    style={{
      minWidth: 30, height: 30, padding: "0 8px",
      background: active ? "var(--ink)" : "transparent",
      color: active ? "#fff" : disabled ? "var(--ink-5)" : "var(--ink-2)",
      border: "1px solid " + (active ? "var(--ink)" : "var(--line-2)"),
      borderRadius: 6, fontSize: 13, cursor: disabled ? "default" : "pointer",
      fontFamily: "inherit",
    }}
  >
    {label}
  </button>
);

function pagerRange(current, total) {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const pages = [1];
  if (current > 3) pages.push("…");
  for (let p = Math.max(2, current - 1); p <= Math.min(total - 1, current + 1); p++) pages.push(p);
  if (current < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

// ── Confirm Modal ─────────────────────────────────────────────────────────────

const EndRecurringModal = ({ name, onClose, onConfirm }) => {
  const [expiryDate, setExpiryDate] = React.useState(todayStr());
  const [loading, setLoading] = React.useState(false);
  const handleConfirm = async () => {
    setLoading(true);
    await onConfirm(expiryDate);
    setLoading(false);
  };
  return (
    <Modal open title="结束定期任务" onClose={onClose} width={380}>
      <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 }}>
          结束「{name}」？结束后可在「已结束」区域恢复。
        </div>
        <FieldRow label="截止日">
          <Input type="date" value={expiryDate} onChange={setExpiryDate} />
        </FieldRow>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleConfirm} disabled={loading}>确认结束</Button>
        </div>
      </div>
    </Modal>
  );
};

const ConfirmModal = ({ message, onClose, onConfirm, confirmLabel = "确认删除", confirmVariant = "danger" }) => (
  <Modal open title="确认操作" onClose={onClose} width={380}>
    <div style={{ padding: 20 }}>
      <div style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 }}>{message}</div>
      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>取消</Button>
        <Button variant={confirmVariant} onClick={onConfirm}>{confirmLabel}</Button>
      </div>
    </div>
  </Modal>
);

// ── Entry Modal (add & edit) ──────────────────────────────────────────────────

const EntryModal = ({ item, fxRates = {}, onClose, onDone }) => {
  const isEdit = !!item;
  const [form, setForm] = React.useState({
    direction: item?.direction || "expense",
    name:      item?.name || "",
    date:      item?.date || todayStr(),
    amount:    item?.amount ? String(item.amount) : "",
    currency:  item?.currency || "CNY",
    category:  item?.category || "0019",  // default: 其他 (expense)
    subcategory: item?.subcategory || "",
    note:      item?.note || "",
    recurring_type: item?.recurring_type || "",
    is_expired: item?.is_expired || false,
  });
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  const { expense: expenseCats, income: incomeCats } = React.useContext(CategoryContext);
  // options: {value: id, label: name}
  const cats = (form.direction === "income" ? incomeCats : expenseCats).map(c => ({ value: c.id, label: c.name }));

  const handleSave = async () => {
    if (!form.name.trim() || !form.amount || !form.date) {
      setError("请填写名称、日期和金额"); return;
    }
    setLoading(true); setError(null);
    try {
      const rawAmount = parseFloat(form.amount);
      const toCNY = (amt, cur) => amt * (fxRates[cur] || 1);
      const cny = toCNY(rawAmount, form.currency);
      const amounts_json = JSON.stringify(
        Object.fromEntries(CURRENCIES.map(c => [c, parseFloat((cny / (fxRates[c] || FX[c] || 1)).toFixed(2))]))
      );
      const body = {
        direction: form.direction,
        name: form.name.trim(),
        date: form.date,
        amount: rawAmount,
        currency: form.currency,
        category: form.category,
        subcategory: form.subcategory.trim() || null,
        note: form.note.trim() || null,
        recurring_type: form.recurring_type || null,
        is_expired: form.is_expired,
        amounts_json,
      };
      if (isEdit) {
        await updateLedgerEntry(item.id, body);
      } else {
        const res = await fetch("/api/ledger", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "保存失败"); }
      }
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title={isEdit ? "编辑记录" : "添加记录"} onClose={onClose} width={440}>
      <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", gap: 8 }}>
          {["expense", "income"].map(d => (
            <button key={d} onClick={() => { set("direction", d); set("category", d === "income" ? "0020" : "0019"); }}
              style={{
                flex: 1, height: 32, borderRadius: 8, border: "1px solid var(--line-2)",
                background: form.direction === d ? "var(--ink)" : "transparent",
                color: form.direction === d ? "#fff" : "var(--ink-3)",
                fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              }}>
              {d === "expense" ? "支出" : "收入"}
            </button>
          ))}
        </div>
        <FieldRow label="名称">
          <Input value={form.name} onChange={v => set("name", v)} placeholder="消费名称" />
        </FieldRow>
        <FieldRow label="日期">
          <Input type="date" value={form.date} onChange={v => set("date", v)} />
        </FieldRow>
        <FieldRow label="金额">
          <div style={{ display: "flex", gap: 6 }}>
            <Select
              value={form.currency}
              onChange={v => set("currency", v)}
              options={CURRENCIES.map(c => ({ value: c, label: c }))}
              style={{ width: 84 }}
            />
            <Input type="number" value={form.amount} onChange={v => set("amount", v)} placeholder="0.00" style={{ flex: 1 }} />
          </div>
        </FieldRow>
        <FieldRow label="分类">
          <Select value={form.category} onChange={v => set("category", v)}
            options={cats} />
        </FieldRow>
        <FieldRow label="定期">
          <Select
            value={form.recurring_type || ""}
            onChange={v => {
              set("recurring_type", v || null);
              // Default subcategory to name when first marking as recurring
              if (v && !form.subcategory && form.name) set("subcategory", form.name);
            }}
            options={[
              { value: "", label: "单次" },
              { value: "monthly", label: "每月" },
              { value: "annual", label: "每年" },
              { value: "semi_annual", label: "每半年" },
              { value: "every_4months", label: "每四个月" },
            ]} />
        </FieldRow>
        <FieldRow label="子类">
          <Input
            value={form.subcategory}
            onChange={v => set("subcategory", v)}
            placeholder={form.recurring_type ? "用于识别同一笔定期项" : "可选，用于分组"}
          />
        </FieldRow>
        <FieldRow label="备注">
          <Input value={form.note} onChange={v => set("note", v)} placeholder="可选" />
        </FieldRow>
        {error && <div style={{ color: "var(--up)", fontSize: 13 }}>{error}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>
            {loading ? "保存中…" : "保存"}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

const FieldRow = ({ label, children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "52px 1fr", alignItems: "center", gap: 10 }}>
    <span style={{ fontSize: 13, color: "var(--ink-3)" }}>{label}</span>
    {children}
  </div>
);

// ── Import Modal ──────────────────────────────────────────────────────────────

const ImportModal = ({ onClose, onDone }) => {
  const [file, setFile] = React.useState(null);
  const [result, setResult] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleImport = async () => {
    if (!file) return;
    setLoading(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch("/api/ledger/import", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Import failed");
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title="导入 Notion CSV" onClose={onClose} width={480}>
      <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>支持 Notion 消费支出记录导出的 CSV 格式，自动去重。</div>
        <input type="file" accept=".csv" onChange={e => { setFile(e.target.files[0]); setResult(null); setError(null); }} style={{ fontSize: 13 }} />
        {error && <div style={{ color: "var(--up)", fontSize: 13 }}>{error}</div>}
        {result && (
          <div style={{ background: "var(--bg-deep)", borderRadius: 8, padding: 12, fontSize: 13 }}>
            <div style={{ color: "var(--down-ink)", fontWeight: 600 }}>✓ 导入成功：{result.imported} 条</div>
            {result.skipped?.length > 0 && (
              <div style={{ color: "var(--ink-3)", marginTop: 4 }}>跳过 {result.skipped.length} 条（零金额或格式问题）</div>
            )}
          </div>
        )}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          {result
            ? <Button variant="primary" onClick={onDone}>完成</Button>
            : <Button variant="primary" onClick={handleImport} disabled={!file || loading}>
                {loading ? "导入中…" : "开始导入"}
              </Button>
          }
        </div>
      </div>
    </Modal>
  );
};

// ── Duplicate Modal (quick record from recurring template) ────────────────────

const DuplicateModal = ({ item, fmt, fxRates = {}, onClose, onDone }) => {
  const [date, setDate] = React.useState(todayStr());
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);

  const handleSave = async () => {
    setLoading(true); setError(null);
    try {
      const rawAmount = item.amount;
      const currency = item.currency || "CNY";
      const cny = rawAmount * (fxRates[currency] || 1);
      const amounts_json = JSON.stringify(
        Object.fromEntries(CURRENCIES.map(c => [c, parseFloat((cny / (fxRates[c] || FX[c] || 1)).toFixed(2))]))
      );
      const body = {
        direction: item.direction,
        name: item.name,
        date,
        amount: rawAmount,
        currency,
        category: item.category,
        orig_category: item.orig_category,
        subcategory: item.subcategory,
        note: item.note,
        recurring_type: item.recurring_type,
        is_expired: false,
        amounts_json,
      };
      const res = await fetch("/api/ledger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "保存失败"); }
      onDone();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal open title={`快速记录`} onClose={onClose} width={360}>
      <div style={{ padding: 20, display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink)" }}>{item.name}</div>
        <div style={{ fontSize: 12, color: "var(--ink-4)" }}>
          {item.category}{item.orig_category ? ` · ${item.orig_category}` : ""}
          {" · "}
          {item.currency && item.currency !== "CNY" ? `${item.currency} ` : ""}
          {fmt(item.amount, item.currency, 2)}
        </div>
        <FieldRow label="日期">
          <Input type="date" value={date} onChange={setDate} />
        </FieldRow>
        {error && <div style={{ color: "var(--up)", fontSize: 13 }}>{error}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>
            {loading ? "保存中…" : "记录"}
          </Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Series Modal (all records for a recurring series) ────────────────────────

const SeriesModal = ({ item, fmt, onClose, onEdit, onDelete }) => {
  const [rows, setRows] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    fetchLedgerSeries({
      recurring_type: item.recurring_type,
      category: item.category,
      subcategory: item.subcategory,
    })
      .then(setRows)
      .catch((e) => setError(e.message));
  }, [item.id]);

  return (
    <Modal open title={`${item.name} · 全部记录`} onClose={onClose} width={520}>
      <div style={{ padding: 18, maxHeight: 480, overflowY: "auto" }}>
        <div style={{ fontSize: 12, color: "var(--ink-4)", marginBottom: 10 }}>
          {RECURRING_LABEL[item.recurring_type] || ""} · {item.category}
          {item.subcategory ? ` · ${item.subcategory}` : ""}
          {" · "}
          {item.currency && item.currency !== "CNY" ? `${item.currency} ` : ""}
          {fmt(item.amount, item.currency, 2)}
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 13 }}>{error}</div>}
        {rows === null && !error && <div style={{ color: "var(--ink-4)", fontSize: 13 }}>加载中…</div>}
        {rows && rows.length === 0 && <div style={{ color: "var(--ink-4)", fontSize: 13 }}>暂无记录</div>}
        {rows && rows.map((r, i) => (
          <div key={r.id} style={{
            display: "grid", gridTemplateColumns: "100px 1fr auto auto", gap: 10, alignItems: "center",
            padding: "8px 0", borderBottom: i === rows.length - 1 ? "none" : "1px solid var(--line)",
          }}>
            <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{r.date}</span>
            <div style={{ overflow: "hidden", minWidth: 0 }}>
              <div style={{ fontSize: 13, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {r.name}
              </div>
              {r.note && (
                <div style={{ fontSize: 11, color: "var(--ink-4)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {r.note}
                </div>
              )}
            </div>
            <span className="mono" style={{ fontSize: 13, fontWeight: 600 }}>
              {r.currency && r.currency !== "CNY" && (
                <span style={{ fontSize: 10, fontWeight: 500, color: "var(--ink-4)", marginRight: 4 }}>{r.currency}</span>
              )}
              {fmt(r.amount, r.currency, 2)}
            </span>
            <div style={{ display: "flex", gap: 2 }}>
              <button onClick={() => onEdit(r)} style={iconBtnStyle} title="编辑"><Icon name="edit" size={13} /></button>
              <button onClick={() => onDelete(r)} style={{ ...iconBtnStyle, color: "var(--up)" }} title="删除"><Icon name="trash" size={13} /></button>
            </div>
          </div>
        ))}
      </div>
    </Modal>
  );
};

// ── Category Manager Modal ───────────────────────────────────────────────────

const ColorPicker = ({ selectedIdx, onChange }) => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
    {COLOR_PICKER_PRESETS.map((p, i) => (
      <button
        key={i}
        type="button"
        onClick={() => onChange(i)}
        style={{
          width: 28, height: 28, borderRadius: 999,
          background: p.bg,
          border: i === selectedIdx ? `2px solid ${p.text}` : "1px solid var(--line-2)",
          cursor: "pointer", padding: 0,
          display: "inline-flex", alignItems: "center", justifyContent: "center",
        }}
      >
        <span style={{ width: 10, height: 10, borderRadius: 999, background: p.text }} />
      </button>
    ))}
  </div>
);

// Find the picker index that matches a category's stored colors.
// Custom categories always pick from presets, so this matches exactly.
// Built-in categories may not match (their palette is broader); returns -1.
const matchPresetIdx = (bg, text) =>
  COLOR_PICKER_PRESETS.findIndex(p => p.bg === bg && p.text === text);

const CategoryManagerModal = ({ onClose, onChange }) => {
  const { list: categories } = React.useContext(CategoryContext);
  const [direction, setDirection] = React.useState("expense");
  const [editingId, setEditingId] = React.useState(null);
  const [editName, setEditName] = React.useState("");
  const [editColorIdx, setEditColorIdx] = React.useState(0);
  const [adding, setAdding] = React.useState(false);
  const [addName, setAddName] = React.useState("");
  const [addColorIdx, setAddColorIdx] = React.useState(0);
  const [error, setError] = React.useState(null);
  const [busy, setBusy] = React.useState(false);

  const filtered = categories.filter(c => c.direction === direction);

  const startEdit = (c) => {
    setError(null);
    setAdding(false);
    setEditingId(c.id);
    setEditName(c.name);
    const idx = matchPresetIdx(c.bg_color, c.text_color);
    setEditColorIdx(idx >= 0 ? idx : 0);
  };

  const cancelEdit = () => { setEditingId(null); setError(null); };

  const saveEdit = async (c) => {
    setError(null); setBusy(true);
    try {
      const preset = COLOR_PICKER_PRESETS[editColorIdx];
      const body = {};
      if (editName.trim() !== c.name) body.name = editName.trim();
      if (preset.bg !== c.bg_color) body.bg_color = preset.bg;
      if (preset.text !== c.text_color) body.text_color = preset.text;
      if (Object.keys(body).length > 0) {
        await updateCategory(c.id, body);
        onChange();
      }
      setEditingId(null);
    } catch (e) {
      setError(e.message);
    } finally { setBusy(false); }
  };

  const handleDelete = async (c) => {
    if (!window.confirm(`删除分类「${c.name}」？已有记录的分类标签会保留为字符串（显示为灰色）。`)) return;
    setError(null); setBusy(true);
    try {
      await deleteCategory(c.id);
      onChange();
    } catch (e) {
      setError(e.message);
    } finally { setBusy(false); }
  };

  const startAdd = () => {
    setError(null);
    setEditingId(null);
    setAdding(true);
    setAddName("");
    setAddColorIdx(0);
  };

  const saveAdd = async () => {
    if (!addName.trim()) { setError("请输入分类名称"); return; }
    setError(null); setBusy(true);
    try {
      const preset = COLOR_PICKER_PRESETS[addColorIdx];
      await createCategory({
        direction,
        name: addName.trim(),
        bg_color: preset.bg,
        text_color: preset.text,
      });
      setAdding(false);
      setAddName("");
      onChange();
    } catch (e) {
      setError(e.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal open title="管理分类" onClose={onClose} width={520}>
      <div style={{ padding: 18 }}>
        <Tabs
          variant="pill"
          value={direction}
          onChange={(d) => { setDirection(d); cancelEdit(); setAdding(false); }}
          tabs={[
            { id: "expense", label: "支出" },
            { id: "income",  label: "收入" },
          ]}
        />

        {error && (
          <div style={{ marginTop: 12, padding: "8px 12px", background: "#FBE9E9", color: "var(--up)", fontSize: 13, borderRadius: 6 }}>
            {error}
          </div>
        )}

        <div style={{ marginTop: 14, maxHeight: 360, overflowY: "auto", border: "1px solid var(--line)", borderRadius: 8 }}>
          {filtered.map((c, i) => (
            <div
              key={c.id}
              style={{
                padding: "10px 14px",
                borderBottom: i === filtered.length - 1 ? "none" : "1px solid var(--line)",
              }}
            >
              {editingId === c.id ? (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <Input value={editName} onChange={setEditName} placeholder="分类名称" />
                  <ColorPicker selectedIdx={editColorIdx} onChange={setEditColorIdx} />
                  <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                    <Button variant="secondary" onClick={cancelEdit}>取消</Button>
                    <Button variant="primary" onClick={() => saveEdit(c)} disabled={busy}>保存</Button>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <span style={{
                    background: c.bg_color, color: c.text_color,
                    padding: "3px 12px", fontSize: 12, fontWeight: 600, borderRadius: 999,
                    minWidth: 80, textAlign: "center",
                  }}>
                    {c.name}
                  </span>
                  <span style={{ flex: 1 }} />
                  {c.is_builtin ? (
                    <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", background: "var(--bg-deep)", padding: "2px 8px", borderRadius: 999 }}>
                      内置
                    </span>
                  ) : (
                    <>
                      <button onClick={() => startEdit(c)} style={iconBtnStyle} title="编辑">
                        <Icon name="edit" size={13} />
                      </button>
                      <button onClick={() => handleDelete(c)} disabled={busy} style={{ ...iconBtnStyle, color: "var(--up)" }} title="删除">
                        <Icon name="trash" size={13} />
                      </button>
                    </>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>

        {adding ? (
          <div style={{ marginTop: 12, padding: 14, border: "1px solid var(--line-2)", borderRadius: 8, display: "flex", flexDirection: "column", gap: 10 }}>
            <Input value={addName} onChange={setAddName} placeholder="新分类名称" autoFocus />
            <ColorPicker selectedIdx={addColorIdx} onChange={setAddColorIdx} />
            <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
              <Button variant="secondary" onClick={() => { setAdding(false); setError(null); }}>取消</Button>
              <Button variant="primary" onClick={saveAdd} disabled={busy}>添加</Button>
            </div>
          </div>
        ) : (
          <button
            onClick={startAdd}
            style={{
              marginTop: 12, width: "100%", padding: "10px",
              background: "transparent", border: "1px dashed var(--line-2)", borderRadius: 8,
              color: "var(--ink-3)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            + 添加 {direction === "expense" ? "支出" : "收入"} 分类
          </button>
        )}
      </div>
    </Modal>
  );
};

window.Ledger = Ledger;
window.LedgerTile = LedgerTile;
