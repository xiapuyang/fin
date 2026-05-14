/* Module 02 — Holdings: positions + transactions + income, per-account */

const ccySymbol = (ccy) => CURRENCY_SYMBOL[ccy] || "¥";

// ── XIRR (Newton-Raphson) ─────────────────────────────────────────────────────
// cashFlows: [{date:"YYYY-MM-DD", amount:float}]
// negative amount = cash out of investor's pocket (deposit/buy)
// positive amount = cash into investor's pocket (withdrawal/dividend/terminal value)
const xirr = (cashFlows) => {
  if (!cashFlows || cashFlows.length < 2) return null;
  if (!cashFlows.some(cf => cf.amount < 0)) return null; // need at least one outflow
  if (!cashFlows.some(cf => cf.amount > 0)) return null;
  const ms = cashFlows.map(cf => new Date(cf.date).getTime());
  const t0 = ms[0];
  const amounts = cashFlows.map(cf => cf.amount);
  const years = ms.map(d => (d - t0) / (365.25 * 86400000));
  let r = 0.1;
  for (let iter = 0; iter < 200; iter++) {
    let f = 0, df = 0;
    for (let i = 0; i < amounts.length; i++) {
      const pv = Math.pow(1 + r, years[i]);
      f  += amounts[i] / pv;
      df -= years[i] * amounts[i] / (pv * (1 + r));
    }
    if (Math.abs(f) < 1e-6) break;
    if (Math.abs(df) < 1e-12) break;
    r = r - f / df;
    if (!isFinite(r) || r <= -1) return null;
  }
  return isFinite(r) && Math.abs(r) < 100 ? r * 100 : null;
};

// ── Compute positions from holdings + transactions ────────────────────────────
const computePositions = (holdings, transactions, prices = {}) => {
  const today = new Date().toISOString().slice(0, 10);
  const sorted = [...transactions].sort((a, b) => a.date.localeCompare(b.date));

  // Synthesize virtual anchor rows for codes that have transactions but no holding snapshot.
  // Without this, a first-ever buy creates no visible position (the buy only deducts cash).
  const holdingCodes = new Set(holdings.map(h => h.code));
  const txnOnlyCodes = [...new Set(
    sorted.filter(t => t.code && t.code !== "CASH" && !holdingCodes.has(t.code)).map(t => t.code)
  )];
  const virtualHoldings = txnOnlyCodes.map(code => {
    const ref = sorted.find(t => t.code === code);
    return { id: `virtual_${code}`, code, name: code, shares: 0, avg_cost: 0,
             as_of_date: null, account: ref.account, currency: ref.currency || "USD" };
  });
  const allHoldings = virtualHoldings.length ? [...holdings, ...virtualHoldings] : holdings;

  return allHoldings.map(h => {
    const dbPrice = prices[h.code] || {};
    const symFallback = SYMBOL_INDEX[h.code] || {};
    const sym = {
      price: dbPrice.price ?? symFallback.price ?? 0,
      prevClose: dbPrice.prev_close ?? symFallback.prevClose ?? 0,
      afterHoursChangePct: (dbPrice.market_state === "POST" || dbPrice.market_state === "PRE") ? (dbPrice.after_hours_change_pct ?? null) : null,
      name: symFallback.name || dbPrice.name || h.name || h.code,
      asset_type: dbPrice.asset_type ?? null,
    };
    const currency = h.currency || "USD";
    const fx = FX[currency] || 1;
    const cutoff = h.as_of_date || null;
    const isCash = h.code === "CASH";

    let dShares = 0, dCost = 0, realized = 0;
    const relevantTxns = isCash ? [] : sorted.filter(t => t.code === h.code && (!cutoff || t.date > cutoff));
    if (isCash) {
      // transactions in the same account+currency affect cash balance
      sorted
        .filter(t => t.account === h.account && t.currency === h.currency && (!cutoff || t.date > cutoff))
        .forEach(t => {
          if (t.side === "buy") dShares -= t.shares * t.price;
          else                  dShares += t.shares * t.price;
        });
    } else {
      relevantTxns.forEach(t => {
        if (t.side === "buy") {
          dCost += t.shares * t.price;
          dShares += t.shares;
        } else {
          // When no post-snapshot buys exist yet, fall back to snapshot avg_cost as basis
          const avg = dShares ? dCost / dShares : (h.avg_cost || 0);
          realized += (t.price - avg) * t.shares;
          dCost -= avg * t.shares;
          dShares -= t.shares;
        }
      });
    }

    const initShares = h.shares || 0;
    const initCost = (h.avg_cost || 0) * initShares;
    const totalShares = initShares + dShares;
    const totalCost = initCost + dCost;
    const avgCost = totalShares > 0 ? totalCost / totalShares : (h.avg_cost || 0);
    const price = isCash ? (h.avg_cost || 1) : (sym.price || 0);
    const prevClose = isCash ? price : (sym.prevClose || 0);
    const value = price * totalShares * fx;
    const cost = avgCost * totalShares * fx;
    const pnl = value - cost;
    const pnlPct = cost ? (pnl / cost) * 100 : 0;
    const dayChange = prevClose ? ((price - prevClose) / prevClose) * 100 : 0;
    const afterHoursChangePct = sym.afterHoursChangePct ?? null;
    const realizedCNY = realized * fx;
    return { ...h, sym, currency, fx, shares: totalShares, avgCost, value, cost, pnl, pnlPct, dayChange, afterHoursChangePct, realizedCNY, txnCount: relevantTxns.length };
  }).filter(p => !String(p.id).startsWith("virtual_") || p.shares > 0);
};

// ── Compute XIRR for an account using income cash flows ───────────────────────
const computeAccountXIRR = (incomeItems, positions) => {
  const today = new Date().toISOString().slice(0, 10);
  const cfs = [];
  incomeItems.forEach(i => {
    const amt = i.amount * (FX[i.currency] || 1);
    if (i.category === "deposit")    cfs.push({ date: i.date, amount: -amt });
    else if (i.category === "withdrawal") cfs.push({ date: i.date, amount: amt });
    else                             cfs.push({ date: i.date, amount: amt });
  });
  const terminalValue = positions.reduce((s, p) => s + p.value, 0);
  if (terminalValue > 0) cfs.push({ date: today, amount: terminalValue });
  cfs.sort((a, b) => a.date.localeCompare(b.date));
  return xirr(cfs);
};

// ── Holdings root component ───────────────────────────────────────────────────
const Holdings = ({ currency = "CNY", birthDate = "" }) => {
  const [accounts, setAccounts] = React.useState([]);
  const [selectedAccountId, setSelectedAccountId] = React.useState(null);
  const [viewMode, setViewMode] = React.useState("portfolio");
  const [tab, setTab] = React.useState("positions");
  const [holdings, setHoldings] = React.useState([]);
  const [transactions, setTransactions] = React.useState([]);
  const [income, setIncome] = React.useState([]);
  const [prices, setPrices] = React.useState({});
  const [pricesReady, setPricesReady] = React.useState(false);
  const [loading, setLoading] = React.useState(true);

  const [showHoldingModal, setShowHoldingModal] = React.useState(false);
  const [editingHolding, setEditingHolding] = React.useState(null);
  const [showTxnModal, setShowTxnModal] = React.useState(false);
  const [editingTxn, setEditingTxn] = React.useState(null);
  const [txnRefresh, setTxnRefresh] = React.useState(0);
  const [showIncomeModal, setShowIncomeModal] = React.useState(false);
  const [editingIncome, setEditingIncome] = React.useState(null);
  const [showAccountModal, setShowAccountModal] = React.useState(false);
  const [editingAccount, setEditingAccount] = React.useState(null);
  const [selectedSnapshot, setSelectedSnapshot] = React.useState(null);
  React.useEffect(() => {
    Promise.all([apiGetAccounts(), apiGetHoldings(), apiGetTransactions(), apiGetIncome()])
      .then(([accts, h, t, i]) => {
        setAccounts(accts);
        if (accts.length > 0) setSelectedAccountId(accts[0].id);
        setHoldings(h); setTransactions(t); setIncome(i);
        setLoading(false);
        // Fetch prices in background — stat tiles show "—" until prices arrive
        const codes = [...new Set([...h, ...t].map(r => r.code).filter(Boolean))];
        if (codes.length > 0) {
          apiGetPrices(codes).then(p => { setPrices(p); setPricesReady(true); }).catch(() => setPricesReady(true));
        } else {
          setPricesReady(true);
        }
      })
      .catch(err => { console.error(err); setLoading(false); setPricesReady(true); });
  }, []);

  const selectedAccount = accounts.find(a => a.id === selectedAccountId) || null;
  const acctName = selectedAccount?.name || null;

  // Filter by selected account (null acctName = "全部" view)
  const acctCutoff = selectedAccount?.cutoff_date || null;
  const acctHoldings = acctName ? holdings.filter(h => h.account === acctName) : holdings;
  // All account transactions for display (no cutoff filter)
  const acctTxns = acctName ? transactions.filter(t => t.account === acctName) : transactions;
  // Cutoff-filtered transactions for P&L calculation only (excludes pre-transfer backup rows)
  const acctTxnsForCalc = acctCutoff
    ? acctTxns.filter(t => t.date >= acctCutoff)
    : acctTxns;
  const acctIncome = acctName ? income.filter(i => i.account === acctName) : income;

  // Snapshots available for this account (null/empty → shown as "未命名")
  const snapshots = React.useMemo(() => {
    const names = [...new Set(acctHoldings.map(h => h.snapshot_name || "未命名"))].sort();
    return names;
  }, [acctHoldings]);

  // Auto-select the latest snapshot when account changes or snapshots load
  React.useEffect(() => {
    if (snapshots.length > 0) setSelectedSnapshot(snapshots[snapshots.length - 1]);
    else setSelectedSnapshot(null);
  }, [acctName, snapshots.join(",")]);

  // Holdings filtered to selected snapshot only (prevents double-counting)
  // null/empty snapshot_name treated as "未命名"
  const snapshotHoldings = selectedSnapshot
    ? acctHoldings.filter(h => (h.snapshot_name || "未命名") === selectedSnapshot)
    : acctHoldings;

  // Build per-account cutoff map — used by both allPositions and allRealized
  const accountCutoffs = React.useMemo(() => {
    const m = {};
    accounts.forEach(a => { if (a.cutoff_date) m[a.name] = a.cutoff_date; });
    return m;
  }, [accounts]);

  // All-accounts aggregate — one row per (account, code), keeping the latest snapshot date
  const latestHoldings = React.useMemo(() => {
    const best = {};
    holdings.forEach(h => {
      const key = `${h.account || "__none__"}|${h.code}`;
      if (!best[key] || (h.as_of_date || "") > (best[key].as_of_date || "")) best[key] = h;
    });
    return Object.values(best);
  }, [holdings]);
  // Apply per-account cutoffs so the aggregate is consistent with per-account P&L
  const txnsForAllCalc = React.useMemo(() =>
    transactions.filter(t => !accountCutoffs[t.account] || t.date >= accountCutoffs[t.account]),
    [transactions, accountCutoffs]
  );
  const allPositions = React.useMemo(() => computePositions(latestHoldings, txnsForAllCalc, prices), [latestHoldings, txnsForAllCalc, prices]);
  const allTotal = allPositions.reduce((s, p) => s + p.value, 0);
  const allCost = allPositions.reduce((s, p) => s + p.cost, 0);
  const allUnrealized = allTotal - allCost;
  const allRealized = transactions
    .filter(t => t.realized != null && (!accountCutoffs[t.account] || t.date >= accountCutoffs[t.account]))
    .reduce((s, t) => s + (t.realized || 0) * (FX[t.currency] || 1), 0);
  const allIncomeTotal = income
    .filter(i => !["deposit","withdrawal"].includes(i.category))
    .reduce((s, i) => s + i.amount * (FX[i.currency] || 1), 0);
  const allDayPnl = allPositions.reduce((s, p) => s + p.value * p.dayChange / 100, 0);
  const allCashValue = allPositions.filter(p => p.code === "CASH").reduce((s, p) => s + p.value, 0);
  const allMarketValue = allTotal - allCashValue;
  const allXIRR = React.useMemo(() => computeAccountXIRR(income, allPositions), [income, allPositions]);

  // Per-account view — uses snapshot-filtered holdings
  const acctCcy = selectedAccount?.currency || "CNY";
  const acctFx = FX[acctCcy] || 1; // CNY rate for converting to account native currency
  const acctPositions = React.useMemo(() => computePositions(snapshotHoldings, acctTxnsForCalc, prices), [snapshotHoldings, acctTxnsForCalc, prices]);
  // acctTotal/cost/unrealized in account's native currency (divide out CNY FX, apply account FX)
  const acctTotal = acctPositions.reduce((s, p) => s + p.value / acctFx, 0);
  const acctCost = acctPositions.reduce((s, p) => s + p.cost / acctFx, 0);
  const acctUnrealized = acctTotal - acctCost;
  const acctRealized = acctTxnsForCalc
    .filter(t => t.realized != null)
    .reduce((s, t) => s + (t.realized || 0) * ((FX[t.currency] || 1) / acctFx), 0);
  const acctIncomeTotal = acctIncome
    .filter(i => !["deposit","withdrawal"].includes(i.category))
    .reduce((s, i) => s + i.amount * ((FX[i.currency] || 1) / acctFx), 0);
  const acctDeposits = acctIncome
    .filter(i => i.category === "deposit" || i.category === "withdrawal")
    .reduce((s, i) => s + i.amount * ((FX[i.currency] || 1) / acctFx) * (i.category === "withdrawal" ? -1 : 1), 0);
  const acctXIRR = React.useMemo(() => computeAccountXIRR(acctIncome, acctPositions), [acctIncome, acctPositions]);

  const summaryFx = FX[currency] || 1;
  const summarySym = ccySymbol(currency);

  const isBond = (p) => p.sym?.asset_type === "bond";
  // Resolve effective market, honouring per-account symbol_markets overrides.
  const effectiveMarket = (p) => {
    const acct = accounts.find(a => a.name === p.account);
    return acct?.symbol_markets?.[p.code] || p.market;
  };
  const knownMarkets = ["US", "HK", "CN", "CA", "CRYPTO"];
  const byMarket = [
    ...knownMarkets.map(m => {
      const v = allPositions.filter(p => effectiveMarket(p) === m && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value, 0);
      return { label: { US: "美股", HK: "港股", CN: "A股", CA: "加股", CRYPTO: "加密货币" }[m] || m, value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#16A34A", CA: "#C8531C", CRYPTO: "#F7931A" }[m] };
    }),
    { label: "美债", value: allPositions.filter(isBond).reduce((s, p) => s + p.value, 0), color: "#7C3AED" },
    { label: "其他", value: allPositions.filter(p => !knownMarkets.includes(effectiveMarket(p)) && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value, 0), color: "#aaa" },
    { label: "现金", value: allCashValue, color: "#888" },
  ].filter(b => b.value > 0);

  const acctCashValue = acctPositions.filter(p => p.code === "CASH").reduce((s, p) => s + p.value / acctFx, 0);
  const acctMarketValue = acctTotal - acctCashValue;
  const acctDayPnl = acctPositions.reduce((s, p) => s + p.value / acctFx * p.dayChange / 100, 0);
  const acctByMarket = [
    ...knownMarkets.map(m => {
      const v = acctPositions.filter(p => effectiveMarket(p) === m && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value / acctFx, 0);
      return { label: { US: "美股", HK: "港股", CN: "A股", CA: "加股", CRYPTO: "加密货币" }[m] || m, value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#16A34A", CA: "#C8531C", CRYPTO: "#F7931A" }[m] };
    }),
    { label: "美债", value: acctPositions.filter(isBond).reduce((s, p) => s + p.value / acctFx, 0), color: "#7C3AED" },
    { label: "其他", value: acctPositions.filter(p => !knownMarkets.includes(effectiveMarket(p)) && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value / acctFx, 0), color: "#aaa" },
    { label: "现金", value: acctCashValue, color: "#888" },
  ].filter(b => b.value > 0);

  const deleteAccount = async (id, name) => {
    if (!confirm(`删除账户「${name}」？\n相关持仓/交易/收入记录不会删除，但将变为未分配状态。`)) return;
    await apiDeleteAccount(id);
    const next = accounts.filter(a => a.id !== id);
    setAccounts(next);
    if (selectedAccountId === id) setSelectedAccountId(next[0]?.id || null);
  };

  if (loading) return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <div style={{ marginBottom: 22 }}>
        <div style={{ width: 120, height: 11, borderRadius: 4, background: "var(--line-2)", marginBottom: 10 }}/>
        <div style={{ width: 200, height: 28, borderRadius: 6, background: "var(--line-2)", marginBottom: 6 }}/>
        <div style={{ width: 300, height: 13, borderRadius: 4, background: "var(--line)" }}/>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        {[0,1,2,3].map(i => (
          <div key={i} style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 12, padding: 20 }}>
            <div style={{ width: "60%", height: 10, borderRadius: 3, background: "var(--line-2)", marginBottom: 12 }}/>
            <div style={{ width: "80%", height: 32, borderRadius: 6, background: "var(--line-2)", marginBottom: 8 }}/>
            <div style={{ width: "50%", height: 10, borderRadius: 3, background: "var(--line)" }}/>
          </div>
        ))}
      </div>
      <div style={{ height: 36, borderRadius: 20, background: "var(--line)", marginBottom: 16, width: 320 }}/>
      <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 12 }}>
        {[0,1,2,3,4].map(i => (
          <div key={i} style={{ padding: "14px 18px", borderBottom: i < 4 ? "1px solid var(--line)" : "none", display: "flex", gap: 16, alignItems: "center" }}>
            <div style={{ width: 8, height: 8, borderRadius: 4, background: "var(--line-2)" }}/>
            <div style={{ flex: 1, height: 12, borderRadius: 4, background: "var(--line-2)" }}/>
            <div style={{ width: 60, height: 12, borderRadius: 4, background: "var(--line)" }}/>
            <div style={{ width: 80, height: 12, borderRadius: 4, background: "var(--line)" }}/>
            <div style={{ width: 80, height: 12, borderRadius: 4, background: "var(--line-2)" }}/>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 02 · PORTFOLIO"
        title="投资组合"
        subtitle="Portfolio Tracker · 所有账户汇总 + 年化回报率"
        right={
          <div style={{ display: "flex", border: "1px solid var(--line-2)", borderRadius: 8, overflow: "hidden" }}>
            {[["portfolio","持仓"],["rebalance","再平衡"]].map(([id, label]) => (
              <button key={id} onClick={() => setViewMode(id)} style={{
                padding: "6px 16px", fontSize: 12, fontWeight: 500, cursor: "pointer", border: "none",
                background: viewMode === id ? "var(--ink)" : "transparent",
                color:      viewMode === id ? "var(--paper)" : "var(--ink-3)",
              }}>{label}</button>
            ))}
          </div>
        }
      />

      {viewMode === "rebalance" && (() => {
        const allPos = computePositions(holdings, transactions, prices);
        const allCNY = allPos.reduce((s, p) => s + p.value, 0);
        return <RebalancePanel positions={allPos} total={allCNY} currency={currency} birthDate={birthDate}/>;
      })()}
      {viewMode === "portfolio" && (<>

      {/* ── All-accounts aggregate ─────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL VALUE · 所有账户</div>
          <div className="mono" style={{ fontSize: 34, fontWeight: 700, marginTop: 4 }}>
            {pricesReady ? `${summarySym}${fmtNum(allTotal/summaryFx, 0)}` : "—"}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
            <div>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Mkt </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? `${summarySym}${fmtNum(allMarketValue/summaryFx, 2)}` : "—"}</span>
            </div>
            <div>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Cash </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? `${summarySym}${fmtNum(allCashValue/summaryFx, 2)}` : "—"}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>今日 </span>
              {pricesReady
                ? <><ChangeNum value={allTotal ? allDayPnl/allTotal*100 : 0} size="sm"/>
                    {allDayPnl !== 0 && (
                      <span className="mono" style={{ fontSize: 11, color: allDayPnl >= 0 ? "var(--up)" : "var(--down)" }}>
                        {allDayPnl >= 0 ? "+" : "−"}{summarySym}{fmtNum(Math.abs(allDayPnl/summaryFx), 0)}
                      </span>
                    )}</>
                : <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>—</span>
              }
            </div>
          </div>
          {pricesReady && allTotal > 0 && (
            <div style={{ marginTop: 14 }}>
              <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden" }}>
                {byMarket.map(b => <div key={b.label} style={{ flex: b.value || 0.001, background: b.color }}/>)}
              </div>
              <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: "var(--ink-3)" }}>
                {byMarket.map(b => <span key={b.label} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 8, height: 8, background: b.color, borderRadius: 2 }}/>{b.label} {allTotal ? (b.value/allTotal*100).toFixed(0) : 0}%</span>)}
              </div>
            </div>
          )}
        </Card>
        <StatTile label="UNREALIZED P&L · 未实现盈亏" value={pricesReady ? `${allUnrealized >= 0 ? "+" : "−"}${summarySym}${fmtNum(Math.abs(allUnrealized/summaryFx), 0)}` : "—"} tone={!pricesReady ? "neutral" : allUnrealized >= 0 ? "up" : "down"} pct={pricesReady && allCost ? (allUnrealized/allCost)*100 : null} sub={pricesReady ? `总成本 ${summarySym}${fmtNum(allCost/summaryFx, 0)}（持仓均价 × 股数）` : "加载价格中…"}/>
        <StatTile label="REALIZED + 收入 · 已实现" value={`+${summarySym}${fmtNum((allRealized+allIncomeTotal)/summaryFx, 0)}`} tone="up" sub={`已实现 ${summarySym}${fmtNum(allRealized/summaryFx, 0)} · 收入 ${summarySym}${fmtNum(allIncomeTotal/summaryFx, 0)}`}/>
        {!pricesReady
          ? <StatTile label="年化回报率 (MWRR)" value="—" tone="neutral" sub="加载价格中…"/>
          : allXIRR != null
            ? <StatTile label="年化回报率 (MWRR)" value={`${allXIRR >= 0 ? "+" : ""}${allXIRR.toFixed(1)}%`} tone={allXIRR >= 0 ? "up" : "down"} sub="所有账户 · 基于转入记录计算"/>
            : <StatTile label="年化回报率 (MWRR)" value="—" tone="neutral" sub="添加转入记录后可计算"/>
        }
      </div>

      {/* ── Account switcher ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "var(--ink-4)", marginRight: 4 }}>账户</span>
        {accounts.map(a => {
          const active = selectedAccountId === a.id;
          const btnBase = {
            border: `1px solid ${active ? "var(--ink)" : "var(--line)"}`,
            background: active ? "var(--ink)" : "var(--paper)",
            color: active ? "var(--paper)" : "var(--ink-2)",
            cursor: "pointer", transition: "all .15s",
          };
          return (
          <div key={a.id} style={{ display: "inline-flex", alignItems: "center", gap: 0 }}>
            <button onClick={() => setSelectedAccountId(a.id)} style={{ ...btnBase, padding: "5px 14px", borderRadius: "20px 0 0 20px", borderRight: "none", fontSize: 13, fontWeight: active ? 600 : 400 }}>
              {a.name}
              {a.cutoff_date && <span style={{ fontSize: 9, opacity: .6, marginLeft: 5 }}>↑{a.cutoff_date.slice(0,7)}</span>}
            </button>
            <button onClick={() => setEditingAccount(a)} title="编辑账户设置" style={{ ...btnBase, padding: "5px 6px", borderRight: "none", borderRadius: 0, color: active ? "rgba(255,255,255,0.55)" : "var(--ink-4)", fontSize: 11 }}>
              <Icon name="settings" size={11}/>
            </button>
            <button onClick={() => deleteAccount(a.id, a.name)} title={`删除账户 ${a.name}`} style={{ ...btnBase, padding: "5px 8px", borderRadius: "0 20px 20px 0", color: active ? "rgba(255,255,255,0.5)" : "var(--ink-4)", fontSize: 11, lineHeight: 1 }}>✕</button>
          </div>
        );})}
        <button
          onClick={() => setShowAccountModal(true)}
          style={{ padding: "5px 14px", borderRadius: 20, border: "1px dashed var(--line-2)", background: "transparent", color: "var(--ink-3)", cursor: "pointer", fontSize: 13 }}
        >+ 新增账户</button>
        {accounts.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--ink-4)", fontStyle: "italic" }}>暂无账户 — 点击「+ 新增账户」开始</span>
        )}
      </div>

      {/* ── Per-account stats ─────────────────────────────────────────────── */}
      {selectedAccount && (() => {
        const hpr = pricesReady && acctDeposits > 0 ? acctUnrealized / acctDeposits * 100 : null;
        const sym = ccySymbol(acctCcy);
        return (
          <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
            <Card padding={20}>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>
                ACCOUNT · {selectedAccount.name}
              </div>
              <div className="mono" style={{ fontSize: 34, fontWeight: 700, marginTop: 4 }}>
                {pricesReady ? `${sym}${fmtNum(acctTotal, 0)}` : "—"}
              </div>
              <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
                <div>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Mkt </span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? `${sym}${fmtNum(acctMarketValue, 2)}` : "—"}</span>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Cash </span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? `${sym}${fmtNum(acctCashValue, 2)}` : "—"}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>今日 </span>
                  {pricesReady
                    ? <><ChangeNum value={acctTotal ? acctDayPnl / acctTotal * 100 : 0} size="sm"/>
                        {acctDayPnl !== 0 && (
                          <span className="mono" style={{ fontSize: 11, color: acctDayPnl >= 0 ? "var(--up)" : "var(--down)" }}>
                            {acctDayPnl >= 0 ? "+" : "−"}{sym}{fmtNum(Math.abs(acctDayPnl), 0)}
                          </span>
                        )}</>
                    : <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>—</span>
                  }
                </div>
              </div>
              {pricesReady && acctTotal > 0 && (
                <div style={{ marginTop: 14 }}>
                  <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden" }}>
                    {acctByMarket.map(b => <div key={b.label} style={{ flex: b.value || 0.001, background: b.color }}/>)}
                  </div>
                  <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: "var(--ink-3)", flexWrap: "wrap" }}>
                    {acctByMarket.map(b => (
                      <span key={b.label} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                        <span style={{ width: 8, height: 8, background: b.color, borderRadius: 2 }}/>{b.label} {acctTotal ? (b.value / acctTotal * 100).toFixed(0) : 0}%
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </Card>
            <StatTile
              label="UNREALIZED P&L · 持有收益"
              value={pricesReady ? `${acctUnrealized >= 0 ? "+" : "−"}${sym}${fmtNum(Math.abs(acctUnrealized), 0)}` : "—"}
              tone={!pricesReady ? "neutral" : acctUnrealized >= 0 ? "up" : "down"}
              pct={hpr}
              sub={pricesReady ? `持有收益率 ${hpr != null ? (hpr >= 0 ? "+" : "") + hpr.toFixed(2) + "%" : "—"} · 净转入 ${sym}${fmtNum(acctDeposits, 0)}` : "加载价格中…"}
            />
            <StatTile label="REALIZED + 收入 · 已实现" value={`+${sym}${fmtNum((acctRealized + acctIncomeTotal), 0)}`} tone="up" sub={`已实现 ${sym}${fmtNum(acctRealized, 0)} · 收入 ${sym}${fmtNum(acctIncomeTotal, 0)}`}/>
            {!pricesReady
              ? <StatTile label="年化回报率 (MWRR)" value="—" tone="neutral" sub="加载价格中…"/>
              : acctXIRR != null
                ? <StatTile label="年化回报率 (MWRR)" value={`${acctXIRR >= 0 ? "+" : ""}${acctXIRR.toFixed(1)}%`} tone={acctXIRR >= 0 ? "up" : "down"} sub={`${selectedAccount.name} · 基于转入记录计算`}/>
                : <StatTile label="年化回报率 (MWRR)" value="—" tone="neutral" sub="添加转入记录后可计算"/>
            }
          </div>
        );
      })()}

      {/* ── Inner tabs ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <Tabs variant="underline" value={tab} onChange={setTab} tabs={[
          { id: "positions",    label: "持仓 Positions",     count: acctPositions.length },
          { id: "transactions", label: "交易记录 Trades",    count: acctTxns.length },
          { id: "income",       label: "收入/转账 Income",   count: acctIncome.length },
          { id: "dividends",    label: "分红日历 Calendar",  count: acctIncome.filter(i => i.category === "dividend").length || null },
        ]}/>
      </div>

      {tab === "positions"    && <PositionsTable positions={acctPositions} total={acctTotal} acctCcy={acctCcy} acctFx={acctFx}
          snapshots={snapshots} selectedSnapshot={selectedSnapshot} onSnapshotChange={setSelectedSnapshot}
          onAddHolding={() => { setEditingHolding(null); setShowHoldingModal(true); }}
          onEditHolding={h => { setEditingHolding(h); setShowHoldingModal(true); }}
          onDeleteHolding={id => apiDeleteHolding(id).then(() => setHoldings(p => p.filter(h => h.id !== id))).catch(console.error)}
        />}
      {tab === "transactions" && <TransactionsTable
          account={acctName}
          refreshKey={txnRefresh}
          allSymbols={[...new Set(acctTxns.map(t => t.code))].sort()}
          assetTypeOf={code => (prices[code] || {}).asset_type ?? null}
          onAdd={() => { setEditingTxn(null); setShowTxnModal(true); }}
          onEdit={t => { setEditingTxn(t); setShowTxnModal(true); }}
          onDelete={id => apiDeleteTransaction(id).then(() => setTransactions(p => p.filter(t => t.id !== id))).catch(console.error)}
          onImportDone={txns => setTransactions(txns)}
        />}
      {tab === "income"       && <IncomeTable items={acctIncome} total={acctIncomeTotal} acctCcy={acctCcy} acctFx={acctFx}
          onAdd={() => { setEditingIncome(null); setShowIncomeModal(true); }}
          onEdit={i => { setEditingIncome(i); setShowIncomeModal(true); }}
          onDelete={id => apiDeleteIncome(id).then(() => setIncome(p => p.filter(i => i.id !== id))).catch(console.error)}
          onImportDone={all => setIncome(all)}
          defaultAccount={acctName}
        />}
      {tab === "dividends"    && <DividendCalendar incomeItems={acctIncome} positions={acctPositions} acctCcy={acctCcy} acctFx={acctFx}/>}

{showHoldingModal && <HoldingModal editing={editingHolding} accounts={accounts} defaultAccount={acctName} onClose={() => setShowHoldingModal(false)}
          onSaved={h => { setHoldings(prev => editingHolding ? prev.map(x => x.id === h.id ? h : x) : [...prev, h]); setShowHoldingModal(false); }}/>}
      {showTxnModal && <TransactionModal editing={editingTxn} accounts={accounts} defaultAccount={acctName} onClose={() => setShowTxnModal(false)}
          onSaved={t => { setTransactions(prev => editingTxn ? prev.map(x => x.id === t.id ? t : x) : [t, ...prev]); setTxnRefresh(r => r + 1); setShowTxnModal(false); }}/>}
      {showIncomeModal && <IncomeModal editing={editingIncome} accounts={accounts} defaultAccount={acctName} onClose={() => setShowIncomeModal(false)}
          onSaved={i => { setIncome(prev => editingIncome ? prev.map(x => x.id === i.id ? i : x) : [i, ...prev]); setShowIncomeModal(false); }}/>}
      {showAccountModal && <AccountModal onClose={() => setShowAccountModal(false)}
          onSaved={a => { setAccounts(prev => [...prev, a]); setSelectedAccountId(a.id); setShowAccountModal(false); }}/>}
      {editingAccount && <AccountEditModal account={editingAccount} onClose={() => setEditingAccount(null)}
          onSaved={a => { setAccounts(prev => prev.map(x => x.id === a.id ? a : x)); setEditingAccount(null); }}/>}

      </>)}
    </div>
  );
};

// ── Shared stat tile ──────────────────────────────────────────────────────────
const StatTile = ({ label, value, sub, tone, pct }) => (
  <Card padding={20}>
    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{label}</div>
    <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 6 }}>
      <div className="mono" style={{ fontSize: 28, fontWeight: 700, color: tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--ink)" }}>{value}</div>
      {pct != null && <ChangeNum value={pct} size="sm"/>}
    </div>
    <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{sub}</div>
  </Card>
);

// ── Positions table ───────────────────────────────────────────────────────────
const priceDp = (p) => p.sym?.asset_type === "mutualfund" ? 4 : 2;

const PositionsTable = ({ positions, total, acctCcy = "CNY", acctFx = 1, snapshots, selectedSnapshot, onSnapshotChange, onAddHolding, onEditHolding, onDeleteHolding }) => {
  const sym = ccySymbol(acctCcy);
  return <Card padding={0}>
    <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>持仓明细 Positions</div>
        {snapshots && snapshots.length > 0 && (
          <select value={selectedSnapshot || ""} onChange={e => onSnapshotChange(e.target.value || null)}
            style={{ fontSize: 13, border: "1px solid var(--line)", borderRadius: 6, padding: "3px 8px", background: "var(--paper)", color: "var(--ink)", cursor: "pointer" }}>
            {snapshots.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        )}
      </div>
      <Button size="sm" variant="secondary" icon="plus" onClick={onAddHolding}>添加持仓</Button>
    </div>
    {positions.length === 0
      ? <Empty icon="wallet" title="暂无持仓" hint="点击「添加持仓」手动录入，或先添加交易记录"/>
      : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: "24px 1fr 70px 95px 90px 80px 100px 110px 56px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
            <span/><span>POSITION</span>
            <span style={{textAlign:"right"}}>SHARES</span><span style={{textAlign:"right"}}>AVG COST</span>
            <span style={{textAlign:"right"}}>PRICE</span><span style={{textAlign:"right"}}>DAY</span>
            <span style={{textAlign:"right"}}>VALUE ({acctCcy})</span><span style={{textAlign:"right"}}>未实现 P&L</span>
            <span/>
          </div>
          {[...positions].sort((a,b) => b.value - a.value).map((p, i, arr) => {
            const cash = p.code === "CASH";
            return (
            <div key={p.id} style={{ display: "grid", gridTemplateColumns: "24px 1fr 70px 95px 90px 80px 100px 110px 56px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < arr.length-1 ? "1px solid var(--line)" : "none" }}>
              <MarketDot market={p.market}/>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>{cash ? `现金 ${p.currency}` : p.code}</span>
                  {!cash && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{p.sym.name || p.name || ""}</span>}
                  {!cash && p.txnCount > 0 && <span style={{ fontSize: 10, color: "var(--ink-4)", padding: "1px 6px", border: "1px solid var(--line)", borderRadius: 4 }}>{p.txnCount} 笔</span>}
                </div>
              </div>
              <span className="mono" style={{textAlign:"right",fontSize:12}}>{cash ? "—" : (p.shares > 0 ? p.shares : "—")}</span>
              <span className="mono" style={{textAlign:"right",fontSize:12,color:"var(--ink-3)"}}>{cash ? "—" : fmtMoney(p.avgCost, p.currency, priceDp(p))}</span>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}>{cash ? "—" : (p.sym.price ? fmtMoney(p.sym.price, p.currency, priceDp(p)) : "—")}</span>
              <div style={{textAlign:"right"}}>
                {cash ? "—" : <ChangeNum value={p.dayChange} size="sm"/>}
                {!cash && p.afterHoursChangePct != null && (
                  <div style={{fontSize:10,color:"var(--ink-4)",marginTop:1}}>
                    盘后 <ChangeNum value={p.afterHoursChangePct} size="sm"/>
                  </div>
                )}
              </div>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}>{sym}{fmtNum(p.value / acctFx, 0)}</span>
              <div style={{textAlign:"right"}}>
                {cash ? <span style={{fontSize:12,color:"var(--ink-4)"}}>现金</span> : (
                  <>
                    <ChangeNum value={p.pnlPct} size="sm"/>
                    <div className="mono" style={{ fontSize: 10.5, color: p.pnl >= 0 ? "var(--up)" : "var(--down)", marginTop: 1 }}>
                      {p.pnl >= 0 ? "+" : "−"}{sym}{fmtNum(Math.abs(p.pnl / acctFx), 0)}
                    </div>
                  </>
                )}
              </div>
              <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                <button style={iconBtn} title="编辑" onClick={() => onEditHolding(p)}><Icon name="edit" size={13}/></button>
                <button style={{ ...iconBtn, color: "var(--up)" }} title="删除" onClick={() => { if (confirm(`删除 ${cash ? "现金" : p.code} 持仓？`)) onDeleteHolding(p.id); }}><Icon name="x" size={13}/></button>
              </div>
            </div>
          );})}
        </>
      )}
  </Card>;
};

// ── Transactions table ────────────────────────────────────────────────────────
const TransactionsTable = ({ account, refreshKey = 0, allSymbols = [], assetTypeOf = () => null, onAdd, onEdit, onDelete, onImportDone }) => {
  const fileRef = React.useRef(null);
  const [importMsg, setImportMsg] = React.useState(null);
  const [symFilter, setSymFilter] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [data, setData] = React.useState({ items: [], total: 0 });

  const totalPages = Math.max(1, Math.ceil(data.total / 30));

  const fetchPage = React.useCallback((pg, sym) => {
    apiGetTransactionsPaged({ page: pg, pageSize: 30, symbol: sym, account: account || "" })
      .then(setData)
      .catch(console.error);
  }, [account]);

  React.useEffect(() => { fetchPage(page, symFilter); }, [page, symFilter, fetchPage, refreshKey]);

  const handleSymFilter = (v) => { setSymFilter(v); setPage(1); };

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = "";
    try {
      const result = await apiImportTransactions(file);
      const all = await apiGetTransactions();
      onImportDone(all);
      fetchPage(1, symFilter);
      setPage(1);
      setImportMsg(`导入 ${result.imported} 条，跳过 ${result.skipped.length} 条`);
      setTimeout(() => setImportMsg(null), 4000);
    } catch (err) {
      setImportMsg(`导入失败: ${err.message}`);
      setTimeout(() => setImportMsg(null), 4000);
    }
  };

  return (
    <Card padding={0}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>交易记录 Transactions</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>买入 & 卖出 · 用于计算平均成本和已实现盈亏</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {importMsg && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{importMsg}</span>}
          <select value={symFilter} onChange={e => handleSymFilter(e.target.value)}
            style={{ fontSize: 12, padding: "4px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", cursor: "pointer" }}>
            <option value="">全部 Symbol</option>
            {allSymbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleImport}/>
          <Button size="sm" variant="secondary" onClick={() => fileRef.current.click()}>导入 CSV</Button>
          <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>新增记录</Button>
        </div>
      </div>
      {data.total === 0
        ? <Empty icon="book" title="暂无交易记录" hint="点击「新增记录」手动添加，或「导入 CSV」批量导入 Notion 数据"/>
        : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "100px 80px 90px 80px 100px 110px 130px 1fr 52px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
              <span>DATE</span><span>TYPE</span><span>SYMBOL</span>
              <span style={{textAlign:"right"}}>SHARES</span><span style={{textAlign:"right"}}>PRICE</span>
              <span style={{textAlign:"right"}}>AMOUNT</span><span style={{textAlign:"right"}}>REALIZED</span>
              <span style={{paddingLeft:24}}>NOTE</span><span/>
            </div>
            {data.items.map((t, i) => {
              const amt = t.shares * t.price;
              return (
                <div key={t.id} style={{ display: "grid", gridTemplateColumns: "100px 80px 90px 80px 100px 110px 130px 1fr 52px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < data.items.length-1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
                  <span className="mono" style={{color:"var(--ink-3)"}}>{t.date}</span>
                  <Badge tone={t.side === "buy" ? "up" : "down"} solid={false} size="sm">{t.side === "buy" ? "买入" : "卖出"}</Badge>
                  <span className="mono" style={{fontWeight:600}}>{t.code}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.shares > 0 ? t.shares : "—"}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.price > 0 ? fmtMoney(t.price, t.currency, assetTypeOf(t.code) === "mutualfund" ? 4 : 2) : "—"}</span>
                  <span className="mono" style={{textAlign:"right",fontWeight:600}}>{amt > 0 ? fmtMoney(amt, t.currency, 0) : "—"}</span>
                  <span className="mono" style={{textAlign:"right",color:t.realized>=0?"var(--up)":t.realized!=null?"var(--down)":"var(--ink-4)",fontWeight:600}}>
                    {t.realized != null ? (t.realized >= 0 ? "+" : "−") + fmtMoney(Math.abs(t.realized), t.currency, 0) : "—"}
                  </span>
                  <span style={{color:"var(--ink-3)",fontSize:12,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",paddingLeft:24}}>{t.note || ""}</span>
                  <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                    <button style={iconBtn} title="编辑" onClick={() => onEdit(t)}><Icon name="edit" size={13}/></button>
                    <button style={{ ...iconBtn, color: "var(--up)" }} title="删除" onClick={() => { if (confirm(`删除此交易记录？`)) onDelete(t.id).then(() => fetchPage(page, symFilter)); }}><Icon name="x" size={13}/></button>
                  </div>
                </div>
              );
            })}
            {totalPages > 1 && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, padding: "12px 18px", borderTop: "1px solid var(--line)" }}>
                <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                  style={{ ...iconBtn, opacity: page === 1 ? 0.3 : 1 }}><Icon name="arrow-left" size={14}/></button>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{page} / {totalPages}</span>
                <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                  style={{ ...iconBtn, opacity: page === totalPages ? 0.3 : 1 }}><Icon name="arrow-right" size={14}/></button>
              </div>
            )}
          </>
        )}
    </Card>
  );
};

// ── Income / Transfer table ───────────────────────────────────────────────────
const IncomeTable = ({ items, total, acctCcy = "CNY", acctFx = 1, onAdd, onEdit, onDelete, onImportDone, defaultAccount }) => {
  const sorted = [...items].sort((a,b) => b.date.localeCompare(a.date));
  const fileRef = React.useRef(null);
  const [importMsg, setImportMsg] = React.useState(null);

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = "";
    try {
      const result = await apiImportIncome(file, defaultAccount || null);
      onImportDone && onImportDone(result.income);
      setImportMsg(`导入 ${result.imported} 条${result.skipped.length ? `，跳过 ${result.skipped.length} 条` : ""}`);
    } catch (ex) {
      setImportMsg(`导入失败：${ex.message}`);
    }
  };
  const sym = ccySymbol(acctCcy);
  const catColors = { dividend: "#1F8A4C", interest: "#2D5BD9", option: "#6B4FB8", deposit: "#2D9CDB", withdrawal: "#C8460F" };
  const catLabels = { dividend: "分红 Dividend", interest: "利息 Interest", option: "期权 Option", deposit: "转入 Deposit", withdrawal: "转出 Withdrawal" };
  // Summarise by category in account currency
  const byCat = items.reduce((acc, i) => {
    const acctAmt = i.amount * (FX[i.currency] || 1) / acctFx;
    acc[i.category] = (acc[i.category] || 0) + acctAmt;
    return acc;
  }, {});

  return (
    <div>
      {Object.keys(byCat).length > 0 && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12, marginBottom: 14 }}>
          {Object.entries(byCat).map(([cat, v]) => (
            <Card key={cat} padding={16}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: catColors[cat] || "#888" }}/>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-3)" }}>{catLabels[cat] || cat}</span>
              </div>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: "var(--up)" }}>
                {cat === "deposit" ? "-" : "+"}{sym}{fmtNum(v, 0)}
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>累计 {items.filter(i => i.category === cat).length} 笔</div>
            </Card>
          ))}
        </div>
      )}
      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>收入 & 转账</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>分红 / 利息 / 期权权利金 / 账户转入转出 — 收入合计 {sym}{fmtNum(total, 0)}</div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            {importMsg && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{importMsg}</span>}
            <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleImport}/>
            <Button size="sm" variant="secondary" onClick={() => fileRef.current.click()}>导入 CSV</Button>
            <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>添加记录</Button>
          </div>
        </div>
        {sorted.length === 0
          ? <Empty icon="spark" title="暂无记录" hint="添加分红、利息、转入转出等记录"/>
          : (
            <>
              <div style={{ display: "grid", gridTemplateColumns: "100px 110px 1.4fr 130px 130px 1fr 52px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
                <span>DATE</span><span>TYPE</span><span>SOURCE</span>
                <span style={{textAlign:"right"}}>AMOUNT</span><span style={{textAlign:"right"}}>≈ {acctCcy}</span>
                <span>NOTE</span><span/>
              </div>
              {sorted.map((i, idx) => {
                const acctAmt = i.amount * (FX[i.currency] || 1) / acctFx;
                const isTransfer = ["deposit","withdrawal"].includes(i.category);
                const sign = isTransfer ? (i.category === "withdrawal" ? "+" : "−") : "+";
                return (
                  <div key={i.id} style={{ display: "grid", gridTemplateColumns: "100px 110px 1.4fr 130px 130px 1fr 52px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: idx < sorted.length-1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
                    <span className="mono" style={{color:"var(--ink-3)"}}>{i.date}</span>
                    <Badge tone={i.category === "dividend" ? "down" : i.category === "option" ? "violet" : i.category === "withdrawal" ? "up" : "info"} size="sm">{catLabels[i.category] || i.category}</Badge>
                    <span>{i.source}</span>
                    <span className="mono" style={{textAlign:"right",fontWeight:600,color:"var(--up)"}}>
                      {sign}{fmtMoney(i.amount, i.currency, 2)}
                    </span>
                    <span className="mono" style={{textAlign:"right",color:"var(--ink-3)"}}>
                      {i.currency !== acctCcy ? `${sign}${sym}${fmtNum(acctAmt, 0)}` : "—"}
                    </span>
                    <span style={{color:"var(--ink-3)",fontSize:12}}>{i.note || "—"}</span>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      <button style={iconBtn} title="编辑" onClick={() => onEdit(i)}><Icon name="edit" size={13}/></button>
                      <button style={{ ...iconBtn, color: "var(--up)" }} title="删除" onClick={() => { if (confirm(`删除此记录？`)) onDelete(i.id); }}><Icon name="x" size={13}/></button>
                    </div>
                  </div>
                );
              })}
            </>
          )}
      </Card>
    </div>
  );
};

// ── Dividend Calendar ─────────────────────────────────────────────────────────
// incomeItems: manually-entered income records (category=dividend shown as confirmed)
// positions: current account positions — used to query yfinance for dividend events

const MONTH_NAMES = ["一月","二月","三月","四月","五月","六月","七月","八月","九月","十月","十一月","十二月"];
const WEEK_HDR = ["一","二","三","四","五","六","日"];

const divFreq = (hist) => {
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  return Math.max(hist.filter(h => new Date(h.date) >= oneYearAgo).length, 1);
};

const DivUpcomingStrip = ({ upcoming, posByCode, acctFx, sym }) => {
  if (!upcoming.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 8 }}>即将除权</div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
        {upcoming.map(u => {
          const pos = posByCode[u.code];
          const shares = pos?.shares || 0;
          const divFx = FX[pos?.currency || "USD"] || 1;
          const perShare = u.per_payment;
          const estPmt = perShare && shares ? perShare * shares * divFx / acctFx : null;
          return (
            <Card key={u.code} padding={14} style={{ minWidth: 120 }}>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{u.code}</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)", marginTop: 2 }}>{u.ex_date}</div>
              {perShare && <div className="mono" style={{ fontSize: 11, color: "var(--up)", marginTop: 2 }}>{ccySymbol(pos?.currency || "USD")}{perShare.toFixed(3)}/sh</div>}
              {estPmt && <div className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--up)", marginTop: 3 }}>≈ {sym}{fmtNum(estPmt, 0)}</div>}
            </Card>
          );
        })}
      </div>
    </div>
  );
};

const DivMonthGrid = ({ year, month, today, eventsByDate, selectedDay, setSelectedDay, prevMonth, nextMonth }) => {
  const firstDayMon = (new Date(year, month - 1, 1).getDay() + 6) % 7;
  const daysInMonth = new Date(year, month, 0).getDate();
  const cells = [...Array(firstDayMon).fill(null), ...Array.from({ length: daysInMonth }, (_, i) => i + 1)];
  const selectedKey = selectedDay ? `${year}-${String(month).padStart(2,"0")}-${String(selectedDay).padStart(2,"0")}` : null;
  const selectedEvents = selectedKey ? (eventsByDate[selectedKey] || []) : [];

  return (
    <Card padding={20}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <button onClick={prevMonth} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink-3)", padding: "4px 10px", fontSize: 18 }}>‹</button>
        <span className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>{year} 年 {MONTH_NAMES[month - 1]}</span>
        <button onClick={nextMonth} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink-3)", padding: "4px 10px", fontSize: 18 }}>›</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 3, marginBottom: 4 }}>
        {WEEK_HDR.map(h => (
          <div key={h} style={{ textAlign: "center", fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".1em", padding: "3px 0" }}>{h}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 3 }}>
        {cells.map((day, idx) => {
          if (!day) return <div key={`e${idx}`}/>;
          const dk = `${year}-${String(month).padStart(2,"0")}-${String(day).padStart(2,"0")}`;
          const events = eventsByDate[dk] || [];
          const hasUpcoming = events.some(e => e.type === "upcoming");
          const hasYf = events.some(e => e.type === "yf");
          const hasIncome = events.some(e => e.type === "income");
          const isToday = dk === today;
          const isSel = day === selectedDay;
          const hasAny = events.length > 0;
          return (
            <div key={day} onClick={() => hasAny ? setSelectedDay(day === selectedDay ? null : day) : null}
              style={{
                borderRadius: 6, padding: "6px 3px", textAlign: "center",
                cursor: hasAny ? "pointer" : "default",
                background: isSel ? "var(--up)" : hasIncome ? "rgba(31,138,76,0.12)" : hasYf ? "rgba(31,138,76,0.06)" : "transparent",
                border: hasUpcoming ? "1.5px dashed var(--up)" : isToday ? "1.5px solid var(--ink-3)" : "1.5px solid transparent",
              }}>
              <div style={{ fontSize: 12, fontWeight: isToday ? 700 : 400, color: isSel ? "white" : dk > today ? "var(--ink-4)" : "var(--ink-3)" }}>{day}</div>
              {hasAny && (
                <div style={{ display: "flex", justifyContent: "center", gap: 2, marginTop: 3 }}>
                  {hasIncome   && <span style={{ width: 5, height: 5, borderRadius: "50%", background: isSel ? "white" : "var(--up)" }}/>}
                  {hasYf       && <span style={{ width: 5, height: 5, borderRadius: "50%", background: isSel ? "rgba(255,255,255,0.7)" : "rgba(31,138,76,0.5)" }}/>}
                  {hasUpcoming && <span style={{ width: 5, height: 5, borderRadius: "50%", background: isSel ? "rgba(255,255,255,0.7)" : "var(--up)", opacity: 0.6 }}/>}
                </div>
              )}
            </div>
          );
        })}
      </div>
      <div style={{ display: "flex", gap: 14, marginTop: 14, borderTop: "1px solid var(--line)", paddingTop: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--up)", display: "inline-block" }}/>已录入收入</div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "rgba(31,138,76,0.4)", display: "inline-block" }}/>历史除权日</div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 10, height: 10, borderRadius: 2, border: "1.5px dashed var(--up)", display: "inline-block" }}/>即将除权</div>
      </div>
      {selectedEvents.length > 0 && (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-3)", marginBottom: 8 }}>{selectedKey}</div>
          {selectedEvents.map((e, idx) => (
            <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: idx < selectedEvents.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
              <div>
                <span style={{ fontWeight: 600, marginRight: 6 }}>{e.source || e.code || "—"}</span>
                <Badge size="sm" tone={e.type === "income" ? "down" : "info"}>
                  {e.type === "income" ? "已收" : e.type === "upcoming" ? "除权日" : "历史"}
                </Badge>
              </div>
              <span className="mono" style={{ color: "var(--up)", fontWeight: 600 }}>
                {e.type === "income" ? `+${fmtMoney(e.amount, e.currency, 2)}` : e.amount ? `${ccySymbol(e.currency || "USD")}${e.amount.toFixed(3)}/sh` : "—"}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
};

const DivStockList = ({ divData, posByCode, today, acctFx, sym }) => (
  <>
    {Object.entries(divData).sort(([, dA], [, dB]) => {
      const yA = dA.annual_rate || 0;
      const yB = dB.annual_rate || 0;
      return yB - yA;
    }).map(([code, d]) => {
      const pos = posByCode[code];
      const shares = pos?.shares || 0;
      const divFx = FX[pos?.currency || "USD"] || 1;
      const estAnnual = d.annual_rate && shares ? d.annual_rate * shares * divFx / acctFx : null;
      const price = pos?.sym?.price;
      const yieldPct = d.annual_rate && price ? (d.annual_rate / price * 100) : null;
      return (
        <Card key={code} padding={14}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700 }}>{code}</div>
              {d.ex_date && <div style={{ fontSize: 11, color: d.ex_date >= today ? "var(--up)" : "var(--ink-4)", marginTop: 2 }}>除权 {d.ex_date}</div>}
            </div>
            <div style={{ textAlign: "right" }}>
              {d.annual_rate && <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{ccySymbol(pos?.currency || "USD")}{d.annual_rate.toFixed(2)}/sh/yr</div>}
              {yieldPct && <div className="mono" style={{ fontSize: 12, color: "var(--up)", marginTop: 2 }}>{yieldPct.toFixed(2)}%</div>}
            </div>
          </div>
          {estAnnual && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>≈ {sym}{fmtNum(estAnnual, 0)}/年</div>}
        </Card>
      );
    })}
  </>
);

const DividendCalendar = ({ incomeItems, positions = [], acctCcy = "CNY", acctFx = 1 }) => {
  const today = new Date().toISOString().slice(0, 10);
  const now = new Date();
  const [year, setYear] = React.useState(now.getFullYear());
  const [month, setMonth] = React.useState(now.getMonth() + 1);
  const [selectedDay, setSelectedDay] = React.useState(null);
  const [divData, setDivData] = React.useState({});
  const [loading, setLoading] = React.useState(false);
  const [fetchError, setFetchError] = React.useState(false);

  const sym = ccySymbol(acctCcy);
  const posByCode = React.useMemo(() => Object.fromEntries(positions.map(p => [p.code, p])), [positions]);
  const codeKey = React.useMemo(
    () => [...new Set(positions.map(p => p.code).filter(c => c && c !== "CASH"))].sort().join(","),
    [positions]
  );

  React.useEffect(() => {
    const codes = codeKey ? codeKey.split(",") : [];
    setDivData({}); setSelectedDay(null); setFetchError(false);
    if (!codes.length) return;
    setLoading(true);
    let cancelled = false;
    apiGetDividends(codes)
      .then(d => { if (!cancelled) setDivData(d); })
      .catch(() => { if (!cancelled) setFetchError(true); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [codeKey]);

  const eventsByDate = React.useMemo(() => {
    const m = {};
    const add = (date, ev) => { if (!m[date]) m[date] = []; m[date].push(ev); };
    Object.entries(divData).forEach(([code, d]) => {
      const posCcy = posByCode[code]?.currency || "USD";
      const hist = d.history || [];
      hist.forEach(h => add(h.date, { type: "yf", code, amount: h.amount, currency: posCcy }));
      if (d.ex_date) add(d.ex_date, { type: "upcoming", code, amount: d.annual_rate ? d.annual_rate / divFreq(hist) : null, currency: posCcy });
    });
    (incomeItems || []).filter(i => i.category === "dividend").forEach(i =>
      add(i.date, { type: "income", code: i.code, amount: i.amount, currency: i.currency, source: i.source })
    );
    return m;
  }, [divData, incomeItems, posByCode]);

  const upcoming = React.useMemo(() => Object.entries(divData)
    .filter(([, d]) => d.ex_date && d.ex_date >= today)
    .map(([code, d]) => ({ code, ex_date: d.ex_date, annual_rate: d.annual_rate, per_payment: d.annual_rate ? d.annual_rate / divFreq(d.history || []) : null }))
    .sort((a, b) => a.ex_date.localeCompare(b.ex_date))
    .slice(0, 8), [divData, today]);

  const totalEstAnnual = React.useMemo(() => Object.entries(divData).reduce((sum, [code, d]) => {
    if (!d.annual_rate) return sum;
    const pos = posByCode[code];
    return sum + d.annual_rate * (pos?.shares || 0) * (FX[pos?.currency || "USD"] || 1) / acctFx;
  }, 0), [divData, posByCode, acctFx]);

  const prevMonth = () => { if (month === 1) { setYear(y => y - 1); setMonth(12); } else setMonth(m => m - 1); setSelectedDay(null); };
  const nextMonth = () => { if (month === 12) { setYear(y => y + 1); setMonth(1); } else setMonth(m => m + 1); setSelectedDay(null); };
  const hasAnyData = Object.keys(divData).length > 0 || (incomeItems || []).some(i => i.category === "dividend");

  return (
    <div>
      <DivUpcomingStrip upcoming={upcoming} posByCode={posByCode} acctFx={acctFx} sym={sym} />
      {loading && !hasAnyData && <div style={{ textAlign: "center", padding: "40px 0", color: "var(--ink-4)", fontSize: 13 }}>正在从 Yahoo Finance 获取分红数据…</div>}
      {!loading && fetchError && <div style={{ textAlign: "center", padding: "20px 0", color: "var(--ink-3)", fontSize: 13 }}>获取分红数据失败，请稍后重试</div>}
      {!loading && !fetchError && !hasAnyData && <Empty icon="spark" title="持仓中暂无分红记录" hint="只有付息股票（ETF、股票）才会显示分红日历，指数和无分红股票不会出现"/>}
      {hasAnyData && (
        <div style={{ maxWidth: 1120, display: "grid", gridTemplateColumns: "1fr 440px", gap: 16, alignItems: "start" }}>
          <DivMonthGrid year={year} month={month} today={today} eventsByDate={eventsByDate} selectedDay={selectedDay} setSelectedDay={setSelectedDay} prevMonth={prevMonth} nextMonth={nextMonth} />
          {Object.keys(divData).length === 1 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "calc((100% - 10px) / 2)" }}>
              {totalEstAnnual > 0 && (
                <Card padding={14}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 4 }}>预估年度分红</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--up)" }}>{sym}{fmtNum(totalEstAnnual, 0)}</span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)" }}>/ 年</span>
                  </div>
                </Card>
              )}
              <DivStockList divData={divData} posByCode={posByCode} today={today} acctFx={acctFx} sym={sym} />
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {totalEstAnnual > 0 && (
                <Card padding={14} style={{ gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 4 }}>预估年度分红</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--up)" }}>{sym}{fmtNum(totalEstAnnual, 0)}</span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)" }}>/ 年</span>
                  </div>
                </Card>
              )}
              <DivStockList divData={divData} posByCode={posByCode} today={today} acctFx={acctFx} sym={sym} />
            </div>
          )}
        </div>
      )}
    </div>
  );
};

// ── Rebalance constants ────────────────────────────────────────────────────────

const RB_EQUITY_TYPES = ["equity", "etf", "mutualfund", "cryptocurrency"];

const computeAge = (birthDate) => {
  if (!birthDate) return 30;
  const ms = Date.now() - new Date(birthDate).getTime();
  return Math.max(1, Math.min(99, Math.floor(ms / (365.25 * 24 * 3600 * 1000))));
};

const computeAgeRuleBuckets = (age) => [
  { label: "股票 Equity",  pct: Math.max(0, 100 - age), color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, markets: [], isCash: false },
  { label: "债券 / 现金",   pct: Math.min(100, age),     color: "#5C6270", codes: [], assetTypes: ["bond"],        markets: [], isCash: true  },
];

const RB_PRESETS = [
  {
    id: "personal",
    label: "个人配置",
    author: "自定义",
    quote: "按实际持仓设定目标比例",
    buckets: [
      { label: "美股 US",    pct: 50, color: "#1F4FE0", codes: [], assetTypes: ["equity","etf"], markets: ["US"],            isCash: false },
      { label: "港股 HK",    pct: 15, color: "#B8447B", codes: [], assetTypes: ["equity","etf"], markets: ["HK"],            isCash: false },
      { label: "A 股 CN",    pct: 10, color: "#C8460F", codes: [], assetTypes: ["equity","etf"], markets: ["CN"],            isCash: false },
      { label: "债券 Bonds",  pct:  5, color: "#5C8AE6", codes: [], assetTypes: ["bond"],         markets: [],               isCash: false },
      { label: "黄金 Gold",   pct:  5, color: "#C8A000", codes: ["GLD","IAU","SGOL","2840.HK"],   assetTypes: [],            markets: [], isCash: false },
      { label: "现金 Cash",   pct: 15, color: "#5C6270", codes: [],                               assetTypes: [], markets: [], isCash: true  },
    ],
  },
  {
    id: "60_40",
    label: "经典 60/40",
    author: "John Bogle",
    quote: "时间证明，简单的股债平衡胜过大多数主动策略。",
    buckets: [
      { label: "股票 Equity",  pct: 60, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { label: "债券 / 现金",   pct: 40, color: "#5C6270", codes: [], assetTypes: ["bond"],        isCash: true  },
    ],
  },
  {
    id: "70_30",
    label: "积极 70/30",
    author: "Vanguard",
    quote: "收益与波动之间的黄金分割，适合30-45岁积累期。",
    buckets: [
      { label: "股票 Equity",  pct: 70, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { label: "债券 / 现金",   pct: 30, color: "#5C6270", codes: [], assetTypes: ["bond"],        isCash: true  },
    ],
  },
  {
    id: "all_weather",
    label: "全天候",
    author: "Ray Dalio",
    quote: "没有人能预测未来，所以要准备好应对所有经济季节。",
    buckets: [
      { label: "股票 Equity",      pct: 30,  color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { label: "长债 LT Bonds",    pct: 40,  color: "#5C8AE6", codes: [], assetTypes: ["bond"],         isCash: false },
      { label: "中债 MT Bonds",    pct: 15,  color: "#B8447B", codes: [], assetTypes: [],               isCash: false },
      { label: "黄金 Gold",        pct: 7.5, color: "#C8460F", codes: [], assetTypes: [],               isCash: false },
      { label: "大宗 Commodities", pct: 7.5, color: "#9C6E3A", codes: [], assetTypes: [],               isCash: true  },
    ],
  },
  {
    id: "permanent",
    label: "永久组合",
    author: "Harry Browne",
    quote: "无论通胀、通缩、繁荣还是萧条，各分一杯羹。",
    buckets: [
      { label: "股票 Equity",   pct: 25, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { label: "长债 LT Bonds", pct: 25, color: "#5C8AE6", codes: [], assetTypes: ["bond"],         isCash: false },
      { label: "现金 Cash",     pct: 25, color: "#5C6270", codes: [], assetTypes: [],               isCash: true  },
      { label: "黄金 Gold",     pct: 25, color: "#C8460F", codes: [], assetTypes: [],               isCash: false },
    ],
  },
  {
    id: "age_rule",
    label: "100 - 年龄",
    author: "生命周期理论",
    quote: "随年龄增长，逐步降低风险敞口。股票% = 100 - 年龄，其余配置债券/现金。",
    buckets: null,
  },
];

const RB_TRIGGER_MODES = [
  { id: "calendar", label: "日历触发", desc: "按固定周期检查，不管偏离大小" },
  { id: "absolute", label: "绝对偏离", desc: "任一桶偏离超过 N pp 触发" },
  { id: "relative", label: "相对偏离", desc: "任一桶偏离超过目标 N% 触发" },
  { id: "hybrid",   label: "混合触发", desc: "日历 + 绝对偏离 (Vanguard 标准)" },
];

const RB_CAL_OPTIONS = [
  { value: "monthly",   label: "每月" },
  { value: "quarterly", label: "每季度" },
  { value: "semi",      label: "每半年" },
  { value: "annual",    label: "每年" },
];

const RB_DEFAULT_CONFIG = {
  presetId: "personal",
  buckets: [
    { label: "美股 US",    pct: 50, color: "#1F4FE0", codes: [], assetTypes: ["equity","etf"], markets: ["US"],            isCash: false },
    { label: "港股 HK",    pct: 15, color: "#B8447B", codes: [], assetTypes: ["equity","etf"], markets: ["HK"],            isCash: false },
    { label: "A 股 CN",    pct: 10, color: "#C8460F", codes: [], assetTypes: ["equity","etf"], markets: ["CN"],            isCash: false },
    { label: "债券 Bonds",  pct:  5, color: "#5C8AE6", codes: [], assetTypes: ["bond"],         markets: [],               isCash: false },
    { label: "黄金 Gold",   pct:  5, color: "#C8A000", codes: ["GLD","IAU","SGOL","2840.HK"],   assetTypes: [], markets: [], isCash: false },
    { label: "现金 Cash",   pct: 15, color: "#5C6270", codes: [], assetTypes: [],               markets: [],               isCash: true  },
  ],
  trigger: { mode: "hybrid", calFreq: "annual", absDriftPp: 5, relDriftPct: 20 },
  birthDate: "",
};

// ── Rebalance edit modal ────────────────────────────────────────────────────────

const RebalanceEditModal = ({ config, birthDate = "", onSave, onClose }) => {
  const [draft, setDraft] = React.useState(JSON.parse(JSON.stringify(config)));
  const [codesTexts, setCodesTexts] = React.useState(config.buckets.map(b => (b.codes || []).join(", ")));

  const applyPreset = (p) => {
    const newBuckets = p.id === "age_rule"
      ? computeAgeRuleBuckets(computeAge(birthDate))
      : JSON.parse(JSON.stringify(p.buckets));
    setDraft(d => ({ ...d, presetId: p.id, buckets: newBuckets }));
    setCodesTexts(newBuckets.map(b => (b.codes || []).join(", ")));
  };
  const updateBucket = (i, key, val) => setDraft(d => ({
    ...d, buckets: d.buckets.map((b, j) => j === i ? { ...b, [key]: val } : b),
  }));
  const handleSave = (d) => {
    const finalDraft = {
      ...d,
      buckets: d.buckets.map((b, i) => ({
        ...b,
        codes: codesTexts[i].split(",").map(s => s.trim().toUpperCase()).filter(Boolean),
      })),
    };
    onSave(finalDraft);
  };
  const sumPct = draft.buckets.reduce((s, b) => s + (parseFloat(b.pct) || 0), 0);
  const valid = Math.abs(sumPct - 100) < 0.5;

  return (
    <Modal open={true} onClose={onClose} title="编辑目标配置" width={500}>
      <div style={{ padding: "16px 20px", maxHeight: "72vh", overflowY: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", marginBottom: 8, textTransform: "uppercase", letterSpacing: ".1em" }}>选择预设</div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 20 }}>
          {RB_PRESETS.map(p => (
            <button key={p.id} onClick={() => applyPreset(p)} style={{
              padding: "4px 12px", borderRadius: 999, fontSize: 12, fontWeight: 500, cursor: "pointer", border: "1px solid",
              borderColor: draft.presetId === p.id ? "var(--accent)" : "var(--line-2)",
              background:  draft.presetId === p.id ? "var(--accent-soft)" : "transparent",
              color:       draft.presetId === p.id ? "var(--accent)" : "var(--ink-3)",
            }}>{p.label}</button>
          ))}
        </div>

        {(() => {
          const pr = RB_PRESETS.find(p => p.id === draft.presetId);
          return pr && pr.id !== "personal" && (
            <div style={{ background: "var(--bg-deep)", borderRadius: 8, padding: "10px 14px", marginBottom: 18, borderLeft: "3px solid var(--accent)" }}>
              <div style={{ fontSize: 12, color: "var(--ink-2)", fontStyle: "italic" }}>"{pr.quote}"</div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>— {pr.author}</div>
            </div>
          );
        })()}

        {draft.presetId === "age_rule" && (
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>出生日期</span>
            {birthDate ? (
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>
                {birthDate} · {computeAge(birthDate)} 岁 · 股 {Math.max(0, 100 - computeAge(birthDate))}% / 债 {Math.min(100, computeAge(birthDate))}%
              </span>
            ) : (
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>未设置 · 请在右上角设置中填写</span>
            )}
          </div>
        )}

        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", marginBottom: 10, textTransform: "uppercase", letterSpacing: ".1em" }}>资产桶 · 目标比例</div>
        {draft.buckets.map((b, i) => (
          <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "10px 1fr 64px 20px", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ width: 10, height: 10, background: b.color, borderRadius: 2, display: "block" }}/>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{b.label}</span>
              <Input value={String(b.pct)} onChange={v => updateBucket(i, "pct", parseFloat(v) || 0)} inputMode="decimal" style={{ textAlign: "right" }}/>
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>%</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 18 }}>
              <span style={{ fontSize: 10.5, color: "var(--ink-4)", flexShrink: 0, width: 52 }}>代码覆盖</span>
              <input
                value={codesTexts[i]}
                onChange={e => setCodesTexts(t => t.map((v, j) => j === i ? e.target.value : v))}
                placeholder="逗号分隔，如 013308, TEC.TO"
                style={{ flex: 1, fontSize: 11.5, border: "1px solid var(--line-2)", borderRadius: 5, padding: "3px 8px", background: "var(--bg-deep)", color: "var(--ink)", outline: "none" }}
              />
            </div>
          </div>
        ))}
        <div style={{ textAlign: "right", fontSize: 12, color: valid ? "var(--down)" : "var(--up)", marginBottom: 16 }}>
          合计 {sumPct.toFixed(1)}% {valid ? "✓" : "· 需等于 100%"}
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={() => handleSave(draft)} disabled={!valid}>保存</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Rebalance panel ────────────────────────────────────────────────────────────

const RB_DEFAULT_TRIGGER = { mode: "hybrid", calFreq: "annual", absDriftPp: 5, relDriftPct: 20 };

const rehydrateBuckets = (buckets, id, birthDate) => {
  const tpl = id === "age_rule"
    ? computeAgeRuleBuckets(computeAge(birthDate))
    : RB_PRESETS.find(p => p.id === id)?.buckets;
  return tpl && buckets
    ? buckets.map((b, i) => ({ ...b, assetTypes: b.assetTypes ?? tpl[i]?.assetTypes ?? [] }))
    : buckets;
};

const RebalancePanel = ({ positions, total, currency = "CNY", birthDate = "" }) => {
  const [activeId, setActiveId] = React.useState("personal");
  const [perPreset, setPerPreset] = React.useState({});
  const [editOpen, setEditOpen] = React.useState(false);
  const [expandedBucket, setExpandedBucket] = React.useState(null);

  React.useEffect(() => {
    fetch("/api/rebalance")
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (!d) return;
        if (d.presets) {
          // migrate "current" key → "personal"
          const presets = d.presets;
          if (presets["current"] && !presets["personal"]) {
            presets["personal"] = presets["current"];
            delete presets["current"];
          }
          const activeId = d.activeId === "current" ? "personal" : (d.activeId || "personal");
          setActiveId(activeId);
          setPerPreset(presets);
        } else if (d.presetId) {
          // migrate v1 flat format
          const id = d.presetId;
          const buckets = rehydrateBuckets(d.buckets, id, d.birthDate);
          setActiveId(id);
          setPerPreset({ [id]: { buckets, trigger: d.trigger, birthDate: d.birthDate || "" } });
        }
      })
      .catch(() => {});
  }, []);

  // Derive active config — fall back to preset defaults if not yet customised
  const activeData = perPreset[activeId] || {};
  const defaultBuckets = activeId === "age_rule"
    ? computeAgeRuleBuckets(computeAge(birthDate))
    : JSON.parse(JSON.stringify(RB_PRESETS.find(p => p.id === activeId)?.buckets || []));
  const config = {
    presetId: activeId,
    buckets:   activeData.buckets || defaultBuckets,
    trigger:   activeData.trigger || RB_DEFAULT_TRIGGER,
  };

  const persist = (id, data, newMap) => {
    const next = newMap || { ...perPreset, [id]: data };
    setPerPreset(next);
    fetch("/api/rebalance", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activeId: id, presets: next }),
    }).catch(() => {});
  };

  const saveConfig = (updates) => {
    const data = { ...activeData, ...updates };
    persist(activeId, data);
  };

  const switchPreset = (newId) => {
    setActiveId(newId);
    setExpandedBucket(null);
    const existing = perPreset[newId];
    const newBuckets = newId === "age_rule"
      ? computeAgeRuleBuckets(computeAge(birthDate))
      : JSON.parse(JSON.stringify(RB_PRESETS.find(p => p.id === newId)?.buckets || []));
    const newData = existing || { buckets: newBuckets, trigger: config.trigger };
    persist(newId, newData, { ...perPreset, [newId]: newData });
  };

  const setTrigger = (k, v) => saveConfig({ trigger: { ...config.trigger, [k]: v } });

  // Use CNY-denominated total for consistent percentage calculations
  // (total prop is in account native currency; p.value is always CNY)
  const totalCNY = positions.reduce((s, p) => s + p.value, 0);
  const dispFx  = FX[currency] || 1;
  const dispSym = ccySymbol(currency);

  // Allocate positions to buckets; isCash bucket absorbs unallocated remainder
  const matchesBucket = (p, b) => {
    if (p.code === "CASH") return false; // CASH always falls to isCash remainder
    if (b.codes?.includes(p.code)) return true;
    const hasType = b.assetTypes?.length > 0;
    const hasMkt  = b.markets?.length > 0;
    if (!hasType && !hasMkt) return false;
    const typeOk = !hasType || b.assetTypes.includes(p.sym?.asset_type);
    const mktOk  = !hasMkt  || b.markets.includes(_guessMarket(p.code));
    return typeOk && mktOk;
  };

  // Build per-bucket matched position sets so cash bucket = unallocated remainder
  const codedPositionSet = new Set();
  const codedValues = config.buckets.map(b => {
    if (b.isCash) return { matched: [], value: 0 };
    const matched = positions.filter(p => matchesBucket(p, b));
    matched.forEach(p => codedPositionSet.add(p));
    return { matched, value: matched.reduce((s, p) => s + p.value, 0) };
  });
  const codedAllocated = codedValues.reduce((s, c) => s + c.value, 0);

  const buckets = config.buckets.map((b, i) => {
    const bPositions = b.isCash
      ? positions.filter(p => !codedPositionSet.has(p))
      : codedValues[i].matched;
    const current = b.isCash ? (totalCNY - codedAllocated) : codedValues[i].value;
    const curPct  = totalCNY ? (current / totalCNY) * 100 : 0;
    const drift   = curPct - b.pct;
    const relDrift = b.pct > 0 ? (Math.abs(drift) / b.pct) * 100 : 0;
    return { ...b, current, curPct, drift, relDrift, delta: (b.pct / 100) * totalCNY - current, bPositions };
  });

  const { mode, absDriftPp, relDriftPct, calFreq } = config.trigger;
  const triggered = mode === "calendar" ? [] : buckets.filter(b =>
    mode === "absolute" ? Math.abs(b.drift) >= absDriftPp :
    mode === "relative" ? b.relDrift >= relDriftPct :
    Math.abs(b.drift) >= absDriftPp  // hybrid: absolute threshold
  );

  const preset   = RB_PRESETS.find(p => p.id === config.presetId) || RB_PRESETS[0];
  const calLabel = (RB_CAL_OPTIONS.find(o => o.value === calFreq) || {}).label || "";

  return (
    <Card padding={20}>
      {/* Header: preset chips + edit button */}
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          {RB_PRESETS.map(p => (
            <button key={p.id} onClick={() => switchPreset(p.id)}
              style={{
                padding: "4px 12px", borderRadius: 999, fontSize: 12, fontWeight: 500, cursor: "pointer", border: "1px solid",
                borderColor: activeId === p.id ? "var(--accent)" : "var(--line-2)",
                background:  activeId === p.id ? "var(--accent-soft)" : "transparent",
                color:       activeId === p.id ? "var(--accent)" : "var(--ink-3)",
              }}
            >{p.label}</button>
          ))}
        </div>
        <Button variant="secondary" icon="settings" onClick={() => setEditOpen(true)}>编辑目标</Button>
      </div>

      {/* Strategy quote */}
      <div style={{ background: "var(--bg-deep)", borderRadius: 8, padding: "10px 14px", marginBottom: 20, borderLeft: "3px solid var(--accent)" }}>
        <div style={{ fontSize: 13, color: "var(--ink-2)", fontStyle: "italic" }}>"{preset.quote}"</div>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 6 }}>
          <div style={{ fontSize: 11, color: "var(--ink-4)" }}>— {preset.author}</div>
          {config.presetId === "age_rule" && (
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              {birthDate ? (
                <span style={{ fontSize: 11, color: "var(--ink-4)" }}>
                  {computeAge(birthDate)} 岁 · 股 {Math.max(0, 100 - computeAge(birthDate))}% / 债 {Math.min(100, computeAge(birthDate))}%
                </span>
              ) : (
                <span style={{ fontSize: 11, color: "var(--ink-4)" }}>未设置出生日期</span>
              )}
              <span style={{ fontSize: 10.5, color: "var(--ink-5)" }}>· 在右上角设置中修改</span>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 28 }}>
        {/* Left: drift bars */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>偏离度 Drift vs Target</div>
          {[...buckets].sort((a, b) => b.curPct - a.curPct).map((b, i) => {
            const fires = triggered.includes(b);
            const isExpanded = expandedBucket === i;
            return (
              <div key={i} style={{ marginBottom: 18 }}>
                {/* Header: label (clickable) + amount + pct */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <button onClick={() => setExpandedBucket(isExpanded ? null : i)} style={{
                    display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, fontWeight: 500,
                    background: "none", border: "none", cursor: "pointer", padding: 0, color: "var(--ink)",
                  }}>
                    <span style={{ width: 8, height: 8, background: b.color, borderRadius: 2 }}/>
                    {b.label}
                    <span style={{ fontSize: 10, color: "var(--ink-4)", marginLeft: 2 }}>{isExpanded ? "▲" : "▼"}</span>
                  </button>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-2)" }}>
                    {dispSym}{fmtNum(b.current / dispFx / 1000, 1)}k
                    <span style={{ color: "var(--ink-5)", margin: "0 5px" }}>·</span>
                    <span style={{ color: b.drift > 0 ? "var(--up)" : b.drift < 0 ? "var(--down)" : "var(--ink-3)", fontWeight: 600 }}>{b.curPct.toFixed(1)}%</span>
                    <span style={{ color: "var(--ink-4)" }}> → {b.pct}%</span>
                  </span>
                </div>

                {/* Current bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <span style={{ fontSize: 9, color: "var(--ink-4)", width: 22, textAlign: "right" }}>当前</span>
                  <div style={{ position: "relative", flex: 1, height: 7, background: "var(--bg-deep)", borderRadius: 3 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, width: `${Math.min(b.curPct, 100)}%`, height: "100%", background: b.color, borderRadius: 3 }}/>
                    <div style={{ position: "absolute", left: `${b.pct}%`, top: -3, width: 2, height: 13, background: "var(--ink-3)", borderRadius: 1 }}/>
                  </div>
                </div>

                {/* Target bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ fontSize: 9, color: "var(--ink-5)", width: 22, textAlign: "right" }}>目标</span>
                  <div style={{ position: "relative", flex: 1, height: 5, background: "var(--bg-deep)", borderRadius: 3 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, width: `${b.pct}%`, height: "100%", background: b.color, opacity: 0.25, borderRadius: 3 }}/>
                    <div style={{ position: "absolute", left: `${b.pct}%`, top: -3, width: 2, height: 11, background: "var(--ink-3)", borderRadius: 1 }}/>
                  </div>
                </div>

                {/* Drift row */}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, paddingLeft: 28 }}>
                  <span className="mono" style={{ color: fires ? "var(--up)" : "var(--ink-4)", fontWeight: fires ? 600 : 400 }}>
                    drift {b.drift >= 0 ? "+" : ""}{b.drift.toFixed(1)}pp
                    {mode !== "calendar" && <span style={{ color: "var(--ink-4)", fontWeight: 400 }}> · {b.relDrift.toFixed(0)}%相对</span>}
                    {fires && " ⚠"}
                  </span>
                  <span className="mono" style={{ color: "var(--ink-4)" }}>
                    建议 {b.delta >= 0 ? "买入" : "卖出"} {dispSym}{fmtNum(Math.abs(b.delta) / dispFx / 1000, 1)}k
                  </span>
                </div>

                {/* Expanded positions */}
                {isExpanded && (
                  <div style={{ marginTop: 8, marginLeft: 28, padding: "8px 12px", background: "var(--bg-deep)", borderRadius: 6, borderLeft: `3px solid ${b.color}` }}>
                    {b.bPositions.length === 0 ? (
                      <div style={{ fontSize: 11, color: "var(--ink-4)", fontStyle: "italic" }}>
                        {b.isCash ? "暂无未分配持仓" : "无匹配持仓"}
                      </div>
                    ) : (
                      <>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: "2px 12px", fontSize: 10, color: "var(--ink-5)", fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 6 }}>
                          <span>代码</span><span>账户</span><span style={{ textAlign: "right" }}>金额</span><span style={{ textAlign: "right" }}>占比</span>
                        </div>
                        {b.bPositions.map((p, j) => (
                          <div key={j} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: "3px 12px", fontSize: 11.5, padding: "3px 0", borderTop: j > 0 ? "1px solid var(--line)" : "none", alignItems: "center" }}>
                            <span style={{ fontWeight: 600, color: "var(--ink-2)" }}>{p.code}</span>
                            <span style={{ color: "var(--ink-4)", fontSize: 11 }}>{p.account}</span>
                            <span className="mono" style={{ color: "var(--ink-2)", textAlign: "right" }}>{dispSym}{fmtNum(p.value / dispFx / 1000, 1)}k</span>
                            <span className="mono" style={{ color: "var(--ink-4)", textAlign: "right" }}>{totalCNY ? (p.value / totalCNY * 100).toFixed(1) : 0}%</span>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Right: trigger config */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>触发规则 Rules</div>

          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 14 }}>
            {RB_TRIGGER_MODES.map(m => (
              <button key={m.id} onClick={() => setTrigger("mode", m.id)} style={{
                padding: "8px 10px", borderRadius: 8, border: "1px solid", textAlign: "left", cursor: "pointer",
                borderColor: mode === m.id ? "var(--accent)" : "var(--line-2)",
                background:  mode === m.id ? "var(--accent-soft)" : "var(--bg-deep)",
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: mode === m.id ? "var(--accent)" : "var(--ink-2)" }}>{m.label}</div>
                <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 2, lineHeight: 1.35 }}>{m.desc}</div>
              </button>
            ))}
          </div>

          <div style={{ borderTop: "1px dashed var(--line)", paddingTop: 12, display: "flex", flexDirection: "column", gap: 10 }}>
            {(mode === "calendar" || mode === "hybrid") && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>检查周期</span>
                <Select value={calFreq} onChange={v => setTrigger("calFreq", v)} options={RB_CAL_OPTIONS} style={{ width: 96 }}/>
              </div>
            )}
            {(mode === "absolute" || mode === "hybrid") && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>绝对阈值</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Input value={String(absDriftPp)} onChange={v => setTrigger("absDriftPp", parseFloat(v) || 5)} inputMode="decimal" style={{ width: 56, textAlign: "right" }}/>
                  <span style={{ fontSize: 12, color: "var(--ink-4)", width: 18 }}>pp</span>
                </div>
              </div>
            )}
            {(mode === "relative" || mode === "hybrid") && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>相对阈值</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Input value={String(relDriftPct)} onChange={v => setTrigger("relDriftPct", parseFloat(v) || 20)} inputMode="decimal" style={{ width: 56, textAlign: "right" }}/>
                  <span style={{ fontSize: 12, color: "var(--ink-4)", width: 18 }}>%</span>
                </div>
              </div>
            )}
          </div>

          {/* Trigger status */}
          <div style={{
            marginTop: 14, padding: "10px 12px", borderRadius: 8,
            background: triggered.length > 0 ? "var(--warn-soft)" : "var(--bg-deep)",
            border: `1px solid ${triggered.length > 0 ? "#E8C06080" : "var(--line-2)"}`,
          }}>
            {mode === "calendar" ? (
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>📅 {calLabel}定期检查 · 偏离不触发</div>
            ) : triggered.length > 0 ? (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#7A4D0E", marginBottom: 4 }}>⚠ {triggered.length} 个桶已触发</div>
                {triggered.map((b, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#7A4D0E" }}>
                    {b.label}：{b.drift >= 0 ? "+" : ""}{b.drift.toFixed(1)}pp ({b.relDrift.toFixed(0)}% 相对)
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>✓ 所有桶在阈值内，无需再平衡</div>
            )}
            {mode === "hybrid" && (
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: triggered.length > 0 ? 6 : 0 }}>
                {calLabel}检查 · 超 {absDriftPp}pp 再平衡
              </div>
            )}
          </div>
        </div>
      </div>

      {editOpen && (
        <RebalanceEditModal config={config} birthDate={birthDate} onSave={next => {
          saveConfig({ buckets: next.buckets });
          setEditOpen(false);
        }} onClose={() => setEditOpen(false)}/>
      )}
    </Card>
  );
};

// ── CRUD Modals ───────────────────────────────────────────────────────────────

const MARKET_CCY = { US: "USD", HK: "HKD", CN: "CNY", CA: "CAD", CRYPTO: "USD" };

const _guessMarket = (code) => {
  if (code.endsWith(".HK") || code.startsWith("^HSI") || code.startsWith("^HSCE") || code.startsWith("^HSTECH")) return "HK";
  if (code.endsWith(".SS") || code.endsWith(".SZ")) return "CN";
  if (code.endsWith(".TO") || code.endsWith(".V")) return "CA";
  if (/^\d{6}$/.test(code)) return "CN"; // bare 6-digit = A-share / CN-listed fund
  return "US";
};

// Symbol autocomplete combobox — presets + backend fallback for unknown tickers
const SymbolCombobox = ({ value, onChange, placeholder }) => {
  const [open, setOpen] = React.useState(false);
  const [backendSym, setBackendSym] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const upper = (value || "").toUpperCase();

  const presetMatches = upper.length === 0 ? [] : Object.values(SYMBOLS).flat().filter(
    s => s.code.startsWith(upper)
  ).slice(0, 8);

  // Backend lookup when no preset matches
  React.useEffect(() => {
    setBackendSym(null);
    if (upper.length === 0 || presetMatches.length > 0) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      setLoading(true);
      fetch(`/api/quote/${encodeURIComponent(upper)}`, { signal: ctrl.signal })
        .then(r => r.ok ? r.json() : null)
        .then(q => {
          if (q) setBackendSym({ code: upper, name: q.name || upper, market: _guessMarket(upper), currency: q.currency || "USD" });
          setLoading(false);
        })
        .catch(err => { if (err?.name !== 'AbortError') setLoading(false); });
    }, 400);
    return () => { clearTimeout(timer); ctrl.abort(); };
  }, [upper, presetMatches.length]);

  const allItems = backendSym ? [...presetMatches, backendSym] : presetMatches;

  const select = (sym) => { onChange(sym); setOpen(false); };

  return (
    <div style={{ position: "relative" }}>
      <Input
        value={value}
        onChange={v => { onChange({ code: v.toUpperCase(), market: null, currency: null }); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder={placeholder || "NVDA"}
      />
      {open && (allItems.length > 0 || loading) && (
        <div style={{
          position: "absolute", top: "100%", left: 0, right: 0, zIndex: 200,
          background: "var(--paper)", border: "1px solid var(--line-2)", borderRadius: 8,
          boxShadow: "var(--shadow-md)", marginTop: 2, overflow: "hidden",
        }}>
          {loading && (
            <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--ink-4)" }}>查询中…</div>
          )}
          {allItems.map(s => (
            <div
              key={s.code}
              onMouseDown={e => { e.preventDefault(); select(s); }}
              style={{ padding: "8px 12px", cursor: "pointer", display: "flex", alignItems: "center", gap: 8, fontSize: 13 }}
              onMouseEnter={e => e.currentTarget.style.background = "var(--bg-deep)"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}
            >
              <MarketDot market={s.market}/>
              <span className="mono" style={{ fontWeight: 600, minWidth: 70 }}>{s.code}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{s.name}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const FormRow = ({ label, children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "90px 1fr", alignItems: "center", gap: 8, marginBottom: 12 }}>
    <label style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", textAlign: "right" }}>{label}</label>
    {children}
  </div>
);

const useForm = (initial) => {
  const [form, setForm] = React.useState(initial);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));
  return [form, set, setForm];
};

const AccountModal = ({ onClose, onSaved }) => {
  const [form, set] = useForm({ name: "", currency: "CNY", note: "", cutoff_date: "" });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setErr("账户名不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const saved = await apiCreateAccount({
        name: form.name.trim(), currency: form.currency,
        note: form.note || null,
        cutoff_date: form.cutoff_date.trim() || null,
      });
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };
  return (
    <Modal open={true} onClose={onClose} title="新增账户" width={400}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="账户名称 *"><Input value={form.name} onChange={v => set("name", v)} placeholder="IBKR / 招商证券 / 支付宝基金"/></FormRow>
        <FormRow label="货币">
          <Select value={form.currency} onChange={v => set("currency", v)} options={CURRENCY_OPTIONS}/>
        </FormRow>
        <FormRow label="截止日期">
          <Input value={form.cutoff_date} onChange={v => set("cutoff_date", v)} placeholder="YYYY-MM-DD（忽略此日期前的交易）"/>
        </FormRow>
        <FormRow label="备注"><Input value={form.note} onChange={v => set("note", v)} placeholder="（可选）"/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "创建账户"}</Button>
        </div>
      </form>
    </Modal>
  );
};

const AccountEditModal = ({ account, onClose, onSaved }) => {
  const [form, set] = useForm({
    name: account.name || "",
    currency: account.currency || "CNY",
    note: account.note || "",
    cutoff_date: account.cutoff_date || "",
    balance_account_id: account.balance_account_id ? String(account.balance_account_id) : "",
    balance_sub_account_id: account.balance_sub_account_id ? String(account.balance_sub_account_id) : "",
  });
  // symbol_markets edited as [{code, market}] rows for convenience
  const [smRows, setSmRows] = React.useState(() =>
    Object.entries(account.symbol_markets || {}).map(([code, market]) => ({ code, market }))
  );
  const [balAccounts, setBalAccounts] = React.useState([]);
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    apiGetBalanceAccounts().then(setBalAccounts).catch(() => {});
  }, []);

  const balParents = balAccounts.filter(a => !a.parent_id);
  const balSubs = form.balance_account_id
    ? balAccounts.filter(a => a.parent_id === Number(form.balance_account_id))
    : [];

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setErr("账户名不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const sm = {};
      smRows.forEach(r => { if (r.code.trim()) sm[r.code.trim().toUpperCase()] = r.market; });
      const saved = await apiUpdateAccount(account.id, {
        name: form.name.trim(),
        currency: form.currency,
        note: form.note || null,
        cutoff_date: form.cutoff_date.trim() || null,
        balance_account_id: form.balance_account_id ? Number(form.balance_account_id) : null,
        balance_sub_account_id: form.balance_sub_account_id ? Number(form.balance_sub_account_id) : null,
        symbol_markets: Object.keys(sm).length ? sm : null,
      });
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={`编辑账户 · ${account.name}`} width={420}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="账户名称 *"><Input value={form.name} onChange={v => set("name", v)} placeholder="IBKR"/></FormRow>
        <FormRow label="货币">
          <Select value={form.currency} onChange={v => set("currency", v)} options={CURRENCY_OPTIONS}/>
        </FormRow>
        <FormRow label="截止日期">
          <Input value={form.cutoff_date} onChange={v => set("cutoff_date", v)} placeholder="YYYY-MM-DD"/>
        </FormRow>
        <div style={{ fontSize: 11, color: "var(--ink-4)", margin: "-8px 0 12px 98px", lineHeight: 1.5 }}>
          此日期之前的交易记录只用作 backup，不参与已实现 / XIRR 计算。
        </div>
        <FormRow label="资产负债账户">
          <Select value={form.balance_account_id} onChange={v => { set("balance_account_id", v); set("balance_sub_account_id", ""); }}
            options={[{ value: "", label: "— 不选 —" }, ...balParents.map(a => ({ value: String(a.id), label: a.name }))]}/>
        </FormRow>
        <FormRow label="资产负债子账户">
          <Select value={form.balance_sub_account_id} onChange={v => set("balance_sub_account_id", v)}
            options={[{ value: "", label: "— 不选 —" }, ...balSubs.map(a => ({ value: String(a.id), label: a.name }))]}
            style={{ opacity: balSubs.length === 0 ? 0.5 : 1, pointerEvents: balSubs.length === 0 ? "none" : "auto" }}/>
        </FormRow>
        <FormRow label="备注"><Input value={form.note} onChange={v => set("note", v)} placeholder="（可选）"/></FormRow>

        {/* Symbol market overrides */}
        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>
            市场分类覆盖
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 8, lineHeight: 1.5 }}>
            将指定 symbol 归入特定市场（用于持仓汇总饼图），不影响货币和价格。
          </div>
          {smRows.length > 0 && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 28px", gap: 6, marginBottom: 6 }}>
              {smRows.map((r, i) => (
                <React.Fragment key={i}>
                  <input value={r.code} onChange={e => setSmRows(rows => rows.map((x, j) => j === i ? { ...x, code: e.target.value } : x))}
                    placeholder="symbol（如 013308）"
                    style={{ fontSize: 13, padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)" }}/>
                  <select value={r.market} onChange={e => setSmRows(rows => rows.map((x, j) => j === i ? { ...x, market: e.target.value } : x))}
                    style={{ fontSize: 13, padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)" }}>
                    <option value="US">美股 US</option>
                    <option value="HK">港股 HK</option>
                    <option value="CN">A股 CN</option>
                    <option value="CA">加股 CA</option>
                    <option value="CRYPTO">加密</option>
                  </select>
                  <button type="button" onClick={() => setSmRows(rows => rows.filter((_, j) => j !== i))}
                    style={{ border: "none", background: "none", color: "var(--ink-4)", cursor: "pointer", fontSize: 15, padding: 0 }}>✕</button>
                </React.Fragment>
              ))}
            </div>
          )}
          <button type="button" onClick={() => setSmRows(rows => [...rows, { code: "", market: "HK" }])}
            style={{ fontSize: 12, color: "var(--ink-3)", border: "1px dashed var(--line-2)", borderRadius: 6, background: "none", padding: "4px 10px", cursor: "pointer" }}>
            + 添加映射
          </button>
        </div>

        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
        </div>
      </form>
    </Modal>
  );
};

const AccountSelect = ({ accounts, value, onChange }) => (
  <Select
    value={value || ""}
    onChange={onChange}
    options={[
      { value: "", label: "— 未分配 —" },
      ...accounts.map(a => ({ value: a.name, label: a.name })),
    ]}
  />
);

const CCY_MARKET = { USD: "US", HKD: "HK", CNY: "CN", CAD: "CA" };

const HoldingModal = ({ editing, accounts, defaultAccount, onClose, onSaved }) => {
  const inferMarket = (code) => SYMBOL_INDEX[code]?.market || null;
  const initCode = editing?.code || "";
  const acctCcy = accounts.find(a => a.name === (editing?.account || defaultAccount))?.currency || null;
  const initMarket = editing?.market || inferMarket(initCode) || CCY_MARKET[acctCcy] || "US";
  const today = new Date().toISOString().slice(0, 10);
  const initDate = editing?.as_of_date || today;
  const [isCash, setIsCash] = React.useState(editing?.code === "CASH");
  const [form, set, setForm] = useForm({
    code: initCode,
    market: initMarket,
    currency: editing?.currency || MARKET_CCY[initMarket],
    account: editing?.account || defaultAccount || "",
    as_of_date: initDate,
    shares: editing?.shares ?? "",
    avg_cost: editing?.avg_cost ?? "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const setCode = (sym) => {
    const c = (typeof sym === "string" ? sym : sym.code || "").toUpperCase();
    const market = (typeof sym === "object" && sym.market) || inferMarket(c) || form.market;
    const currency = (typeof sym === "object" && sym.currency) || MARKET_CCY[market];
    setForm(f => ({ ...f, code: c, market, currency }));
  };
  const setMarket = (m) => setForm(f => ({ ...f, market: m, currency: MARKET_CCY[m] }));

  const toggleCash = (cash) => {
    setIsCash(cash);
    if (cash) setForm(f => ({ ...f, code: "CASH", avg_cost: "1" }));
    else setForm(f => ({ ...f, code: "", avg_cost: "" }));
  };

  const setCashCurrency = (ccy) => setForm(f => ({ ...f, currency: ccy, market: CCY_MARKET[ccy] || "US" }));

  const submit = async (e) => {
    e.preventDefault();
    if (isCash) {
      if (!form.shares || parseFloat(form.shares) <= 0) { setErr("金额须大于 0"); return; }
    } else {
      if (!form.code.trim())                            { setErr("代码不能为空"); return; }
      if (!form.shares || parseFloat(form.shares) <= 0) { setErr("持仓股数须大于 0"); return; }
      if (form.avg_cost === "" || parseFloat(form.avg_cost) < 0) { setErr("均价成本不能为空"); return; }
    }
    if (!form.as_of_date.trim()) { setErr("快照日期不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        shares: parseFloat(form.shares),
        avg_cost: isCash ? 1 : parseFloat(form.avg_cost),
        account: form.account || null,
        snapshot_name: form.as_of_date.trim(),
      };
      const saved = editing ? await apiUpdateHolding(editing.id, payload) : await apiCreateHolding(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? "编辑持仓" : "添加持仓"} width={440}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="类型">
          <Tabs variant="pill" value={isCash ? "cash" : "stock"} onChange={v => toggleCash(v === "cash")}
            tabs={[{id:"stock",label:"证券"},{id:"cash",label:"现金"}]}/>
        </FormRow>
        {isCash ? (
          <>
            <FormRow label="货币">
              <Select value={form.currency} onChange={setCashCurrency}
                options={CURRENCY_OPTIONS}/>
            </FormRow>
            <FormRow label="金额 *"><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="10000" suffix={form.currency}/></FormRow>
          </>
        ) : (
          <>
            <FormRow label="代码 *">
              <SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA"/>
              {/^\d{6}$/.test(form.code) && <div style={{fontSize:11,color:"var(--ink-3)",marginTop:3}}>6位纯数字为基金代码；A股股票请加交易所后缀（如 002594.SZ / 600519.SS）</div>}
            </FormRow>
            <FormRow label="市场">
              <Select value={form.market} onChange={setMarket} options={[{value:"US",label:"美股 US"},{value:"HK",label:"港股 HK"},{value:"CN",label:"A股 CN"},{value:"CA",label:"加股 CA"},{value:"CRYPTO",label:"加密货币"}]}/>
            </FormRow>
            <FormRow label="持仓股数 *"><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="100"/></FormRow>
            <FormRow label="均价成本 *"><Input value={form.avg_cost} onChange={v => set("avg_cost", v)} inputMode="decimal" placeholder="120.00" suffix={form.currency}/></FormRow>
          </>
        )}
        <FormRow label="账户"><AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/></FormRow>
        <FormRow label="快照日期 *"><Input value={form.as_of_date} onChange={v => set("as_of_date", v)} placeholder="YYYY-MM-DD"/></FormRow>
        <FormRow label="备注"><Input value={form.note} onChange={v => set("note", v)} placeholder="（可选）"/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
        </div>
      </form>
    </Modal>
  );
};

const TransactionModal = ({ editing, accounts, defaultAccount, onClose, onSaved }) => {
  const today = new Date().toISOString().slice(0, 10);
  const ccyFromCode = (code) => {
    const sym = SYMBOL_INDEX[code.toUpperCase()];
    return sym ? (MARKET_CCY[sym.market] || "USD") : "USD";
  };
  const acctCcy = accounts.find(a => a.name === (editing?.account || defaultAccount))?.currency || null;
  const [form, set] = useForm({
    date: editing?.date || today,
    code: editing?.code || "",
    side: editing?.side || "buy",
    shares: editing?.shares ?? "",
    price: editing?.price ?? "",
    currency: editing?.currency || (editing?.code ? ccyFromCode(editing.code) : null) || acctCcy || "USD",
    account: editing?.account || defaultAccount || "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const setCode = (sym) => {
    const c = (typeof sym === "string" ? sym : sym.code || "").toUpperCase();
    set("code", c);
    set("currency", (typeof sym === "object" && sym.currency) || ccyFromCode(c));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.date.trim())                            { setErr("日期不能为空"); return; }
    if (!form.code.trim())                            { setErr("代码不能为空"); return; }
    if (!form.shares || parseFloat(form.shares) <= 0) { setErr("股数须大于 0"); return; }
    if (form.price === "" || parseFloat(form.price) < 0) { setErr("价格不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        code: form.code.toUpperCase(),
        shares: parseFloat(form.shares),
        price: parseFloat(form.price),
        account: form.account || null,
      };
      const saved = editing ? await apiUpdateTransaction(editing.id, payload) : await apiCreateTransaction(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? "编辑交易记录" : "新增交易记录"} width={440}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="日期 *"><Input value={form.date} onChange={v => set("date", v)} placeholder="YYYY-MM-DD"/></FormRow>
        <FormRow label="代码 *"><SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA"/></FormRow>
        <FormRow label="方向">
          <Select value={form.side} onChange={v => set("side", v)} options={[{value:"buy",label:"买入 Buy"},{value:"sell",label:"卖出 Sell"}]}/>
        </FormRow>
        <FormRow label="股数 *"><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="100"/></FormRow>
        <FormRow label="价格 *"><Input value={form.price} onChange={v => set("price", v)} inputMode="decimal" placeholder="120.00" suffix={form.currency}/></FormRow>
        <FormRow label="账户"><AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/></FormRow>
        <FormRow label="备注"><Input value={form.note} onChange={v => set("note", v)} placeholder="（可选）"/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
        </div>
      </form>
    </Modal>
  );
};

const IncomeModal = ({ editing, accounts, defaultAccount, onClose, onSaved }) => {
  const today = new Date().toISOString().slice(0, 10);
  const ccyFromCode = (code) => {
    const sym = SYMBOL_INDEX[(code || "").toUpperCase()];
    return sym ? (MARKET_CCY[sym.market] || "USD") : "USD";
  };
  const catLabels = { dividend: "分红 Dividend", interest: "利息 Interest", deposit: "转入 Deposit", withdrawal: "转出 Withdrawal" };
  const ccyOptions = CURRENCY_OPTIONS;
  const acctCcy = accounts.find(a => a.name === (editing?.account || defaultAccount))?.currency || null;

  const [form, set] = useForm({
    date: editing?.date || today,
    code: editing?.code || "",
    source: editing?.source || "",
    category: editing?.category || "dividend",
    amount: editing?.amount ?? "",
    currency: editing?.currency || (editing?.code ? ccyFromCode(editing.code) : null) || acctCcy || "USD",
    account: editing?.account || defaultAccount || "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const isTransfer = form.category === "deposit" || form.category === "withdrawal";

  const setCode = (sym) => {
    const c = (typeof sym === "string" ? sym : sym.code || "").toUpperCase();
    set("code", c);
    set("currency", (typeof sym === "object" && sym.currency) || ccyFromCode(c));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.date.trim())                            { setErr("日期不能为空"); return; }
    if (!form.source.trim())                          { setErr("来源不能为空"); return; }
    if (!form.amount || parseFloat(form.amount) <= 0) { setErr("金额须大于 0"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        amount: parseFloat(form.amount),
        code: isTransfer ? null : (form.code || null),
        account: form.account || null,
      };
      const saved = editing ? await apiUpdateIncome(editing.id, payload) : await apiCreateIncome(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? "编辑记录" : "添加收入/转账"} width={440}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="日期 *"><Input value={form.date} onChange={v => set("date", v)} placeholder="YYYY-MM-DD"/></FormRow>
        <FormRow label="类型">
          <Select value={form.category} onChange={v => set("category", v)} options={Object.entries(catLabels).map(([value,label]) => ({value,label}))}/>
        </FormRow>
        <FormRow label="来源 *"><Input value={form.source} onChange={v => set("source", v)} placeholder="NVDA 分红 / IBKR 转入"/></FormRow>
        {!isTransfer && <FormRow label="代码"><SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA（可选）"/></FormRow>}
        <FormRow label="金额 *">
          <div style={{ display: "flex", gap: 8 }}>
            <Input value={form.amount} onChange={v => set("amount", v)} inputMode="decimal" placeholder="320.00"
              suffix={!isTransfer ? form.currency : undefined} style={{ flex: 1 }}/>
            {isTransfer && <Select value={form.currency} onChange={v => set("currency", v)} options={ccyOptions} style={{ width: 90 }}/>}
          </div>
        </FormRow>
        <FormRow label="账户"><AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/></FormRow>
        <FormRow label="备注"><Input value={form.note} onChange={v => set("note", v)} placeholder="（可选）"/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
        </div>
      </form>
    </Modal>
  );
};

// ── Shared ────────────────────────────────────────────────────────────────────

const iconBtn = { width: 24, height: 24, background: "transparent", border: "none", borderRadius: 4, color: "var(--ink-3)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" };

const ComingSoonBanner = ({ module, features }) => (
  <div style={{ marginTop: 22, padding: 18, background: "var(--paper-2)", border: "1px dashed var(--line-2)", borderRadius: 12 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
      <Icon name="spark" size={14} style={{ color: "var(--warn)" }}/>
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)", textTransform: "uppercase", letterSpacing: ".1em" }}>Roadmap · {module}</span>
    </div>
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {features.map(f => <span key={f} style={{ fontSize: 12, padding: "4px 10px", background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 6, color: "var(--ink-3)" }}>{f}</span>)}
    </div>
  </div>
);

window.Holdings = Holdings;
window.ComingSoonBanner = ComingSoonBanner;
