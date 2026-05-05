/* Module 02 — Holdings: positions + transactions + income, per-account */

const ccySymbol = (ccy) => ccy === "USD" ? "$" : ccy === "HKD" ? "HK$" : "¥";

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
  return holdings.map(h => {
    const dbPrice = prices[h.code] || {};
    const symFallback = SYMBOL_INDEX[h.code] || {};
    const sym = {
      price: dbPrice.price ?? symFallback.price ?? 0,
      prevClose: dbPrice.prev_close ?? symFallback.prevClose ?? 0,
      name: symFallback.name || h.name || h.code,
    };
    const currency = h.currency || "USD";
    const fx = FX[currency] || 1;
    const cutoff = h.as_of_date || null;
    const relevantTxns = sorted.filter(t => t.code === h.code && (!cutoff || t.date > cutoff));

    let dShares = 0, dCost = 0, realized = 0;
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

    const initShares = h.shares || 0;
    const initCost = (h.avg_cost || 0) * initShares;
    const totalShares = initShares + dShares;
    const totalCost = initCost + dCost;
    const avgCost = totalShares > 0 ? totalCost / totalShares : (h.avg_cost || 0);
    const price = sym.price || 0;
    const prevClose = sym.prevClose || 0;
    const value = price * totalShares * fx;
    const cost = avgCost * totalShares * fx;
    const pnl = value - cost;
    const pnlPct = cost ? (pnl / cost) * 100 : 0;
    const dayChange = prevClose ? ((price - prevClose) / prevClose) * 100 : 0;
    const realizedCNY = realized * fx;
    return { ...h, sym, currency, fx, shares: totalShares, avgCost, value, cost, pnl, pnlPct, dayChange, realizedCNY, txnCount: relevantTxns.length };
  });
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
const Holdings = () => {
  const [accounts, setAccounts] = React.useState([]);
  const [selectedAccountId, setSelectedAccountId] = React.useState(null);
  const [tab, setTab] = React.useState("positions");
  const [holdings, setHoldings] = React.useState([]);
  const [transactions, setTransactions] = React.useState([]);
  const [income, setIncome] = React.useState([]);
  const [prices, setPrices] = React.useState({});
  const [loading, setLoading] = React.useState(true);

  const [showHoldingModal, setShowHoldingModal] = React.useState(false);
  const [editingHolding, setEditingHolding] = React.useState(null);
  const [showTxnModal, setShowTxnModal] = React.useState(false);
  const [editingTxn, setEditingTxn] = React.useState(null);
  const [showIncomeModal, setShowIncomeModal] = React.useState(false);
  const [editingIncome, setEditingIncome] = React.useState(null);
  const [showAccountModal, setShowAccountModal] = React.useState(false);
  const [selectedSnapshot, setSelectedSnapshot] = React.useState(null);
  const [summaryCcy, setSummaryCcy] = React.useState("CNY");

  React.useEffect(() => {
    Promise.all([apiGetAccounts(), apiGetHoldings(), apiGetTransactions(), apiGetIncome()])
      .then(([accts, h, t, i]) => {
        setAccounts(accts);
        if (accts.length > 0) setSelectedAccountId(accts[0].id);
        setHoldings(h); setTransactions(t); setIncome(i);
        // Fetch prices for all unique codes across holdings + transactions
        const codes = [...new Set([...h, ...t].map(r => r.code).filter(Boolean))];
        if (codes.length > 0) apiGetPrices(codes).then(setPrices).catch(() => {});
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const selectedAccount = accounts.find(a => a.id === selectedAccountId) || null;
  const acctName = selectedAccount?.name || null;

  // Filter by selected account (null acctName = "全部" view)
  const acctHoldings = acctName ? holdings.filter(h => h.account === acctName) : holdings;
  const acctTxns = acctName ? transactions.filter(t => t.account === acctName) : transactions;
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

  // All-accounts aggregate — one row per (account, code), keeping the latest snapshot date
  const latestHoldings = React.useMemo(() => {
    const best = {};
    holdings.forEach(h => {
      const key = `${h.account || "__none__"}|${h.code}`;
      if (!best[key] || (h.as_of_date || "") > (best[key].as_of_date || "")) best[key] = h;
    });
    return Object.values(best);
  }, [holdings]);
  const allPositions = React.useMemo(() => computePositions(latestHoldings, transactions, prices), [latestHoldings, transactions, prices]);
  const allTotal = allPositions.reduce((s, p) => s + p.value, 0);
  const allCost = allPositions.reduce((s, p) => s + p.cost, 0);
  const allUnrealized = allTotal - allCost;
  const allRealized = transactions
    .filter(t => t.realized != null)
    .reduce((s, t) => s + (t.realized || 0) * (FX[t.currency] || 1), 0);
  const allIncomeTotal = income
    .filter(i => !["deposit","withdrawal"].includes(i.category))
    .reduce((s, i) => s + i.amount * (FX[i.currency] || 1), 0);
  const allDayPnl = allPositions.reduce((s, p) => s + p.value * p.dayChange / 100, 0);
  const allXIRR = React.useMemo(() => computeAccountXIRR(income, allPositions), [income, allPositions]);

  // Per-account view — uses snapshot-filtered holdings
  const acctCcy = selectedAccount?.currency || "CNY";
  const acctFx = FX[acctCcy] || 1; // CNY rate for converting to account native currency
  const acctPositions = React.useMemo(() => computePositions(snapshotHoldings, acctTxns, prices), [snapshotHoldings, acctTxns, prices]);
  // acctTotal/cost/unrealized in account's native currency (divide out CNY FX, apply account FX)
  const acctTotal = acctPositions.reduce((s, p) => s + p.value / acctFx, 0);
  const acctCost = acctPositions.reduce((s, p) => s + p.cost / acctFx, 0);
  const acctUnrealized = acctTotal - acctCost;
  const acctRealized = acctPositions.reduce((s, p) => s + p.realizedCNY / acctFx, 0);
  const acctIncomeTotal = acctIncome
    .filter(i => !["deposit","withdrawal"].includes(i.category))
    .reduce((s, i) => s + i.amount * ((FX[i.currency] || 1) / acctFx), 0);
  const acctDeposits = acctIncome.filter(i => i.category === "deposit")
    .reduce((s, i) => s + i.amount * ((FX[i.currency] || 1) / acctFx), 0);
  const acctXIRR = React.useMemo(() => computeAccountXIRR(acctIncome, acctPositions), [acctIncome, acctPositions]);

  const summaryFx = FX[summaryCcy] || 1;
  const summarySym = ccySymbol(summaryCcy);

  const byMarket = ["US", "HK", "CN"].map(m => {
    const v = allPositions.filter(p => p.market === m).reduce((s, p) => s + p.value, 0);
    return { label: m === "US" ? "美股" : m === "HK" ? "港股" : "A股", value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#C8460F" }[m] };
  });

  const deleteAccount = async (id, name) => {
    if (!confirm(`删除账户「${name}」？\n相关持仓/交易/收入记录不会删除，但将变为未分配状态。`)) return;
    await apiDeleteAccount(id);
    const next = accounts.filter(a => a.id !== id);
    setAccounts(next);
    if (selectedAccountId === id) setSelectedAccountId(next[0]?.id || null);
  };

  if (loading) return <div style={{ padding: 48, textAlign: "center", color: "var(--ink-3)" }}>加载中…</div>;

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 02 · PORTFOLIO"
        title="投资组合"
        subtitle="Portfolio Tracker · 所有账户汇总 + 年化回报率"
        right={null}
      />

      {/* ── All-accounts aggregate ─────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL VALUE · 所有账户</div>
            <div style={{ display: "flex", gap: 3 }}>
              {["CNY","USD"].map(c => (
                <button key={c} onClick={() => setSummaryCcy(c)} style={{ fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 4, border: `1px solid ${summaryCcy===c?"var(--ink)":"var(--line)"}`, background: summaryCcy===c?"var(--ink)":"transparent", color: summaryCcy===c?"var(--paper)":"var(--ink-4)", cursor: "pointer" }}>{c}</button>
              ))}
            </div>
          </div>
          <div className="mono" style={{ fontSize: 34, fontWeight: 700, marginTop: 4 }}>
            {allTotal/summaryFx >= 1e6
              ? <>{summarySym}{((allTotal/summaryFx)/1e6).toFixed(2)}<span style={{ fontSize: 18, color: "var(--ink-3)" }}>M</span></>
              : <>{summarySym}{((allTotal/summaryFx)/1000).toFixed(1)}<span style={{ fontSize: 18, color: "var(--ink-3)" }}>k</span></>
            }
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
            <div><span style={{ fontSize: 11, color: "var(--ink-4)" }}>未实现 </span><ChangeNum value={allCost ? (allUnrealized/allCost)*100 : 0} size="sm"/></div>
            <div><span style={{ fontSize: 11, color: "var(--ink-4)" }}>今日 </span><ChangeNum value={allTotal ? allDayPnl/allTotal*100 : 0} size="sm"/></div>
          </div>
          {allTotal > 0 && (
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
        <StatTile label="UNREALIZED P&L · 未实现盈亏" value={`${allUnrealized >= 0 ? "+" : "−"}${summarySym}${(Math.abs(allUnrealized/summaryFx)/1000).toFixed(1)}k`} tone={allUnrealized >= 0 ? "up" : "down"} sub={`总成本 ${summarySym}${(allCost/summaryFx/1000).toFixed(1)}k（持仓均价 × 股数）`}/>
        <StatTile label="REALIZED + 收入 · 已实现" value={`+${summarySym}${((allRealized+allIncomeTotal)/summaryFx/1000).toFixed(1)}k`} tone="up" sub={`已实现 ${summarySym}${(allRealized/summaryFx/1000).toFixed(1)}k · 收入 ${summarySym}${(allIncomeTotal/summaryFx/1000).toFixed(1)}k`}/>
        {allXIRR != null
          ? <StatTile label="年化回报率 (MWRR)" value={`${allXIRR >= 0 ? "+" : ""}${allXIRR.toFixed(1)}%`} tone={allXIRR >= 0 ? "up" : "down"} sub="所有账户 · 基于转入记录计算"/>
          : <StatTile label="年化回报率 (MWRR)" value="—" tone="neutral" sub="添加转入记录后可计算"/>
        }
      </div>

      {/* ── Account switcher ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "var(--ink-4)", marginRight: 4 }}>账户</span>
        {accounts.map(a => (
          <div key={a.id} style={{ display: "inline-flex", alignItems: "center", gap: 0 }}>
            <button
              onClick={() => setSelectedAccountId(a.id)}
              style={{
                padding: "5px 14px", borderRadius: accounts.length > 0 ? "20px 0 0 20px" : 20,
                border: `1px solid ${selectedAccountId === a.id ? "var(--ink)" : "var(--line)"}`,
                borderRight: "none",
                background: selectedAccountId === a.id ? "var(--ink)" : "var(--paper)",
                color: selectedAccountId === a.id ? "var(--paper)" : "var(--ink-2)",
                cursor: "pointer", fontSize: 13, fontWeight: selectedAccountId === a.id ? 600 : 400,
                transition: "all .15s",
              }}
            >{a.name}</button>
            <button
              onClick={() => deleteAccount(a.id, a.name)}
              title={`删除账户 ${a.name}`}
              style={{
                padding: "5px 8px", borderRadius: "0 20px 20px 0",
                border: `1px solid ${selectedAccountId === a.id ? "var(--ink)" : "var(--line)"}`,
                background: selectedAccountId === a.id ? "var(--ink)" : "var(--paper)",
                color: selectedAccountId === a.id ? "rgba(255,255,255,0.5)" : "var(--ink-4)",
                cursor: "pointer", fontSize: 11, lineHeight: 1,
                transition: "all .15s",
              }}
            >✕</button>
          </div>
        ))}
        <button
          onClick={() => setShowAccountModal(true)}
          style={{ padding: "5px 14px", borderRadius: 20, border: "1px dashed var(--line-2)", background: "transparent", color: "var(--ink-3)", cursor: "pointer", fontSize: 13 }}
        >+ 新增账户</button>
        {accounts.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--ink-4)", fontStyle: "italic" }}>暂无账户 — 点击「+ 新增账户」开始</span>
        )}
      </div>

      {/* ── Per-account stats strip ───────────────────────────────────────── */}
      {selectedAccount && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 10, marginBottom: 16, padding: "14px 18px", background: "var(--paper-2)", borderRadius: 10, border: "1px solid var(--line)" }}>
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em" }}>{selectedAccount.name} · 市值</div>
            <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 3 }}>{ccySymbol(acctCcy)}{(acctTotal/1000).toFixed(1)}k</div>
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>{acctCcy}</div>
          </div>
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em" }}>已转入</div>
            <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 3, color: "var(--ink-2)" }}>{ccySymbol(acctCcy)}{(acctDeposits/1000).toFixed(1)}k</div>
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>记录转入合计</div>
          </div>
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em" }}>未实现 P&L</div>
            <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 3, color: acctUnrealized >= 0 ? "var(--up)" : "var(--down)" }}>
              {acctUnrealized >= 0 ? "+" : "−"}{ccySymbol(acctCcy)}{(Math.abs(acctUnrealized)/1000).toFixed(1)}k
            </div>
          </div>
          <div>
            <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em" }}>
              年化回报率 {acctXIRR != null ? "(MWRR)" : "(CAGR 估算)"}
            </div>
            {acctXIRR != null ? (
              <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 3, color: acctXIRR >= 0 ? "var(--up)" : "var(--down)" }}>
                {acctXIRR >= 0 ? "+" : ""}{acctXIRR.toFixed(1)}%
              </div>
            ) : (
              <div>
                <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 3, color: "var(--ink-4)" }}>—</div>
                <div style={{ fontSize: 11, color: "var(--ink-4)" }}>添加转入记录后可计算</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Inner tabs ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <Tabs variant="underline" value={tab} onChange={setTab} tabs={[
          { id: "positions",    label: "持仓 Positions",     count: acctPositions.length },
          { id: "transactions", label: "交易记录 Trades",    count: acctTxns.length },
          { id: "income",       label: "收入/转账 Income",   count: acctIncome.length },
          { id: "rebalance",    label: "再平衡 Rebalance",   icon: "spark" },
        ]}/>
      </div>

      {tab === "positions"    && <PositionsTable positions={acctPositions} total={acctTotal} acctCcy={acctCcy} acctFx={acctFx}
          snapshots={snapshots} selectedSnapshot={selectedSnapshot} onSnapshotChange={setSelectedSnapshot}
          onAddHolding={() => { setEditingHolding(null); setShowHoldingModal(true); }}
          onEditHolding={h => { setEditingHolding(h); setShowHoldingModal(true); }}
          onDeleteHolding={id => apiDeleteHolding(id).then(() => setHoldings(p => p.filter(h => h.id !== id))).catch(console.error)}
        />}
      {tab === "transactions" && <TransactionsTable txns={acctTxns}
          onAdd={() => { setEditingTxn(null); setShowTxnModal(true); }}
          onEdit={t => { setEditingTxn(t); setShowTxnModal(true); }}
          onDelete={id => apiDeleteTransaction(id).then(() => setTransactions(p => p.filter(t => t.id !== id))).catch(console.error)}
          onImportDone={txns => setTransactions(txns)}
        />}
      {tab === "income"       && <IncomeTable items={acctIncome} total={acctIncomeTotal} acctCcy={acctCcy} acctFx={acctFx}
          onAdd={() => { setEditingIncome(null); setShowIncomeModal(true); }}
          onEdit={i => { setEditingIncome(i); setShowIncomeModal(true); }}
          onDelete={id => apiDeleteIncome(id).then(() => setIncome(p => p.filter(i => i.id !== id))).catch(console.error)}
        />}
      {tab === "rebalance"    && <RebalancePanel positions={acctPositions} total={acctTotal}/>}

      {showHoldingModal && <HoldingModal editing={editingHolding} accounts={accounts} defaultAccount={acctName} onClose={() => setShowHoldingModal(false)}
          onSaved={h => { setHoldings(prev => editingHolding ? prev.map(x => x.id === h.id ? h : x) : [...prev, h]); setShowHoldingModal(false); }}/>}
      {showTxnModal && <TransactionModal editing={editingTxn} accounts={accounts} defaultAccount={acctName} onClose={() => setShowTxnModal(false)}
          onSaved={t => { setTransactions(prev => editingTxn ? prev.map(x => x.id === t.id ? t : x) : [t, ...prev]); setShowTxnModal(false); }}/>}
      {showIncomeModal && <IncomeModal editing={editingIncome} accounts={accounts} defaultAccount={acctName} onClose={() => setShowIncomeModal(false)}
          onSaved={i => { setIncome(prev => editingIncome ? prev.map(x => x.id === i.id ? i : x) : [i, ...prev]); setShowIncomeModal(false); }}/>}
      {showAccountModal && <AccountModal onClose={() => setShowAccountModal(false)}
          onSaved={a => { setAccounts(prev => [...prev, a]); setSelectedAccountId(a.id); setShowAccountModal(false); }}/>}

      <ComingSoonBanner module="Holdings" features={["批量分配账户", "Auto-import 券商 CSV", "Tax-loss harvesting hints", "Dividend calendar"]} />
    </div>
  );
};

// ── Shared stat tile ──────────────────────────────────────────────────────────
const StatTile = ({ label, value, sub, tone }) => (
  <Card padding={20}>
    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{label}</div>
    <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--ink)" }}>{value}</div>
    <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{sub}</div>
  </Card>
);

// ── Positions table ───────────────────────────────────────────────────────────
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
          {[...positions].sort((a,b) => b.value - a.value).map((p, i, arr) => (
            <div key={p.id} style={{ display: "grid", gridTemplateColumns: "24px 1fr 70px 95px 90px 80px 100px 110px 56px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < arr.length-1 ? "1px solid var(--line)" : "none" }}>
              <MarketDot market={p.market}/>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>{p.code}</span>
                  <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{p.sym.name || p.name || ""}</span>
                  {p.txnCount > 0 && <span style={{ fontSize: 10, color: "var(--ink-4)", padding: "1px 6px", border: "1px solid var(--line)", borderRadius: 4 }}>{p.txnCount} 笔</span>}
                </div>
              </div>
              <span className="mono" style={{textAlign:"right",fontSize:12}}>{p.shares > 0 ? p.shares : "—"}</span>
              <span className="mono" style={{textAlign:"right",fontSize:12,color:"var(--ink-3)"}}>{fmtMoney(p.avgCost, p.currency, 2)}</span>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}>{p.sym.price ? fmtMoney(p.sym.price, p.currency, 2) : "—"}</span>
              <span style={{textAlign:"right"}}><ChangeNum value={p.dayChange} size="sm"/></span>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}>{sym}{fmtNum(p.value / acctFx, 0)}</span>
              <div style={{textAlign:"right"}}>
                <ChangeNum value={p.pnlPct} size="sm"/>
                <div className="mono" style={{ fontSize: 10.5, color: p.pnl >= 0 ? "var(--up)" : "var(--down)", marginTop: 1 }}>
                  {p.pnl >= 0 ? "+" : "−"}{sym}{fmtNum(Math.abs(p.pnl / acctFx), 0)}
                </div>
              </div>
              <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                <button style={iconBtn} title="编辑" onClick={() => onEditHolding(p)}><Icon name="edit" size={13}/></button>
                <button style={{ ...iconBtn, color: "var(--up)" }} title="删除" onClick={() => { if (confirm(`删除 ${p.code} 持仓？`)) onDeleteHolding(p.id); }}><Icon name="x" size={13}/></button>
              </div>
            </div>
          ))}
        </>
      )}
  </Card>;
};

// ── Transactions table ────────────────────────────────────────────────────────
const TransactionsTable = ({ txns, onAdd, onEdit, onDelete, onImportDone }) => {
  const sorted = [...txns].sort((a,b) => b.date.localeCompare(a.date));
  const fileRef = React.useRef(null);
  const [importMsg, setImportMsg] = React.useState(null);

  const handleImport = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    e.target.value = "";
    try {
      const result = await apiImportTransactions(file);
      const all = await apiGetTransactions();
      onImportDone(all);
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
          <input ref={fileRef} type="file" accept=".csv" style={{ display: "none" }} onChange={handleImport}/>
          <Button size="sm" variant="secondary" onClick={() => fileRef.current.click()}>导入 CSV</Button>
          <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>新增记录</Button>
        </div>
      </div>
      {sorted.length === 0
        ? <Empty icon="book" title="暂无交易记录" hint="点击「新增记录」手动添加，或「导入 CSV」批量导入 Notion 数据"/>
        : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "100px 80px 90px 80px 100px 110px 130px 1fr 52px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
              <span>DATE</span><span>TYPE</span><span>SYMBOL</span>
              <span style={{textAlign:"right"}}>SHARES</span><span style={{textAlign:"right"}}>PRICE</span>
              <span style={{textAlign:"right"}}>AMOUNT</span><span style={{textAlign:"right"}}>REALIZED</span>
              <span style={{paddingLeft:24}}>NOTE</span><span/>
            </div>
            {sorted.map((t, i) => {
              const amt = t.shares * t.price;
              return (
                <div key={t.id} style={{ display: "grid", gridTemplateColumns: "100px 80px 90px 80px 100px 110px 130px 1fr 52px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < sorted.length-1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
                  <span className="mono" style={{color:"var(--ink-3)"}}>{t.date}</span>
                  <Badge tone={t.side === "buy" ? "up" : "down"} solid={false} size="sm">{t.side === "buy" ? "买入" : "卖出"}</Badge>
                  <span className="mono" style={{fontWeight:600}}>{t.code}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.shares > 0 ? t.shares : "—"}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.price > 0 ? fmtMoney(t.price, t.currency, 2) : "—"}</span>
                  <span className="mono" style={{textAlign:"right",fontWeight:600}}>{amt > 0 ? fmtMoney(amt, t.currency, 0) : "—"}</span>
                  <span className="mono" style={{textAlign:"right",color:t.realized>=0?"var(--up)":t.realized!=null?"var(--down)":"var(--ink-4)",fontWeight:600}}>
                    {t.realized != null ? (t.realized >= 0 ? "+" : "−") + fmtMoney(Math.abs(t.realized), t.currency, 0) : "—"}
                  </span>
                  <span style={{color:"var(--ink-3)",fontSize:12,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",paddingLeft:24}}>{t.note || ""}</span>
                  <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                    <button style={iconBtn} title="编辑" onClick={() => onEdit(t)}><Icon name="edit" size={13}/></button>
                    <button style={{ ...iconBtn, color: "var(--up)" }} title="删除" onClick={() => { if (confirm(`删除此交易记录？`)) onDelete(t.id); }}><Icon name="x" size={13}/></button>
                  </div>
                </div>
              );
            })}
          </>
        )}
    </Card>
  );
};

// ── Income / Transfer table ───────────────────────────────────────────────────
const IncomeTable = ({ items, total, acctCcy = "CNY", acctFx = 1, onAdd, onEdit, onDelete }) => {
  const sorted = [...items].sort((a,b) => b.date.localeCompare(a.date));
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
          <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>添加记录</Button>
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

// ── Rebalance panel (unchanged) ───────────────────────────────────────────────
const RebalancePanel = ({ positions, total }) => {
  const targets = {
    "美股科技 US Tech":  { pct: 50, current: 0, color: "#1F4FE0", codes: ["NVDA","GOOGL","AAPL","TSM"] },
    "宽基 ETF":         { pct: 20, current: 0, color: "#5C8AE6", codes: ["QQQ"] },
    "港股 HK":          { pct: 15, current: 0, color: "#B8447B", codes: ["0700.HK"] },
    "A 股":             { pct: 10, current: 0, color: "#C8460F", codes: ["600519.SS"] },
    "现金 / 黄金":       { pct: 5,  current: 0, color: "#5C6270", codes: [] },
  };
  positions.forEach(p => {
    Object.values(targets).forEach(t => {
      if (t.codes.includes(p.code)) t.current += p.value;
    });
  });
  const allocated = Object.values(targets).reduce((s, t) => s + t.current, 0);
  targets["现金 / 黄金"].current = total - allocated + targets["现金 / 黄金"].current;

  return (
    <Card padding={20}>
      <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 18 }}>
        <div>
          <div style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "3px 10px", background: "var(--warn-soft)", color: "#7A4D0E", borderRadius: 999, fontSize: 11, fontWeight: 600, marginBottom: 8 }}>
            <Icon name="spark" size={12}/> ROADMAP · COMING SOON
          </div>
          <div className="serif-cn" style={{ fontSize: 19, fontWeight: 700 }}>年度再平衡通知</div>
          <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>定义目标比例 · 阈值偏离 ≥ 5pp 自动邮件提醒 · 一键生成调仓清单</div>
        </div>
        <Button variant="secondary" icon="settings">编辑目标比例</Button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 24 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>偏离度 Drift vs Target</div>
          {Object.entries(targets).map(([label, t]) => {
            const curPct = total ? (t.current / total) * 100 : 0;
            const drift = curPct - t.pct;
            const deltaCny = (t.pct/100 * total) - t.current;
            return (
              <div key={label} style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <span style={{ width: 8, height: 8, background: t.color, borderRadius: 2 }}/>{label}
                  </span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{curPct.toFixed(1)}% / {t.pct}%</span>
                </div>
                <div style={{ position: "relative", height: 8, background: "var(--bg-deep)", borderRadius: 4 }}>
                  <div style={{ position: "absolute", left: 0, top: 0, width: `${Math.min(curPct,100)}%`, height: "100%", background: t.color, borderRadius: 4, opacity: .5 }}/>
                  <div style={{ position: "absolute", left: `${t.pct}%`, top: -3, width: 2, height: 14, background: "var(--ink)" }}/>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 11 }}>
                  <span style={{ color: Math.abs(drift) >= 5 ? "var(--up)" : "var(--ink-4)", fontWeight: Math.abs(drift) >= 5 ? 600 : 400 }} className="mono">
                    drift {drift >= 0 ? "+" : ""}{drift.toFixed(1)}pp {Math.abs(drift) >= 5 ? "⚠" : ""}
                  </span>
                  <span className="mono" style={{ color: "var(--ink-4)" }}>建议 {deltaCny >= 0 ? "买入" : "卖出"} ¥{fmtNum(Math.abs(deltaCny)/1000, 1)}k</span>
                </div>
              </div>
            );
          })}
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>提醒规则 Rules</div>
          {[
            { label: "年度自动提醒", desc: "每年 1 月 1 日发送一次", on: true },
            { label: "偏离 ≥ 5pp 触发", desc: "任一桶超过 5 个百分点", on: true },
            { label: "现金 ≥ 10% 提醒投入", desc: "未投资现金堆积时", on: false },
            { label: "新仓位 5 日提醒", desc: "买入后 5 个工作日检查", on: false },
          ].map((r, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "12px 0", borderBottom: i < 3 ? "1px dashed var(--line)" : "none" }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 500 }}>{r.label}</div>
                <div style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 2 }}>{r.desc}</div>
              </div>
              <Toggle value={r.on} onChange={()=>{}}/>
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
};

// ── CRUD Modals ───────────────────────────────────────────────────────────────

const MARKET_CCY = { US: "USD", HK: "HKD", CN: "CNY" };

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
  const [form, set] = useForm({ name: "", currency: "CNY", note: "" });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setErr("账户名不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const saved = await apiCreateAccount({ name: form.name.trim(), currency: form.currency, note: form.note || null });
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };
  return (
    <Modal open={true} onClose={onClose} title="新增账户" width={380}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="账户名称 *"><Input value={form.name} onChange={v => set("name", v)} placeholder="IBKR / 招商证券 / 支付宝基金"/></FormRow>
        <FormRow label="货币">
          <Select value={form.currency} onChange={v => set("currency", v)} options={[{value:"CNY",label:"人民币 CNY"},{value:"USD",label:"美元 USD"},{value:"HKD",label:"港元 HKD"}]}/>
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

const HoldingModal = ({ editing, accounts, defaultAccount, onClose, onSaved }) => {
  const inferMarket = (code) => SYMBOL_INDEX[code]?.market || null;
  const initCode = editing?.code || "";
  const initMarket = editing?.market || inferMarket(initCode) || "US";
  const today = new Date().toISOString().slice(0, 10);
  const initDate = editing?.as_of_date || today;
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

  const setCode = (v) => {
    const c = v.toUpperCase();
    const market = inferMarket(c) || form.market;
    setForm(f => ({ ...f, code: c, market, currency: MARKET_CCY[market] }));
  };
  const setMarket = (m) => setForm(f => ({ ...f, market: m, currency: MARKET_CCY[m] }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.code.trim())                            { setErr("代码不能为空"); return; }
    if (!form.shares || parseFloat(form.shares) <= 0) { setErr("持仓股数须大于 0"); return; }
    if (form.avg_cost === "" || parseFloat(form.avg_cost) < 0) { setErr("均价成本不能为空"); return; }
    if (!form.as_of_date.trim())                      { setErr("快照日期不能为空"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        shares: parseFloat(form.shares),
        avg_cost: parseFloat(form.avg_cost),
        account: form.account || null,
        snapshot_name: form.as_of_date.trim(), // snapshot_name = as_of_date always
      };
      const saved = editing ? await apiUpdateHolding(editing.id, payload) : await apiCreateHolding(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? "编辑持仓" : "添加持仓"} width={440}>
      <form onSubmit={submit} style={{ padding: "18px 20px" }}>
        <FormRow label="代码 *"><Input value={form.code} onChange={setCode} placeholder="NVDA"/></FormRow>
        <FormRow label="市场">
          <Select value={form.market} onChange={setMarket} options={[{value:"US",label:"美股 US"},{value:"HK",label:"港股 HK"},{value:"CN",label:"A股 CN"}]}/>
        </FormRow>
        <FormRow label="账户"><AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/></FormRow>
        <FormRow label="快照日期 *"><Input value={form.as_of_date} onChange={v => set("as_of_date", v)} placeholder="YYYY-MM-DD"/></FormRow>
        <FormRow label="持仓股数 *"><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="100"/></FormRow>
        <FormRow label="均价成本 *"><Input value={form.avg_cost} onChange={v => set("avg_cost", v)} inputMode="decimal" placeholder="120.00" suffix={form.currency}/></FormRow>
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
  const [form, set] = useForm({
    date: editing?.date || today,
    code: editing?.code || "",
    side: editing?.side || "buy",
    shares: editing?.shares ?? "",
    price: editing?.price ?? "",
    currency: editing?.currency || ccyFromCode(editing?.code || ""),
    account: editing?.account || defaultAccount || "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const setCode = (v) => { const c = v.toUpperCase(); set("code", c); set("currency", ccyFromCode(c)); };

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
        <FormRow label="代码 *"><Input value={form.code} onChange={setCode} placeholder="NVDA"/></FormRow>
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
  const catLabels = { dividend: "分红 Dividend", interest: "利息 Interest", option: "期权 Option", deposit: "转入 Deposit", withdrawal: "转出 Withdrawal" };
  const [form, set] = useForm({
    date: editing?.date || today,
    code: editing?.code || "",
    source: editing?.source || "",
    category: editing?.category || "dividend",
    amount: editing?.amount ?? "",
    currency: editing?.currency || ccyFromCode(editing?.code || ""),
    account: editing?.account || defaultAccount || "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const setCode = (v) => { const c = v.toUpperCase(); set("code", c); set("currency", ccyFromCode(c)); };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.date.trim())                           { setErr("日期不能为空"); return; }
    if (!form.source.trim())                         { setErr("来源不能为空"); return; }
    if (!form.amount || parseFloat(form.amount) <= 0) { setErr("金额须大于 0"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        amount: parseFloat(form.amount),
        code: form.code || null,
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
        <FormRow label="代码"><Input value={form.code} onChange={setCode} placeholder="NVDA（可选）"/></FormRow>
        <FormRow label="金额 *"><Input value={form.amount} onChange={v => set("amount", v)} inputMode="decimal" placeholder="320.00" suffix={form.currency}/></FormRow>
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
