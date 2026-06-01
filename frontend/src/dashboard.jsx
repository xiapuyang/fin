/* Dashboard — overview of all 5 modules + market summary */

const STATE_LABEL = {
  REGULAR: "盘中 Open",
  PRE:     "盘前 Pre",
  POST:    "盘后 After",
  CLOSED:  "休市 Closed",
};

// Fallback used only when the backend's /api/market-states is stale or unavailable.
// Backend (exchange_calendars) is authoritative — it handles holidays correctly.
// This client-side approximation does not.
const MARKET_HOURS = (now = new Date()) => {
  const day = now.getUTCDay();
  const t = now.getUTCHours() * 60 + now.getUTCMinutes();
  const inRange = (lo, hi) => t >= lo && t < hi;
  const weekday = day >= 1 && day <= 5;

  // US (NYSE/NASDAQ) and CA (TSX) share Eastern Time — pre 04:00, regular 09:30-16:00, post 16:00-20:00 ET.
  // Hardcoded to EDT (UTC-4); will be off by 1h when DST is not in effect.
  const etState = !weekday ? "CLOSED"
    : inRange(13 * 60 + 30, 20 * 60) ? "REGULAR"
    : inRange(20 * 60, 24 * 60)       ? "POST"
    : inRange(8 * 60, 13 * 60 + 30)  ? "PRE"
    : "CLOSED";

  // HK: HKEX Mon-Fri 09:30-12:00 and 13:00-16:00 HKT = 01:30-04:00 and 05:00-08:00 UTC
  const hkState = weekday && (inRange(1 * 60 + 30, 4 * 60) || inRange(5 * 60, 8 * 60)) ? "REGULAR" : "CLOSED";

  // CN: SSE/SZSE Mon-Fri 09:30-11:30 and 13:00-15:00 CST = 01:30-03:30 and 05:00-07:00 UTC
  const cnState = weekday && (inRange(1 * 60 + 30, 3 * 60 + 30) || inRange(5 * 60, 7 * 60)) ? "REGULAR" : "CLOSED";

  const mk = (state) => ({ state, label: STATE_LABEL[state] });
  return { US: mk(etState), HK: mk(hkState), CN: mk(cnState), CA: mk(etState) };
};

// Compute CNY value of a balance item
const _bsCNY = (it) => it.amount * (FX[it.currency] || 1);

const Dashboard = ({ onNavigate, alerts, history, timezone, currency = "CNY", displayName = "" }) => {
  timezone = timezone || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  usePrivacyMasked(); // re-render on toggle so chart Y-labels refresh
  const [now, setNow] = React.useState(new Date());

  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60 * 1000);
    return () => clearInterval(t);
  }, []);

  const curSym = { CNY: "¥", USD: "$", HKD: "HK$", CAD: "C$" }[currency] || "¥";
  const toCur = (cnyVal) => cnyVal / (FX[currency] || 1);
  const fmtM = (cnyVal) => {
    if (PRIVACY.masked) return `${curSym}•••`;
    const v = toCur(cnyVal);
    return Math.abs(v) >= 1e6
      ? `${curSym}${(v / 1e6).toFixed(2)}M`
      : Math.abs(v) >= 1e3
        ? `${curSym}${(v / 1e3).toFixed(1)}K`
        : `${curSym}${Math.round(v).toLocaleString()}`;
  };

  // ── Watchlist ───────────────────────────────────────────────────────────────
  const [watchlist, setWatchlist] = React.useState([]);
  const [watchQuotes, setWatchQuotes] = React.useState({});
  const [alertQuotes, setAlertQuotes] = React.useState({});

  React.useEffect(() => {
    fetch("/api/watchlist").then(r => r.json()).then(setWatchlist).catch(console.error);
  }, []);

  React.useEffect(() => {
    const ctrl = new AbortController();
    const watchSyms = watchlist.map(w => w.symbol);
    const alertSyms = alerts.filter(a => a.enabled).map(a => a.code);
    const all = [...new Set([...watchSyms, ...alertSyms])];
    if (!all.length) return () => ctrl.abort();
    fetch(`/api/prices?symbols=${all.map(encodeURIComponent).join(",")}`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setWatchQuotes(prev => {
          const next = { ...prev };
          watchSyms.forEach(s => { if (data[s]) next[s] = data[s]; });
          return next;
        });
        setAlertQuotes(prev => {
          const next = { ...prev };
          alertSyms.forEach(s => { if (data[s]) next[s] = data[s]; });
          return next;
        });
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [watchlist.map(w => w.symbol).join(","), alerts.filter(a => a.enabled).map(a => a.code).join(",")]);

  const watch = watchlist.map(w => {
    const q = watchQuotes[w.symbol];
    const base = SYMBOL_INDEX[w.symbol] || { code: w.symbol, name: w.name || w.symbol, market: w.market || "US", currency: w.currency || "USD" };
    return q ? { ...base, price: q.price, prevClose: q.prev_close } : base;
  }).filter(s => s.price != null);

  // ── Settings (for FIRE params + greeting) ───────────────────────────────────
  const [fireSettings, setFireSettings] = React.useState(null);
  React.useEffect(() => {
    fetch("/api/settings").then(r => r.json()).then(setFireSettings).catch(() => {});
  }, []);

  // ── Holdings → portfolio value + allocation ─────────────────────────────────
  const [positions, setPositions] = React.useState([]);
  const [portfolioLoading, setPortfolioLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([apiGetHoldings(), apiGetTransactions()])
      .then(([h, t]) => {
        const codes = [...new Set(h.map(x => x.code).filter(c => c !== "CASH"))];
        if (!codes.length) {
          setPositions(computePositions(h, t, {}));
          setPortfolioLoading(false);
          return;
        }
        apiGetPrices(codes)
          .then(prices => {
            setPositions(computePositions(h, t, prices));
            setPortfolioLoading(false);
          })
          .catch(() => {
            setPositions(computePositions(h, t, {}));
            setPortfolioLoading(false);
          });
      })
      .catch(() => setPortfolioLoading(false));
  }, []);

  // ── Ledger → entries in the past 7 days ─────────────────────────────────────
  const [ledgerWeekCount, setLedgerWeekCount] = React.useState(null);
  React.useEffect(() => {
    const since = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);
    fetch(`/api/ledger?start_date=${since}&page=1&page_size=1`)
      .then(r => r.json())
      .then(d => setLedgerWeekCount(d.total ?? 0))
      .catch(() => setLedgerWeekCount(0));
  }, []);

  // ── Balance sheet → net worth history + asset breakdown ────────────────────
  const [snapSeries, setSnapSeries] = React.useState([]);
  const [snapCount, setSnapCount] = React.useState(0);
  const [assetBreakdown, setAssetBreakdown] = React.useState([]);
  const [balLoading, setBalLoading] = React.useState(true);

  React.useEffect(() => {
    Promise.all([apiGetBalanceSnapshots(), apiGetAllBalanceItems()])
      .then(([snaps, allItems]) => {
        const sorted = [...snaps].sort((a, b) => a.snapshot_date.localeCompare(b.snapshot_date));
        const series = sorted.map(s => {
          const its = allItems.filter(i => i.snapshot_id === s.id);
          const assets = its.filter(i => i.side === "asset").reduce((sum, i) => sum + _bsCNY(i), 0);
          const liabilities = its.filter(i => i.side === "liability").reduce((sum, i) => sum + _bsCNY(i), 0);
          const liquid = its.filter(i => i.side === "asset" && ["现金", "理财", "投资"].includes(i.category))
            .reduce((sum, i) => sum + _bsCNY(i), 0);
          return { date: s.snapshot_date, net: assets - liabilities, liquid };
        });
        // Asset breakdown by category for the latest snapshot
        const latestSnap = sorted[sorted.length - 1];
        if (latestSnap) {
          const latestItems = allItems.filter(i => i.snapshot_id === latestSnap.id && i.side === "asset");
          const byCategory = {};
          latestItems.forEach(i => { byCategory[i.category] = (byCategory[i.category] || 0) + _bsCNY(i); });
          const breakdown = Object.entries(byCategory)
            .filter(([, v]) => v > 0)
            .map(([label, value]) => ({ label, value, color: BS_CAT_COLORS[label] || "#aaa" }))
            .sort((a, b) => b.value - a.value);
          setAssetBreakdown(breakdown);
        }
        setSnapSeries(series);
        setSnapCount(snaps.length);
        setBalLoading(false);
      })
      .catch(() => setBalLoading(false));
  }, []);

  // ── Derived: allocation donut ────────────────────────────────────────────────
  const isBond = (p) => p.sym?.asset_type === "bond";
  const knownMarkets = ["US", "HK", "CN", "CA", "CRYPTO"];
  const allTotal = positions.reduce((s, p) => s + p.value, 0);
  const allCashValue = positions.filter(p => p.code === "CASH").reduce((s, p) => s + p.value, 0);
  const allocation = [
    ...knownMarkets.map(m => {
      const v = positions.filter(p => p.market === m && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value, 0);
      return {
        label: { US: "美股", HK: "港股", CN: "A股", CA: "加股", CRYPTO: "加密" }[m] || m,
        value: v,
        color: { US: "#1F4FE0", HK: "#B8447B", CN: "#16A34A", CA: "#C8531C", CRYPTO: "#F7931A" }[m],
      };
    }),
    { label: "美债", value: positions.filter(isBond).reduce((s, p) => s + p.value, 0), color: "#7C3AED" },
    { label: "现金", value: allCashValue, color: "#888" },
  ].filter(b => b.value > 0);

  // ── Derived: net worth + history ─────────────────────────────────────────────
  const latestSnap = snapSeries[snapSeries.length - 1] || null;
  const netWorth = latestSnap ? latestSnap.net : allTotal;
  const netWorthSeries = snapSeries.length > 1
    ? snapSeries.map(s => ({ label: s.date.slice(5, 7) + "/" + s.date.slice(2, 4), value: s.net }))
    : allTotal > 0
      ? [{ label: "—", value: allTotal }]
      : [];
  const prevSnapValue = snapSeries.length > 1 ? snapSeries[snapSeries.length - 2].net : null;
  const momPct = prevSnapValue != null && prevSnapValue > 0
    ? (netWorth - prevSnapValue) / prevSnapValue * 100
    : null;

  // ── Derived: FIRE ────────────────────────────────────────────────────────────
  const birthDate   = fireSettings?.birth_date   || "";
  const manualAge   = fireSettings?.fire_manual_age ?? 32;
  const age = birthDate
    ? Math.max(1, Math.floor((Date.now() - new Date(birthDate).getTime()) / (365.25 * 24 * 3600 * 1000)))
    : manualAge;

  const fireMonthlyExp  = fireSettings?.fire_monthly_exp  ?? 0;
  const fireSwr         = fireSettings?.fire_swr          ?? 4.0;
  const fireInflation   = fireSettings?.fire_inflation    ?? 3;
  const fireCagr        = fireSettings?.fire_cagr         ?? 10;
  const fireMonthly     = fireSettings?.fire_monthly      ?? 0;
  const fireTargetAge   = fireSettings?.fire_target_age   ?? 50;

  const realCagr      = fireCagr - fireInflation;
  const investable    = allTotal;
  const fireTarget    = fireMonthlyExp > 0 ? (fireMonthlyExp * 12) / (fireSwr / 100) : 0;
  const fireProgress  = fireTarget > 0 ? Math.min(1, investable / fireTarget) : 0;

  const yearsToFire = React.useMemo(() => {
    if (fireTarget <= 0) return null;
    if (investable >= fireTarget) return 0;
    let v = investable, yr = 0;
    while (yr < 60 && v < fireTarget) {
      v = v * (1 + realCagr / 100) + fireMonthly * 12;
      yr++;
    }
    return v >= fireTarget ? yr : null;
  }, [investable, fireTarget, realCagr, fireMonthly]);

  // Binary search for required nominal CAGR (deterministic) to hit fireTarget by fireTargetAge
  const requiredCagr = React.useMemo(() => {
    if (fireTarget <= 0 || investable >= fireTarget) return 0;
    const targetYears = Math.max(1, fireTargetAge - age);
    const test = (nomCagr) => {
      const real = nomCagr - fireInflation;
      let v = investable;
      for (let i = 0; i < targetYears; i++) v = v * (1 + real / 100) + fireMonthly * 12;
      return v >= fireTarget;
    };
    if (!test(40)) return null;
    let lo = 0, hi = 40;
    for (let i = 0; i < 24; i++) {
      const mid = (lo + hi) / 2;
      test(mid) ? hi = mid : lo = mid;
    }
    return Math.round(hi * 10) / 10;
  }, [investable, fireTarget, age, fireTargetAge, fireInflation, fireMonthly]);

  // ── Alerts summary ───────────────────────────────────────────────────────────
  const activeAlerts = alerts.filter(a => a.enabled).length;
  const triggered = alerts.filter(a => a.triggered).length;

  // ── Modules meta ─────────────────────────────────────────────────────────────
  const modules = [
    {
      id: "alerts", icon: "bell", kicker: "MODULE 01", title: "提醒", en: "Alerts",
      color: "var(--up)",
      stat: `${activeAlerts} active · ${triggered} triggered`,
      blurb: "盘中价格 & 涨跌触发邮件",
    },
    {
      id: "holdings", icon: "wallet", kicker: "MODULE 02", title: "投资组合", en: "Portfolio",
      color: "var(--info)",
      stat: portfolioLoading ? "加载中…" : allTotal > 0 ? `${fmtM(allTotal)} · ${allocation.length} 类` : "暂无持仓",
      blurb: "成本 & 盈亏 & 年化 IRR",
    },
    {
      id: "ledger", icon: "book", kicker: "MODULE 03", title: "记账", en: "Ledger",
      color: "var(--violet)",
      stat: ledgerWeekCount == null ? "加载中…" : ledgerWeekCount > 0 ? `${ledgerWeekCount} entries this week` : "本周暂无记录",
      blurb: "支出收入 & 月度报表",
    },
    {
      id: "balance", icon: "target", kicker: "MODULE 04", title: "资产负债", en: "Balance Sheet",
      color: "var(--warn)",
      stat: balLoading ? "加载中…" : `${snapCount} 快照 · ${fmtM(netWorth)}`,
      blurb: "净资产 & 历史快照",
    },
    {
      id: "fire", icon: "spark", kicker: "MODULE 05", title: "退休计划", en: "FIRE",
      color: "var(--down)",
      stat: fireTarget > 0
        ? yearsToFire === 0 ? "已达到 FIRE 目标 🎯"
        : yearsToFire != null ? `${yearsToFire}y to 财务自由`
        : "目标不可达"
        : "请先设置月支出",
      blurb: "FIRE 数字 & 复利推演 & 里程碑",
    },
  ];

  const fireSubtitle = fireTarget > 0 && yearsToFire != null && yearsToFire > 0
    ? `Net worth tracking toward FIRE · ${yearsToFire}y to 财务自由`
    : fireTarget > 0 && yearsToFire === 0
    ? "FIRE 目标已达成 🎉"
    : "Net worth tracking toward FIRE";

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      {/* Welcome */}
      <div style={{ marginBottom: 22 }}>
        <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink-4)" }}>{(() => {
          const tzDate = new Date(now.toLocaleString("en-US", { timeZone: timezone }));
          const y = tzDate.getFullYear();
          const start = new Date(y, 0, 1);
          const week = Math.ceil(((tzDate - start) / 86400000 + start.getDay() + 1) / 7);
          const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
          return `${y} · WEEK ${String(week).padStart(2,"0")} · ${months[tzDate.getMonth()]} ${String(tzDate.getDate()).padStart(2,"0")}`;
        })()}</div>
        <h1 className="serif-cn" style={{ fontSize: 36, fontWeight: 700, margin: "6px 0 4px", letterSpacing: ".01em" }}>{displayName ? `下午好，${displayName}` : "下午好"}</h1>
        <div style={{ fontSize: 14, color: "var(--ink-3)" }}>{fireSubtitle}</div>
      </div>

      {/* Top stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 0.9fr 0.9fr 0.9fr", gap: 14, marginBottom: 22 }}>
        {/* Net Worth */}
        <Card padding={20}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>NET WORTH · 净资产</div>
            {balLoading && portfolioLoading ? (
              <div style={{ fontSize: 13, color: "var(--ink-4)", marginTop: 10 }}>加载中…</div>
            ) : (
              <>
                <div className="mono" style={{ fontSize: 36, fontWeight: 700, marginTop: 6, letterSpacing: "-.01em" }}>
                  <Private>{curSym}{(toCur(netWorth) / 1e6).toFixed(2)}<span style={{ fontSize: 18, color: "var(--ink-3)", fontWeight: 500 }}>M</span></Private>
                </div>
                <div style={{ display: "flex", gap: 12, marginTop: 4, alignItems: "center" }}>
                  {momPct != null
                    ? <><ChangeNum value={momPct} format="pct" size="sm"/><span style={{ fontSize: 12, color: "var(--ink-4)" }}>vs prev snapshot</span></>
                    : <span style={{ fontSize: 12, color: "var(--ink-4)" }}>{snapSeries.length > 0 ? "首个快照" : "来自持仓估值"}</span>
                  }
                </div>
              </>
            )}
          </div>
          {netWorthSeries.length > 1 && (
            <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px dashed var(--line)" }}>
              <AreaChart
                data={netWorthSeries} width={380} height={120}
                color="var(--ink)" fillOpacity={.06} yLabels={3}
                yFormat={v => {
                  if (PRIVACY.masked) return "•••";
                  const cv = toCur(v);
                  if (Math.abs(cv) >= 1e6) return `${(cv / 1e6).toFixed(1)}M`;
                  if (Math.abs(cv) >= 1e3) return `${(cv / 1e3).toFixed(0)}K`;
                  return Math.round(cv).toLocaleString();
                }}
              />
            </div>
          )}
        </Card>

        {/* Asset Breakdown (balance sheet categories) */}
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>ASSET BREAKDOWN · 资产分类</div>
          {balLoading ? (
            <div style={{ fontSize: 13, color: "var(--ink-4)", marginTop: 16 }}>加载中…</div>
          ) : assetBreakdown.length === 0 ? (
            <Empty icon="target" title="无资产数据" hint="在资产负债页记录资产"/>
          ) : (() => {
            const totalAssets = assetBreakdown.reduce((s, a) => s + a.value, 0);
            return (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginTop: 8 }}>
                <Donut
                  data={assetBreakdown} size={110} thickness={18}
                  centerValue={PRIVACY.masked ? `${curSym}•.•M` : `${curSym}${(toCur(totalAssets) / 1e6).toFixed(1)}M`}
                  centerSub="总资产"
                />
                <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, width: "100%" }}>
                  {assetBreakdown.map(a => {
                    const pct = totalAssets > 0 ? a.value / totalAssets * 100 : 0;
                    return (
                      <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: a.color, flexShrink: 0 }}/>
                        <span style={{ flex: 1, color: "var(--ink-2)" }}>{a.label}</span>
                        <span className="mono" style={{ color: "var(--ink-3)", fontWeight: 500 }}>{pct.toFixed(0)}%</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </Card>

        {/* Allocation (portfolio by market) */}
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>ALLOCATION · 仓位</div>
          {portfolioLoading ? (
            <div style={{ fontSize: 13, color: "var(--ink-4)", marginTop: 16 }}>加载中…</div>
          ) : allocation.length === 0 ? (
            <Empty icon="wallet" title="暂无持仓" hint="在投资组合页面添加持仓"/>
          ) : (() => {
            return (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, marginTop: 8 }}>
                <Donut
                  data={allocation} size={110} thickness={18}
                  centerValue={PRIVACY.masked ? `${curSym}•.•M` : `${curSym}${(toCur(allTotal) / 1e6).toFixed(1)}M`}
                  centerSub="投资组合"
                />
                <div style={{ display: "flex", flexDirection: "column", gap: 4, fontSize: 11, width: "100%" }}>
                  {allocation.map(a => {
                    const pct = allTotal > 0 ? a.value / allTotal * 100 : 0;
                    return (
                      <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span style={{ width: 7, height: 7, borderRadius: 2, background: a.color, flexShrink: 0 }}/>
                        <span style={{ flex: 1, color: "var(--ink-2)" }}>{a.label}</span>
                        <span className="mono" style={{ color: "var(--ink-3)", fontWeight: 500 }}>{pct.toFixed(0)}%</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </Card>

        {/* FIRE Target */}
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>FIRE TARGET · 财务自由</div>
          {fireTarget <= 0 ? (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 13, color: "var(--ink-4)", lineHeight: 1.6 }}>请在退休计划页设置月支出以计算 FIRE 目标</div>
              <Button variant="ghost" size="sm" style={{ marginTop: 10 }} onClick={() => onNavigate("fire")}>前往设置 →</Button>
            </div>
          ) : (
            <>
              <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 12 }}>
                <ProgressRing value={fireProgress} size={88} thickness={9} color="var(--down)"/>
                <div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>
                    {(fireProgress * 100).toFixed(1)}<span style={{ fontSize: 14, color: "var(--ink-3)" }}>%</span>
                  </div>
                  <div style={{ fontSize: 12, color: "var(--ink-3)" }}>
                    of <Private>{curSym}{(toCur(fireTarget) / 1e6).toFixed(1)}M</Private> target
                  </div>
                </div>
              </div>
              <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px dashed var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>Years to go</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>
                    {yearsToFire === 0 ? <span style={{ fontSize: 14, color: "var(--up)" }}>已达成</span>
                      : yearsToFire != null ? <>{yearsToFire}<span style={{ fontSize: 14, color: "var(--ink-3)" }}>y</span></>
                      : <span style={{ fontSize: 14, color: "var(--ink-4)" }}>—</span>}
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>Required CAGR</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: requiredCagr == null ? "var(--ink-4)" : requiredCagr <= 15 ? "var(--up)" : "var(--warn)" }}>
                    {requiredCagr == null ? "—"
                      : requiredCagr === 0 ? <span style={{ fontSize: 14, color: "var(--up)" }}>已达成</span>
                      : <>{requiredCagr.toFixed(1)}<span style={{ fontSize: 14 }}>%</span></>}
                  </div>
                </div>
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Modules grid */}
      <SectionHeader kicker="MODULES" title="模块导航" subtitle="Local-first · zero cloud · five focused modules"/>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 32 }}>
        {modules.map(m => (
          <ModuleCard key={m.id} mod={m} onClick={() => onNavigate(m.id)}/>
        ))}
      </div>

      {/* Bottom — watchlist + alerts overview */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card padding={0}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>关注列表 Watchlist</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{watchlist.length} 支 · 自选标的</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrow-right" onClick={() => onNavigate({ route: "alerts", category: WATCHLIST_TAB })}>Manage</Button>
          </div>
          <div>
            {watch.length === 0 && (
              <Empty icon="bell" title="自选为空" hint="在提醒页搜索标的并添加到自选"/>
            )}
            {watch.map((s, i) => {
              const ch = (s.price - s.prevClose) / s.prevClose * 100;
              return (
                <div key={s.code} style={{
                  padding: "12px 20px", display: "grid", gridTemplateColumns: "auto 1fr 90px 120px 80px", gap: 16, alignItems: "center",
                  borderBottom: i < watch.length - 1 ? "1px solid var(--line)" : "none",
                }}>
                  <MarketDot market={s.market}/>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{s.code}</span>
                      <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{s.name}</span>
                    </div>
                  </div>
                  <Sparkline data={s.spark} width={90} height={26} fill={true}/>
                  <div className="mono" style={{ textAlign: "right", fontSize: 14, fontWeight: 600 }}>
                    {fmtMoney(s.price, s.currency, 2)}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <ChangeNum value={ch} size="sm"/>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card padding={0}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>提醒概览 Alerts</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{activeAlerts} active · {triggered} fired this month</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrow-right" onClick={() => onNavigate("alerts")}>查看全部</Button>
          </div>
          <div style={{ padding: "10px 14px" }}>
            {alerts.filter(a => a.enabled).slice(0, 10).map(a => {
              const q = alertQuotes[a.code];
              const isPriceCond = a.cond.startsWith("price");
              const ch = q ? (q.price - q.prev_close) / q.prev_close * 100 : null;
              const distance = q
                ? (isPriceCond
                    ? (a.threshold - q.price) / q.price * 100
                    : a.threshold - ch)
                : null;
              const condLabel = { price_gte: "≥", price_lte: "≤", change_gte: "Δ≥", change_lte: "Δ≤" }[a.cond];
              return (
                <div key={a.id} style={{ padding: "8px 6px", display: "flex", alignItems: "center", gap: 10, borderRadius: 6 }}>
                  <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: "var(--up)", flexShrink: 0 }}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.name}</div>
                    <div style={{ fontSize: 11, color: "var(--ink-4)", display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="mono">{a.code}</span>
                      <span>·</span>
                      <span className="mono">{condLabel} {a.threshold}{isPriceCond ? "" : "%"}</span>
                    </div>
                  </div>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                    {distance != null && isFinite(distance)
                      ? `${Math.abs(distance).toFixed(1)}${isPriceCond ? "%" : "pp"} away`
                      : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
};

const ModuleCard = ({ mod, onClick }) => {
  const [hov, setHov] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: "var(--paper)", border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)", padding: 18, cursor: "pointer",
        transition: "transform .15s, box-shadow .2s, border-color .15s",
        boxShadow: hov ? "var(--shadow-md)" : "var(--shadow-sm)",
        transform: hov ? "translateY(-2px)" : "none",
        borderColor: hov ? "var(--line-strong)" : "var(--line)",
        position: "relative", overflow: "hidden",
      }}>
      <div style={{
        position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: mod.color,
      }}/>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{
          width: 32, height: 32, borderRadius: 8, background: "var(--bg-deep)",
          display: "inline-flex", alignItems: "center", justifyContent: "center", color: mod.color,
        }}><Icon name={mod.icon} size={17}/></span>
        <Icon name="arrow-right" size={14} style={{ color: hov ? "var(--ink)" : "var(--ink-5)", transition: "color .15s, transform .15s", transform: hov ? "translateX(2px)" : "none" }}/>
      </div>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".15em", color: "var(--ink-4)", marginTop: 14 }}>{mod.kicker}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
        <span className="serif-cn" style={{ fontSize: 22, fontWeight: 700 }}>{mod.title}</span>
        <span style={{ fontSize: 12, color: "var(--ink-4)", fontWeight: 500 }}>{mod.en}</span>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 6, lineHeight: 1.45 }}>{mod.blurb}</div>
      <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 12, paddingTop: 10, borderTop: "1px dashed var(--line)" }}>{mod.stat}</div>
    </div>
  );
};

window.Dashboard = Dashboard;
