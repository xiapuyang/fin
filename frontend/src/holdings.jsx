/* Module 02 — Holdings: positions + transactions + income, per-account */

const ccySymbol = (ccy) => CURRENCY_SYMBOL[ccy] || "¥";
// Mask digits in a precomputed string when global privacy is on. Used for
// prop strings (e.g. StatTile.value) that JSX wrapping can't reach.
const maskDigits = (s) => PRIVACY.masked ? String(s).replace(/\d/g, "•") : s;

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
const computePositions = (holdings, transactions, prices = {}, accounts = []) => {
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
             account: ref.account, currency: ref.currency || "USD",
             market: SYMBOL_INDEX[code]?.market || null };
  });
  const allHoldings = virtualHoldings.length ? [...holdings, ...virtualHoldings] : holdings;

  // Per-account cash analysis for auto-FX deduction (IBKR-style).
  // A cross-currency trade is attributed to ONE cash position to avoid double-counting:
  // prefer cash matching the account's base currency; otherwise the alphabetically
  // first cash currency in the account. Conversion goes through CNY pivot via FX.
  const accountBaseCcy = {};
  accounts.forEach(a => { if (a.currency) accountBaseCcy[a.name] = a.currency; });
  const cashByAccount = {};
  allHoldings.filter(h => h.code === "CASH").forEach(h => {
    if (!cashByAccount[h.account]) cashByAccount[h.account] = new Set();
    cashByAccount[h.account].add(h.currency);
  });
  const crossCurrencySink = (account) => {
    const present = cashByAccount[account];
    if (!present || present.size === 0) return null;
    const base = accountBaseCcy[account];
    if (base && present.has(base)) return base;
    return [...present].sort()[0];
  };

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
    const cutoff = h.snapshot_name || null;
    const isCash = h.code === "CASH";

    let dShares = 0, dCost = 0, realized = 0;
    const relevantTxns = isCash ? [] : sorted.filter(t => t.code === h.code && (!cutoff || t.date > cutoff));
    if (isCash) {
      // Same-currency trades hit this cash directly. Cross-currency trades hit it only
      // if no matching-currency cash exists in the account AND this cash is the chosen
      // FX sink — converted via the CNY pivot to avoid double-deducting from siblings.
      const sink = crossCurrencySink(h.account);
      const cashPresent = cashByAccount[h.account] || new Set();
      sorted
        .filter(t => t.account === h.account && (!cutoff || t.date > cutoff))
        .forEach(t => {
          const sameCcy = t.currency === h.currency;
          const handlesCross = !cashPresent.has(t.currency) && h.currency === sink;
          if (!sameCcy && !handlesCross) return;
          let amt = t.shares * t.price;
          if (!sameCcy) amt = amt * (FX[t.currency] || 1) / (FX[h.currency] || 1);
          if (t.side === "buy") dShares -= amt;
          else                  dShares += amt;
        });
    } else {
      const snapShares = h.shares || 0;
      const snapCost = (h.avg_cost || 0) * snapShares;
      relevantTxns.forEach(t => {
        if (t.side === "buy") {
          dCost += t.shares * t.price;
          dShares += t.shares;
        } else {
          // Weighted average over snapshot lot + post-snapshot buys at the time of the sell
          const liveShares = snapShares + dShares;
          const liveCost = snapCost + dCost;
          const avg = liveShares > 0 ? liveCost / liveShares : (h.avg_cost || 0);
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
    // Cash carries no unrealized P&L. Cross-currency trades reduce dShares without
    // a matching dCost adjustment, which would otherwise leave a phantom loss on
    // the funding cash position.
    const cost = isCash ? value : avgCost * totalShares * fx;
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
    if (i.category !== "deposit" && i.category !== "withdrawal") return;
    const amt = i.amount * (FX[i.currency] || 1);
    cfs.push({ date: i.date, amount: i.category === "deposit" ? -amt : amt });
  });
  const terminalValue = positions.reduce((s, p) => s + p.value, 0);
  if (terminalValue > 0) cfs.push({ date: today, amount: terminalValue });
  cfs.sort((a, b) => a.date.localeCompare(b.date));
  return xirr(cfs);
};

// ── Holdings root component ───────────────────────────────────────────────────
const Holdings = ({ currency = "CNY", birthDate = "" }) => {
  usePrivacyMasked(); // re-render whole module on privacy toggle so totals refresh
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
  const [incomeDefaultCat, setIncomeDefaultCat] = React.useState("dividend");
  const [incomeAllowedCats, setIncomeAllowedCats] = React.useState(null);
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
      })
      .catch(err => { console.error(err); setLoading(false); setPricesReady(true); });
  }, []);

  // Price polling — fetch on initial load and every 60s while page is open.
  // Re-runs when the symbol set changes. Includes only codes with positive net
  // shares: snapshot shares + post-snapshot transactions per (account, code).
  // Excludes fully-exited tickers regardless of whether they're in holdings or
  // only in transactions.
  const codesKey = (() => {
    const net = {};
    const cutoff = {};
    holdings.forEach(h => {
      if (!h.code || h.code === "CASH") return;
      const key = `${h.account}|${h.code}`;
      net[key] = (net[key] || 0) + (h.shares || 0);
      if (h.snapshot_name && (!cutoff[key] || h.snapshot_name > cutoff[key])) cutoff[key] = h.snapshot_name;
    });
    transactions.forEach(t => {
      if (!t.code || t.code === "CASH") return;
      const key = `${t.account}|${t.code}`;
      if (cutoff[key] && t.date <= cutoff[key]) return;
      net[key] = (net[key] || 0) + (t.side === "buy" ? (t.shares || 0) : -(t.shares || 0));
    });
    const codes = new Set();
    Object.entries(net).forEach(([key, n]) => { if (n > 0) codes.add(key.split("|")[1]); });
    return [...codes].sort().join(",");
  })();
  React.useEffect(() => {
    if (loading) return;
    if (!codesKey) { setPricesReady(true); return; }
    const codes = codesKey.split(",");
    let cancelled = false;
    const fetchPrices = () => apiGetPrices(codes)
      .then(p => { if (!cancelled) { setPrices(p); setPricesReady(true); } })
      .catch(() => { if (!cancelled) setPricesReady(true); });
    fetchPrices();
    const timer = setInterval(fetchPrices, 60_000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [loading, codesKey]);

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

  // Snapshots available for this account (null/empty → shown as "Unnamed")
  const snapshots = React.useMemo(() => {
    const names = [...new Set(acctHoldings.map(h => h.snapshot_name || "Unnamed"))].sort();
    return names;
  }, [acctHoldings]);

  // Auto-select the latest snapshot when account changes or snapshots load
  React.useEffect(() => {
    if (snapshots.length > 0) setSelectedSnapshot(snapshots[snapshots.length - 1]);
    else setSelectedSnapshot(null);
  }, [acctName, snapshots.join(",")]);

  // Reset tab to "positions" when on benchmark tab but benchmark is not enabled
  // (covers both account switching and disabling benchmark on the current account)
  React.useEffect(() => {
    const acct = accounts.find(a => a.id === selectedAccountId);
    if (tab === "benchmark" && acct && !acct.benchmark_enabled) {
      setTab("positions");
    }
  }, [selectedAccountId, selectedAccount?.benchmark_enabled]);

  // Holdings filtered to selected snapshot only (prevents double-counting)
  // null/empty snapshot_name treated as "Unnamed"
  const snapshotHoldings = selectedSnapshot
    ? acctHoldings.filter(h => (h.snapshot_name || "Unnamed") === selectedSnapshot)
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
      if (!best[key] || (h.snapshot_name || "") > (best[key].snapshot_name || "")) best[key] = h;
    });
    return Object.values(best);
  }, [holdings]);
  // Apply per-account cutoffs so the aggregate is consistent with per-account P&L
  const txnsForAllCalc = React.useMemo(() =>
    transactions.filter(t => !accountCutoffs[t.account] || t.date >= accountCutoffs[t.account]),
    [transactions, accountCutoffs]
  );
  const allPositions = React.useMemo(() => computePositions(latestHoldings, txnsForAllCalc, prices, accounts), [latestHoldings, txnsForAllCalc, prices, accounts]);
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
  const acctPositions = React.useMemo(() => computePositions(snapshotHoldings, acctTxnsForCalc, prices, accounts), [snapshotHoldings, acctTxnsForCalc, prices, accounts]);
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
      return { label: { US: I18N.t("base.market.us"), HK: I18N.t("base.market.hk"), CN: I18N.t("base.market.cn"), CA: I18N.t("base.market.ca"), CRYPTO: I18N.t("base.market.crypto") }[m] || m, value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#16A34A", CA: "#C8531C", CRYPTO: "#F7931A" }[m] };
    }),
    { label: I18N.t("holdings.bond"), value: allPositions.filter(isBond).reduce((s, p) => s + p.value, 0), color: "#7C3AED" },
    { label: I18N.t("holdings.other"), value: allPositions.filter(p => !knownMarkets.includes(effectiveMarket(p)) && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value, 0), color: "#aaa" },
    { label: I18N.t("holdings.cash"), value: allCashValue, color: "#888" },
  ].filter(b => b.value > 0);

  const acctCashValue = acctPositions.filter(p => p.code === "CASH").reduce((s, p) => s + p.value / acctFx, 0);
  const acctMarketValue = acctTotal - acctCashValue;
  const acctDayPnl = acctPositions.reduce((s, p) => s + p.value / acctFx * p.dayChange / 100, 0);
  const acctByMarket = [
    ...knownMarkets.map(m => {
      const v = acctPositions.filter(p => effectiveMarket(p) === m && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value / acctFx, 0);
      return { label: { US: I18N.t("base.market.us"), HK: I18N.t("base.market.hk"), CN: I18N.t("base.market.cn"), CA: I18N.t("base.market.ca"), CRYPTO: I18N.t("base.market.crypto") }[m] || m, value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#16A34A", CA: "#C8531C", CRYPTO: "#F7931A" }[m] };
    }),
    { label: I18N.t("holdings.bond"), value: acctPositions.filter(isBond).reduce((s, p) => s + p.value / acctFx, 0), color: "#7C3AED" },
    { label: I18N.t("holdings.other"), value: acctPositions.filter(p => !knownMarkets.includes(effectiveMarket(p)) && p.code !== "CASH" && !isBond(p)).reduce((s, p) => s + p.value / acctFx, 0), color: "#aaa" },
    { label: I18N.t("holdings.cash"), value: acctCashValue, color: "#888" },
  ].filter(b => b.value > 0);

  const deleteAccount = async (id, name) => {
    if (!confirm(I18N.tf("holdings.accounts.deleteConfirm", { name }))) return;
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
        title={I18N.t("holdings.title")}
        subtitle={I18N.t("holdings.subtitle")}
        right={
          <div style={{ display: "flex", border: "1px solid var(--line-2)", borderRadius: 8, overflow: "hidden" }}>
            {[["portfolio",I18N.t("holdings.tab.portfolio")],["rebalance",I18N.t("holdings.tab.rebalance")]].map(([id, label]) => (
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
        const allPos = computePositions(holdings, transactions, prices, accounts);
        const allCNY = allPos.reduce((s, p) => s + p.value, 0);
        return <RebalancePanel positions={allPos} total={allCNY} currency={currency} birthDate={birthDate}/>;
      })()}
      {viewMode === "portfolio" && (<>

      {/* ── All-accounts aggregate ─────────────────────────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{I18N.t("holdings.stat.total")}</div>
          <div className="mono" style={{ fontSize: 34, fontWeight: 700, marginTop: 4 }}>
            {pricesReady ? <Private>{summarySym}{fmtNum(allTotal/summaryFx, 0)}</Private> : "—"}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
            <div>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Mkt </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? <Private>{summarySym}{fmtNum(allMarketValue/summaryFx, 2)}</Private> : "—"}</span>
            </div>
            <div>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Cash </span>
              <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? <Private>{summarySym}{fmtNum(allCashValue/summaryFx, 2)}</Private> : "—"}</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{I18N.t("holdings.stat.today")} </span>
              {pricesReady
                ? <><ChangeNum value={allTotal ? allDayPnl/allTotal*100 : 0} size="sm"/>
                    {allDayPnl !== 0 && (
                      <span className="mono" style={{ fontSize: 11, color: allDayPnl >= 0 ? "var(--up)" : "var(--down)" }}>
                        {allDayPnl >= 0 ? "+" : "−"}<Private>{summarySym}{fmtNum(Math.abs(allDayPnl/summaryFx), 0)}</Private>
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
        <StatTile label={I18N.t("holdings.stat.unrealized")} value={pricesReady ? maskDigits(`${allUnrealized >= 0 ? "+" : "−"}${summarySym}${fmtNum(Math.abs(allUnrealized/summaryFx), 0)}`) : "—"} tone={!pricesReady ? "neutral" : allUnrealized >= 0 ? "up" : "down"} pct={pricesReady && allCost ? (allUnrealized/allCost)*100 : null} sub={pricesReady ? maskDigits(`${I18N.t("holdings.stat.cost")} ${summarySym}${fmtNum(allCost/summaryFx, 0)}`) : I18N.t("holdings.stat.mwrr.loading")}/>
        <StatTile label={I18N.t("holdings.stat.realized")} value={maskDigits(`+${summarySym}${fmtNum((allRealized+allIncomeTotal)/summaryFx, 0)}`)} tone="up" sub={maskDigits(I18N.tf("holdings.stat.realized.detail", { realized: `${summarySym}${fmtNum(allRealized/summaryFx, 0)}`, income: `${summarySym}${fmtNum(allIncomeTotal/summaryFx, 0)}` }))}/>
        {!pricesReady
          ? <StatTile label={I18N.t("holdings.stat.mwrr")} value="—" tone="neutral" sub={I18N.t("holdings.stat.mwrr.loading")}/>
          : allXIRR != null
            ? <StatTile label={I18N.t("holdings.stat.mwrr")} value={`${allXIRR >= 0 ? "+" : ""}${allXIRR.toFixed(1)}%`} tone={allXIRR >= 0 ? "up" : "down"} sub={I18N.t("holdings.stat.mwrr.allAccounts")}/>
            : <StatTile label={I18N.t("holdings.stat.mwrr")} value="—" tone="neutral" sub={I18N.t("holdings.stat.mwrr.noDeposit")}/>
        }
      </div>

      {/* ── Account switcher ──────────────────────────────────────────────── */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 16, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: ".1em", color: "var(--ink-4)", marginRight: 4 }}>{I18N.t("holdings.accounts.label")}</span>
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
            <button onClick={() => setEditingAccount(a)} title={I18N.t("holdings.accounts.editTitle")} style={{ ...btnBase, padding: "5px 6px", borderRight: "none", borderRadius: 0, color: active ? "rgba(255,255,255,0.55)" : "var(--ink-4)", fontSize: 11 }}>
              <Icon name="settings" size={11}/>
            </button>
            <button onClick={() => deleteAccount(a.id, a.name)} title={`${I18N.t("holdings.accounts.deleteTitle")} ${a.name}`} style={{ ...btnBase, padding: "5px 8px", borderRadius: "0 20px 20px 0", color: active ? "rgba(255,255,255,0.5)" : "var(--ink-4)", fontSize: 11, lineHeight: 1 }}>✕</button>
          </div>
        );})}
        <button
          onClick={() => setShowAccountModal(true)}
          style={{ padding: "5px 14px", borderRadius: 20, border: "1px dashed var(--line-2)", background: "transparent", color: "var(--ink-3)", cursor: "pointer", fontSize: 13 }}
        >{I18N.t("holdings.accounts.add")}</button>
        {accounts.length === 0 && (
          <span style={{ fontSize: 12, color: "var(--ink-4)", fontStyle: "italic" }}>{I18N.t("holdings.accounts.empty")}</span>
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
                {pricesReady ? <Private>{sym}{fmtNum(acctTotal, 0)}</Private> : "—"}
              </div>
              <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
                <div>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Mkt </span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? <Private>{sym}{fmtNum(acctMarketValue, 2)}</Private> : "—"}</span>
                </div>
                <div>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>Cash </span>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-2)" }}>{pricesReady ? <Private>{sym}{fmtNum(acctCashValue, 2)}</Private> : "—"}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{I18N.t("holdings.stat.today")} </span>
                  {pricesReady
                    ? <><ChangeNum value={acctTotal ? acctDayPnl / acctTotal * 100 : 0} size="sm"/>
                        {acctDayPnl !== 0 && (
                          <span className="mono" style={{ fontSize: 11, color: acctDayPnl >= 0 ? "var(--up)" : "var(--down)" }}>
                            {acctDayPnl >= 0 ? "+" : "−"}<Private>{sym}{fmtNum(Math.abs(acctDayPnl), 0)}</Private>
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
              label={I18N.t("holdings.stat.unrealized")}
              value={pricesReady ? maskDigits(`${acctUnrealized >= 0 ? "+" : "−"}${sym}${fmtNum(Math.abs(acctUnrealized), 0)}`) : "—"}
              tone={!pricesReady ? "neutral" : acctUnrealized >= 0 ? "up" : "down"}
              pct={hpr}
              sub={pricesReady ? `${I18N.t("holdings.stat.hpr")} ${hpr != null ? (hpr >= 0 ? "+" : "") + hpr.toFixed(2) + "%" : "—"} · ${I18N.t("holdings.stat.netDeposits")} ${maskDigits(`${sym}${fmtNum(acctDeposits, 0)}`)}` : I18N.t("holdings.stat.mwrr.loading")}
            />
            <StatTile label={I18N.t("holdings.stat.realized")} value={maskDigits(`+${sym}${fmtNum((acctRealized + acctIncomeTotal), 0)}`)} tone="up" sub={maskDigits(I18N.tf("holdings.stat.realized.detail", { realized: `${sym}${fmtNum(acctRealized, 0)}`, income: `${sym}${fmtNum(acctIncomeTotal, 0)}` }))}/>
            {!pricesReady
              ? <StatTile label={I18N.t("holdings.stat.mwrr")} value="—" tone="neutral" sub={I18N.t("holdings.stat.mwrr.loading")}/>
              : acctXIRR != null
                ? <StatTile label={I18N.t("holdings.stat.mwrr")} value={`${acctXIRR >= 0 ? "+" : ""}${acctXIRR.toFixed(1)}%`} tone={acctXIRR >= 0 ? "up" : "down"} sub={`${selectedAccount.name} · ${I18N.t("holdings.stat.mwrr.depositBased")}`}/>
                : <StatTile label={I18N.t("holdings.stat.mwrr")} value="—" tone="neutral" sub={I18N.t("holdings.stat.mwrr.noDeposit")}/>
            }
          </div>
        );
      })()}

      {/* ── Inner tabs ────────────────────────────────────────────────────── */}
      <div style={{ marginBottom: 14 }}>
        <Tabs variant="underline" value={tab} onChange={setTab} tabs={[
          { id: "positions",    label: I18N.t("holdings.positions.title"),   count: acctPositions.length },
          { id: "transactions", label: I18N.t("holdings.txns.title"),        count: acctTxns.length },
          { id: "cashflows",    label: I18N.t("holdings.cashflows.title"),   count: acctIncome.filter(i => ["deposit","withdrawal"].includes(i.category)).length || null },
          { id: "income",       label: I18N.t("holdings.income.title"),      count: acctIncome.filter(i => !["deposit","withdrawal"].includes(i.category)).length || null },
          { id: "dividends",    label: I18N.t("holdings.calendar.title"),    count: acctIncome.filter(i => i.category === "dividend").length || null },
          ...(selectedAccount?.benchmark_enabled ? [{ id: "benchmark", label: I18N.t("benchmark.tab.title") }] : []),
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
      {tab === "cashflows"    && (() => { const cfItems = acctIncome.filter(i => ["deposit","withdrawal"].includes(i.category)); return <IncomeTable items={cfItems} total={cfItems.reduce((s,i) => s + i.amount*(FX[i.currency]||1)/acctFx*(i.category==="withdrawal"?-1:1), 0)} acctCcy={acctCcy} acctFx={acctFx} title={I18N.t("holdings.cashflows.title")} subtitle={I18N.t("holdings.cashflows.subtitle")}
          onAdd={() => { setEditingIncome(null); setIncomeDefaultCat("deposit"); setIncomeAllowedCats(["deposit","withdrawal"]); setShowIncomeModal(true); }}
          onEdit={i => { setEditingIncome(i); setIncomeAllowedCats(["deposit","withdrawal"]); setShowIncomeModal(true); }}
          onDelete={id => apiDeleteIncome(id).then(() => setIncome(p => p.filter(i => i.id !== id))).catch(console.error)}
          onImportDone={all => setIncome(all)}
          defaultAccount={acctName}
        />; })()}
      {tab === "income"       && (() => { const divItems = acctIncome.filter(i => !["deposit","withdrawal"].includes(i.category)); return <IncomeTable items={divItems} total={divItems.reduce((s,i) => s + i.amount*(FX[i.currency]||1)/acctFx, 0)} acctCcy={acctCcy} acctFx={acctFx} title={I18N.t("holdings.income.title")} subtitle={I18N.t("holdings.income.subtitle")}
          onAdd={() => { setEditingIncome(null); setIncomeDefaultCat("dividend"); setIncomeAllowedCats(["dividend","interest"]); setShowIncomeModal(true); }}
          onEdit={i => { setEditingIncome(i); setIncomeAllowedCats(["dividend","interest"]); setShowIncomeModal(true); }}
          onDelete={id => apiDeleteIncome(id).then(() => setIncome(p => p.filter(i => i.id !== id))).catch(console.error)}
          onImportDone={all => setIncome(all)}
          defaultAccount={acctName}
        />; })()}
      {tab === "dividends"    && <DividendCalendar incomeItems={acctIncome} positions={acctPositions} acctCcy={acctCcy} acctFx={acctFx}/>}
      {tab === "benchmark" && selectedAccount?.benchmark_enabled && (
        <BenchmarkTab
          account={selectedAccount}
          onAccountUpdated={() => apiGetAccounts().then(setAccounts)}
        />
      )}

{showHoldingModal && <HoldingModal editing={editingHolding} accounts={accounts} defaultAccount={acctName} onClose={() => setShowHoldingModal(false)}
          onSaved={h => {
            const wasVirtual = editingHolding && String(editingHolding.id).startsWith("virtual_");
            setHoldings(prev => {
              if (wasVirtual) return [...prev.filter(x => x.id !== editingHolding.id), h];
              return editingHolding ? prev.map(x => x.id === h.id ? h : x) : [...prev, h];
            });
            setShowHoldingModal(false);
          }}/>}
      {showTxnModal && <TransactionModal editing={editingTxn} accounts={accounts} defaultAccount={acctName} onClose={() => setShowTxnModal(false)}
          onSaved={t => { setTransactions(prev => editingTxn ? prev.map(x => x.id === t.id ? t : x) : [t, ...prev]); setTxnRefresh(r => r + 1); setShowTxnModal(false); }}/>}
      {showIncomeModal && <IncomeModal editing={editingIncome} accounts={accounts} defaultAccount={acctName} defaultCategory={incomeDefaultCat} allowedCategories={incomeAllowedCats} onClose={() => setShowIncomeModal(false)}
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

const POSITIONS_GRID_COLS = "24px 1fr 70px 95px 90px 100px 100px 110px 56px";

const PositionsTable = ({ positions, total, acctCcy = "CNY", acctFx = 1, snapshots, selectedSnapshot, onSnapshotChange, onAddHolding, onEditHolding, onDeleteHolding }) => {
  const sym = ccySymbol(acctCcy);
  return <Card padding={0}>
    <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>{I18N.t("holdings.positions.title")}</div>
        {snapshots && snapshots.length > 0 && (
          <select value={selectedSnapshot || ""} onChange={e => onSnapshotChange(e.target.value || null)}
            style={{ fontSize: 13, border: "1px solid var(--line)", borderRadius: 6, padding: "3px 8px", background: "var(--paper)", color: "var(--ink)", cursor: "pointer" }}>
            {snapshots.map(s => <option key={s} value={s}>{s === "Unnamed" ? I18N.t("holdings.snapshot.unnamed") : s}</option>)}
          </select>
        )}
      </div>
      <Button size="sm" variant="secondary" icon="plus" onClick={onAddHolding}>{I18N.t("holdings.positions.add")}</Button>
    </div>
    {positions.length === 0
      ? <Empty icon="wallet" title={I18N.t("holdings.positions.empty").split(" — ")[0]} hint={I18N.t("holdings.positions.empty").split(" — ")[1]}/>
      : (
        <>
          <div style={{ display: "grid", gridTemplateColumns: POSITIONS_GRID_COLS, gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
            <span/><span>{I18N.t("holdings.col.position")}</span>
            <span style={{textAlign:"right"}}>{I18N.t("holdings.col.shares")}</span><span style={{textAlign:"right"}}>{I18N.t("holdings.col.avgCost")}</span>
            <span style={{textAlign:"right"}}>{I18N.t("holdings.col.price")}</span><span style={{textAlign:"right"}}>{I18N.t("holdings.col.value")} ({acctCcy})</span>
            <span style={{textAlign:"right"}}>{I18N.t("holdings.col.dayChange")}</span><span style={{textAlign:"right"}}>{I18N.t("holdings.col.unrealizedPL")}</span>
            <span/>
          </div>
          {[...positions].sort((a,b) => b.value - a.value).map((p, i, arr) => {
            const cash = p.code === "CASH";
            return (
            <div key={p.id} style={{ display: "grid", gridTemplateColumns: POSITIONS_GRID_COLS, gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < arr.length-1 ? "1px solid var(--line)" : "none" }}>
              <MarketDot market={p.market}/>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>{cash ? `${I18N.t("holdings.positions.cash")} ${p.currency}` : p.code}</span>
                  {!cash && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{p.sym.name || p.name || ""}</span>}
                  {!cash && p.txnCount > 0 && <span style={{ fontSize: 10, color: "var(--ink-4)", padding: "1px 6px", border: "1px solid var(--line)", borderRadius: 4 }}>{p.txnCount} {I18N.t("holdings.positions.txns")}</span>}
                </div>
              </div>
              <span className="mono" style={{textAlign:"right",fontSize:12}}>{cash ? "—" : (p.shares > 0 ? maskDigits(String(p.shares)) : "—")}</span>
              <span className="mono" style={{textAlign:"right",fontSize:12,color:"var(--ink-3)"}}>{cash ? "—" : fmtMoney(p.avgCost, p.currency, priceDp(p))}</span>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}>{cash ? "—" : (p.sym.price ? fmtMoney(p.sym.price, p.currency, priceDp(p)) : "—")}</span>
              <span className="mono" style={{textAlign:"right",fontSize:13,fontWeight:600}}><Private>{sym}{fmtNum(p.value / acctFx, 0)}</Private></span>
              <div style={{textAlign:"right"}}>
                {cash ? "—" : (
                  <>
                    <ChangeNum value={p.dayChange} size="sm"/>
                    <div className="mono" style={{ fontSize: 10.5, color: p.dayChange >= 0 ? "var(--up)" : "var(--down)", marginTop: 1 }}>
                      {p.dayChange >= 0 ? "+" : "−"}<Private>{sym}{fmtNum(Math.abs(p.value / acctFx * p.dayChange / 100), 0)}</Private>
                    </div>
                  </>
                )}
                {!cash && p.afterHoursChangePct != null && (
                  <div style={{fontSize:10,color:"var(--ink-4)",marginTop:1}}>
                    {I18N.t("holdings.positions.afterHours")} <ChangeNum value={p.afterHoursChangePct} size="sm"/>
                  </div>
                )}
              </div>
              <div style={{textAlign:"right"}}>
                {cash ? <span style={{fontSize:12,color:"var(--ink-4)"}}>{I18N.t("holdings.positions.cash")}</span> : (
                  <>
                    <ChangeNum value={p.pnlPct} size="sm"/>
                    <div className="mono" style={{ fontSize: 10.5, color: p.pnl >= 0 ? "var(--up)" : "var(--down)", marginTop: 1 }}>
                      {p.pnl >= 0 ? "+" : "−"}<Private>{sym}{fmtNum(Math.abs(p.pnl / acctFx), 0)}</Private>
                    </div>
                  </>
                )}
              </div>
              <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                <button style={iconBtn} title={I18N.t("holdings.positions.edit")} onClick={() => onEditHolding(p)}><Icon name="edit" size={13}/></button>
                <button style={{ ...iconBtn, color: "var(--up)" }} title={I18N.t("holdings.positions.delete")} onClick={() => { if (confirm(I18N.tf("holdings.positions.deleteConfirm", { code: cash ? I18N.t("holdings.positions.cash") : p.code }))) onDeleteHolding(p.id); }}><Icon name="x" size={13}/></button>
              </div>
            </div>
          );})}
        </>
      )}
  </Card>;
};

// ── Transactions table ────────────────────────────────────────────────────────
const TXN_PAGE_SIZE = 30;

const TransactionsTable = ({ account, refreshKey = 0, allSymbols = [], assetTypeOf = () => null, onAdd, onEdit, onDelete, onImportDone }) => {
  const fileRef = React.useRef(null);
  const [importMsg, setImportMsg] = React.useState(null);
  const [symFilter, setSymFilter] = React.useState("");
  const [page, setPage] = React.useState(1);
  const [data, setData] = React.useState({ items: [], total: 0 });

  const totalPages = Math.max(1, Math.ceil(data.total / TXN_PAGE_SIZE));

  const fetchPage = React.useCallback((pg, sym) => {
    apiGetTransactionsPaged({ page: pg, pageSize: TXN_PAGE_SIZE, symbol: sym, account: account || "" })
      .then(setData)
      .catch(console.error);
  }, [account]);

  React.useEffect(() => { fetchPage(page, symFilter); }, [page, symFilter, fetchPage, refreshKey]);
  React.useEffect(() => { setPage(1); }, [account]);

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
      setImportMsg(`Imported ${result.imported}, skipped ${result.skipped.length}`);
      setTimeout(() => setImportMsg(null), 4000);
    } catch (err) {
      setImportMsg(`Import failed: ${err.message}`);
      setTimeout(() => setImportMsg(null), 4000);
    }
  };

  return (
    <Card padding={0}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>{I18N.t("holdings.txns.title")}</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{I18N.t("holdings.txns.subtitle")}</div>
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {importMsg && <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{importMsg}</span>}
          <select value={symFilter} onChange={e => handleSymFilter(e.target.value)}
            style={{ fontSize: 12, padding: "4px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", cursor: "pointer" }}>
            <option value="">{I18N.t("holdings.txns.allSymbols")}</option>
            {allSymbols.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>{I18N.t("holdings.txns.add")}</Button>
        </div>
      </div>
      {data.total === 0
        ? <Empty icon="book" title={I18N.t("holdings.txns.empty").split(" — ")[0]} hint={I18N.t("holdings.txns.empty").split(" — ")[1]}/>
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
                  <Badge tone={t.side === "buy" ? "up" : "down"} solid={false} size="sm">{t.side === "buy" ? I18N.t("holdings.txns.buy") : I18N.t("holdings.txns.sell")}</Badge>
                  <span className="mono" style={{fontWeight:600}}>{t.code}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.shares > 0 ? maskDigits(String(t.shares)) : "—"}</span>
                  <span className="mono" style={{textAlign:"right"}}>{t.price > 0 ? fmtMoney(t.price, t.currency, assetTypeOf(t.code) === "mutualfund" ? 4 : 2) : "—"}</span>
                  <span className="mono" style={{textAlign:"right",fontWeight:600}}><Private>{amt > 0 ? fmtMoney(amt, t.currency, 0) : "—"}</Private></span>
                  <span className="mono" style={{textAlign:"right",color:t.realized>=0?"var(--up)":t.realized!=null?"var(--down)":"var(--ink-4)",fontWeight:600}}>
                    <Private>{t.realized != null ? (t.realized >= 0 ? "+" : "−") + fmtMoney(Math.abs(t.realized), t.currency, 0) : "—"}</Private>
                  </span>
                  <span style={{color:"var(--ink-3)",fontSize:12,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap",paddingLeft:24}}>{t.note || ""}</span>
                  <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                    <button style={iconBtn} title={I18N.t("holdings.txns.edit")} onClick={() => onEdit(t)}><Icon name="edit" size={13}/></button>
                    <button style={{ ...iconBtn, color: "var(--up)" }} title={I18N.t("holdings.txns.delete")} onClick={() => { if (confirm(I18N.t("holdings.txns.deleteConfirm"))) onDelete(t.id).then(() => fetchPage(page, symFilter)); }}><Icon name="x" size={13}/></button>
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
const IncomeTable = ({ items, total, acctCcy = "CNY", acctFx = 1, onAdd, onEdit, onDelete, onImportDone, defaultAccount, title, subtitle }) => {
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
      setImportMsg(`Imported ${result.imported}${result.skipped.length ? `, skipped ${result.skipped.length}` : ""}`);
    } catch (ex) {
      setImportMsg(`Import failed: ${ex.message}`);
    }
  };
  const sym = ccySymbol(acctCcy);
  const catColors = { dividend: "#1F8A4C", interest: "#2D5BD9", option: "#6B4FB8", deposit: "#2D9CDB", withdrawal: "#C8460F" };
  const catLabels = { dividend: I18N.t("holdings.income.cat.dividend"), interest: I18N.t("holdings.income.cat.interest"), option: I18N.t("holdings.income.cat.option"), deposit: I18N.t("holdings.income.cat.deposit"), withdrawal: I18N.t("holdings.income.cat.withdrawal") };
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
                {cat === "deposit" ? "-" : "+"}<Private>{sym}{fmtNum(v, 0)}</Private>
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>{I18N.tf("holdings.income.cat.count", { n: items.filter(i => i.category === cat).length })}</div>
            </Card>
          ))}
        </div>
      )}
      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>{title || I18N.t("holdings.income.title")}</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{subtitle || I18N.t("holdings.income.subtitle")} — {I18N.t("holdings.income.total")} <Private>{sym}{fmtNum(Math.abs(total), 0)}</Private></div>
          </div>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <Button size="sm" variant="secondary" icon="plus" onClick={onAdd}>{I18N.t("holdings.income.add")}</Button>
          </div>
        </div>
        {sorted.length === 0
          ? <Empty icon="spark" title={I18N.t("holdings.income.empty").split(" — ")[0]} hint={I18N.t("holdings.income.empty").split(" — ")[1]}/>
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
                      <Private>{sign}{fmtMoney(i.amount, i.currency, 2)}</Private>
                    </span>
                    <span className="mono" style={{textAlign:"right",color:"var(--ink-3)"}}>
                      <Private>{i.currency !== acctCcy ? `${sign}${sym}${fmtNum(acctAmt, 0)}` : "—"}</Private>
                    </span>
                    <span style={{color:"var(--ink-3)",fontSize:12}}>{i.note || "—"}</span>
                    <div style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                      <button style={iconBtn} title={I18N.t("holdings.income.edit")} onClick={() => onEdit(i)}><Icon name="edit" size={13}/></button>
                      <button style={{ ...iconBtn, color: "var(--up)" }} title={I18N.t("holdings.income.delete")} onClick={() => { if (confirm(I18N.t("holdings.income.deleteConfirm"))) onDelete(i.id); }}><Icon name="x" size={13}/></button>
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

const MONTH_NAMES = () => [1,2,3,4,5,6,7,8,9,10,11,12].map(n => I18N.t(`holdings.month.${n}`));
const WEEK_HDR    = () => ["mon","tue","wed","thu","fri","sat","sun"].map(d => I18N.t(`holdings.week.${d}`));

const divFreq = (hist) => {
  const oneYearAgo = new Date();
  oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);
  return Math.max(hist.filter(h => new Date(h.date) >= oneYearAgo).length, 1);
};

const DivUpcomingStrip = ({ upcoming, posByCode, acctFx, sym }) => {
  if (!upcoming.length) return null;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 8 }}>{I18N.t("holdings.calendar.upcoming")}</div>
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
        <span className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>{year} {MONTH_NAMES()[month - 1]}</span>
        <button onClick={nextMonth} style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink-3)", padding: "4px 10px", fontSize: 18 }}>›</button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, 1fr)", gap: 3, marginBottom: 4 }}>
        {WEEK_HDR().map(h => (
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
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "var(--up)", display: "inline-block" }}/>{I18N.t("holdings.calendar.recorded")}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 8, height: 8, borderRadius: "50%", background: "rgba(31,138,76,0.4)", display: "inline-block" }}/>{I18N.t("holdings.calendar.historical")}</div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-4)" }}><span style={{ width: 10, height: 10, borderRadius: 2, border: "1.5px dashed var(--up)", display: "inline-block" }}/>{I18N.t("holdings.calendar.upcoming")}</div>
      </div>
      {selectedEvents.length > 0 && (
        <div style={{ marginTop: 12, borderTop: "1px solid var(--line)", paddingTop: 12 }}>
          <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-3)", marginBottom: 8 }}>{selectedKey}</div>
          {selectedEvents.map((e, idx) => (
            <div key={idx} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "5px 0", borderBottom: idx < selectedEvents.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
              <div>
                <span style={{ fontWeight: 600, marginRight: 6 }}>{e.source || e.code || "—"}</span>
                <Badge size="sm" tone={e.type === "income" ? "down" : "info"}>
                  {e.type === "income" ? I18N.t("holdings.calendar.recorded") : e.type === "upcoming" ? I18N.t("holdings.calendar.exDate") : I18N.t("holdings.calendar.historical")}
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
              {d.ex_date && <div style={{ fontSize: 11, color: d.ex_date >= today ? "var(--up)" : "var(--ink-4)", marginTop: 2 }}>{I18N.t("holdings.calendar.exDate")} {d.ex_date}</div>}
            </div>
            <div style={{ textAlign: "right" }}>
              {d.annual_rate && <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{ccySymbol(pos?.currency || "USD")}{d.annual_rate.toFixed(2)}/sh/yr</div>}
              {yieldPct && <div className="mono" style={{ fontSize: 12, color: "var(--up)", marginTop: 2 }}>{yieldPct.toFixed(2)}%</div>}
            </div>
          </div>
          {estAnnual && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>≈ {sym}{fmtNum(estAnnual, 0)}{I18N.t("holdings.calendar.perYear")}</div>}
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
      {loading && !hasAnyData && <div style={{ textAlign: "center", padding: "40px 0", color: "var(--ink-4)", fontSize: 13 }}>{I18N.t("holdings.calendar.loading")}</div>}
      {!loading && fetchError && <div style={{ textAlign: "center", padding: "20px 0", color: "var(--ink-3)", fontSize: 13 }}>{I18N.t("holdings.calendar.error")}</div>}
      {!loading && !fetchError && !hasAnyData && <Empty icon="spark" title={I18N.t("holdings.calendar.empty")} hint={I18N.t("holdings.calendar.empty.hint")}/>}
      {hasAnyData && (
        <div style={{ maxWidth: 1120, display: "grid", gridTemplateColumns: "1fr 440px", gap: 16, alignItems: "start" }}>
          <DivMonthGrid year={year} month={month} today={today} eventsByDate={eventsByDate} selectedDay={selectedDay} setSelectedDay={setSelectedDay} prevMonth={prevMonth} nextMonth={nextMonth} />
          {Object.keys(divData).length === 1 ? (
            <div style={{ display: "flex", flexDirection: "column", gap: 10, width: "calc((100% - 10px) / 2)" }}>
              {totalEstAnnual > 0 && (
                <Card padding={14}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 4 }}>{I18N.t("holdings.calendar.annualEst")}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--up)" }}><Private>{sym}{fmtNum(totalEstAnnual, 0)}</Private></span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{I18N.t("holdings.calendar.perYear")}</span>
                  </div>
                </Card>
              )}
              <DivStockList divData={divData} posByCode={posByCode} today={today} acctFx={acctFx} sym={sym} />
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
              {totalEstAnnual > 0 && (
                <Card padding={14} style={{ gridColumn: "1 / -1" }}>
                  <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)", marginBottom: 4 }}>{I18N.t("holdings.calendar.annualEst")}</div>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                    <span className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--up)" }}><Private>{sym}{fmtNum(totalEstAnnual, 0)}</Private></span>
                    <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{I18N.t("holdings.calendar.perYear")}</span>
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

const _RB_LABEL_KEYS = {
  "US Stocks": "holdings.rb.us", "US": "holdings.rb.us", "美股": "holdings.rb.us", "美股 US": "holdings.rb.us",
  "HK Stocks": "holdings.rb.hk", "HK": "holdings.rb.hk", "港股": "holdings.rb.hk", "港股 HK": "holdings.rb.hk",
  "CN Stocks": "holdings.rb.cn", "CN": "holdings.rb.cn", "A股": "holdings.rb.cn", "A股 CN": "holdings.rb.cn", "A 股 CN": "holdings.rb.cn",
  "Bonds": "holdings.rb.bonds", "债券": "holdings.rb.bonds", "债券 Bonds": "holdings.rb.bonds",
  "Cash": "holdings.rb.cash", "现金": "holdings.rb.cash", "现金 Cash": "holdings.rb.cash",
  "Gold": "holdings.rb.gold", "黄金": "holdings.rb.gold", "黄金 Gold": "holdings.rb.gold",
  "Equity": "holdings.rb.equity", "权益": "holdings.rb.equity", "股票 Equity": "holdings.rb.equity",
  "Bonds / Cash": "holdings.rb.bonds_cash", "债券 / 现金": "holdings.rb.bonds_cash",
  "LT Bonds": "holdings.rb.lt.bonds", "长债": "holdings.rb.lt.bonds",
  "MT Bonds": "holdings.rb.mt.bonds", "中债": "holdings.rb.mt.bonds",
  "Commodities": "holdings.rb.commodities", "大宗": "holdings.rb.commodities", "大宗 Commodities": "holdings.rb.commodities",
};
const _rbLabel = (b) => {
  if (_RB_LABEL_KEYS[b.label]) return I18N.t(_RB_LABEL_KEYS[b.label]);
  return b.label;
};

const computeAgeRuleBuckets = (age) => [
  { get label() { return I18N.t("holdings.rb.equity"); },      pct: Math.max(0, 100 - age), color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, markets: [], isCash: false },
  { get label() { return I18N.t("holdings.rb.bonds_cash"); },  pct: Math.min(100, age),     color: "#5C6270", codes: [], assetTypes: ["bond"],        markets: [], isCash: true  },
];

const RB_PRESETS = [
  {
    id: "personal",
    get label() { return I18N.t("holdings.rb.personal"); },
    get author() { return I18N.t("holdings.rb.personal.author"); },
    get quote() { return I18N.t("holdings.rb.personal.quote"); },
    buckets: [
      { get label() { return I18N.t("holdings.rb.us"); },    pct: 50, color: "#1F4FE0", codes: [], assetTypes: ["equity","etf"], markets: ["US"],            isCash: false },
      { get label() { return I18N.t("holdings.rb.hk"); },    pct: 15, color: "#B8447B", codes: [], assetTypes: ["equity","etf"], markets: ["HK"],            isCash: false },
      { get label() { return I18N.t("holdings.rb.cn"); },    pct: 10, color: "#C8460F", codes: [], assetTypes: ["equity","etf"], markets: ["CN"],            isCash: false },
      { get label() { return I18N.t("holdings.rb.bonds"); }, pct:  5, color: "#5C8AE6", codes: [], assetTypes: ["bond"],         markets: [],               isCash: false },
      { get label() { return I18N.t("holdings.rb.gold"); },  pct:  5, color: "#C8A000", codes: ["GLD","IAU","SGOL","2840.HK"],   assetTypes: [],            markets: [], isCash: false },
      { get label() { return I18N.t("holdings.rb.cash"); },  pct: 15, color: "#5C6270", codes: [],                               assetTypes: [], markets: [], isCash: true  },
    ],
  },
  {
    id: "60_40",
    get label() { return I18N.t("holdings.rb.6040.label"); },
    author: "John Bogle",
    get quote() { return I18N.t("holdings.rb.6040.quote"); },
    buckets: [
      { get label() { return I18N.t("holdings.rb.equity"); },     pct: 60, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { get label() { return I18N.t("holdings.rb.bonds_cash"); }, pct: 40, color: "#5C6270", codes: [], assetTypes: ["bond"],        isCash: true  },
    ],
  },
  {
    id: "70_30",
    get label() { return I18N.t("holdings.rb.7030.label"); },
    author: "Vanguard",
    get quote() { return I18N.t("holdings.rb.7030.quote"); },
    buckets: [
      { get label() { return I18N.t("holdings.rb.equity"); },     pct: 70, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { get label() { return I18N.t("holdings.rb.bonds_cash"); }, pct: 30, color: "#5C6270", codes: [], assetTypes: ["bond"],        isCash: true  },
    ],
  },
  {
    id: "all_weather",
    get label() { return I18N.t("holdings.rb.allweather.label"); },
    author: "Ray Dalio",
    get quote() { return I18N.t("holdings.rb.allweather.quote"); },
    buckets: [
      { get label() { return I18N.t("holdings.rb.equity"); }, pct: 30,  color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { get label() { return I18N.t("holdings.rb.lt.bonds"); },    pct: 40,  color: "#5C8AE6", codes: [], assetTypes: ["bond"],         isCash: false },
      { get label() { return I18N.t("holdings.rb.mt.bonds"); },    pct: 15,  color: "#B8447B", codes: [], assetTypes: [],               isCash: false },
      { get label() { return I18N.t("holdings.rb.gold"); },        pct: 7.5, color: "#C8460F", codes: [], assetTypes: [],               isCash: false },
      { get label() { return I18N.t("holdings.rb.commodities"); }, pct: 7.5, color: "#9C6E3A", codes: [], assetTypes: [],               isCash: true  },
    ],
  },
  {
    id: "permanent",
    get label() { return I18N.t("holdings.rb.permanent.label"); },
    author: "Harry Browne",
    get quote() { return I18N.t("holdings.rb.permanent.quote"); },
    buckets: [
      { get label() { return I18N.t("holdings.rb.equity"); },   pct: 25, color: "#1F4FE0", codes: [], assetTypes: RB_EQUITY_TYPES, isCash: false },
      { get label() { return I18N.t("holdings.rb.lt.bonds"); }, pct: 25, color: "#5C8AE6", codes: [], assetTypes: ["bond"],        isCash: false },
      { get label() { return I18N.t("holdings.rb.cash"); },     pct: 25, color: "#5C6270", codes: [], assetTypes: [],              isCash: true  },
      { get label() { return I18N.t("holdings.rb.gold"); },     pct: 25, color: "#C8460F", codes: [], assetTypes: [],               isCash: false },
    ],
  },
  {
    id: "age_rule",
    get label() { return I18N.t("holdings.rb.lifecycle.label"); },
    get author() { return I18N.t("holdings.rb.lifecycle.author"); },
    get quote() { return I18N.t("holdings.rb.lifecycle.quote"); },
    buckets: null,
  },
];

const RB_TRIGGER_MODES = [
  { id: "calendar", get label() { return I18N.t("holdings.rebalance.trigger.calendar"); }, get desc() { return I18N.t("holdings.rebalance.freq.monthly"); } },
  { id: "absolute", get label() { return I18N.t("holdings.rebalance.trigger.absolute"); }, get desc() { return I18N.t("holdings.rebalance.absThreshold"); } },
  { id: "relative", get label() { return I18N.t("holdings.rebalance.trigger.relative"); }, get desc() { return I18N.t("holdings.rebalance.relThreshold"); } },
  { id: "hybrid",   get label() { return I18N.t("holdings.rebalance.trigger.hybrid"); },   get desc() { return I18N.t("holdings.rebalance.trigger.hybrid"); } },
];

const RB_CAL_OPTIONS = [
  { value: "monthly",   get label() { return I18N.t("holdings.rebalance.freq.monthly"); } },
  { value: "quarterly", get label() { return I18N.t("holdings.rebalance.freq.quarterly"); } },
  { value: "semi",      get label() { return I18N.t("holdings.rebalance.freq.semi"); } },
  { value: "annual",    get label() { return I18N.t("holdings.rebalance.freq.annual"); } },
];

const RB_DEFAULT_CONFIG = {
  presetId: "personal",
  buckets: [
    { label: "US",    pct: 50, color: "#1F4FE0", codes: [], assetTypes: ["equity","etf"], markets: ["US"],            isCash: false },
    { label: "HK",    pct: 15, color: "#B8447B", codes: [], assetTypes: ["equity","etf"], markets: ["HK"],            isCash: false },
    { label: "CN",    pct: 10, color: "#C8460F", codes: [], assetTypes: ["equity","etf"], markets: ["CN"],            isCash: false },
    { label: "Bonds", pct:  5, color: "#5C8AE6", codes: [], assetTypes: ["bond"],         markets: [],               isCash: false },
    { label: "Gold",  pct:  5, color: "#C8A000", codes: ["GLD","IAU","SGOL","2840.HK"],   assetTypes: [], markets: [], isCash: false },
    { label: "Cash",  pct: 15, color: "#5C6270", codes: [], assetTypes: [],               markets: [],               isCash: true  },
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
    <Modal open={true} onClose={onClose} title={I18N.t("holdings.rebalance.editTarget")} width={500}>
      <div style={{ padding: "16px 20px", maxHeight: "72vh", overflowY: "auto" }}>
        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", marginBottom: 8, textTransform: "uppercase", letterSpacing: ".1em" }}>{I18N.t("holdings.rebalance.preset")}</div>
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
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{I18N.t("app.settings.birthDate")}</span>
            {birthDate ? (
              <span className="mono" style={{ fontSize: 12, color: "var(--ink-4)" }}>
                {birthDate} · {computeAge(birthDate)} · Eq {Math.max(0, 100 - computeAge(birthDate))}% / {I18N.t("base.market.bonds")} {Math.min(100, computeAge(birthDate))}%
              </span>
            ) : (
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>{I18N.t("holdings.rebalance.noBirthDate")} · {I18N.t("holdings.rebalance.noBirthDate.hint")}</span>
            )}
          </div>
        )}

        <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-4)", marginBottom: 10, textTransform: "uppercase", letterSpacing: ".1em" }}>{I18N.t("holdings.rebalance.buckets")}</div>
        {draft.buckets.map((b, i) => (
          <div key={i} style={{ marginBottom: 12, paddingBottom: 12, borderBottom: "1px solid var(--line)" }}>
            <div style={{ display: "grid", gridTemplateColumns: "10px 1fr 64px 20px", alignItems: "center", gap: 10, marginBottom: 6 }}>
              <span style={{ width: 10, height: 10, background: b.color, borderRadius: 2, display: "block" }}/>
              <span style={{ fontSize: 13, fontWeight: 500 }}>{_rbLabel(b)}</span>
              <Input value={String(b.pct)} onChange={v => updateBucket(i, "pct", parseFloat(v) || 0)} inputMode="decimal" style={{ textAlign: "right" }}/>
              <span style={{ fontSize: 12, color: "var(--ink-4)" }}>%</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, paddingLeft: 18 }}>
              <span style={{ fontSize: 10.5, color: "var(--ink-4)", flexShrink: 0, width: 52 }}>{I18N.t("holdings.rebalance.codeOverride")}</span>
              <input
                value={codesTexts[i]}
                onChange={e => setCodesTexts(t => t.map((v, j) => j === i ? e.target.value : v))}
                placeholder="013308, TEC.TO"
                autoComplete="off"
                style={{ flex: 1, fontSize: 11.5, border: "1px solid var(--line-2)", borderRadius: 5, padding: "3px 8px", background: "var(--bg-deep)", color: "var(--ink)", outline: "none" }}
              />
            </div>
          </div>
        ))}
        <div style={{ textAlign: "right", fontSize: 12, color: valid ? "var(--down)" : "var(--up)", marginBottom: 16 }}>
          {I18N.t("holdings.rebalance.total")} {sumPct.toFixed(1)}% {valid ? "✓" : `· ${I18N.t("holdings.rebalance.mustEqual100")}`}
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={() => handleSave(draft)} disabled={!valid}>{I18N.t("base.btn.save")}</Button>
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
        <Button variant="secondary" icon="settings" onClick={() => setEditOpen(true)}>{I18N.t("holdings.rebalance.editTarget")}</Button>
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
                  {computeAge(birthDate)} · Eq {Math.max(0, 100 - computeAge(birthDate))}% / {I18N.t("base.market.bonds")} {Math.min(100, computeAge(birthDate))}%
                </span>
              ) : (
                <span style={{ fontSize: 11, color: "var(--ink-4)" }}>{I18N.t("holdings.rebalance.noBirthDate")}</span>
              )}
              <span style={{ fontSize: 10.5, color: "var(--ink-5)" }}>· {I18N.t("holdings.rebalance.noBirthDate.hint")}</span>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 28 }}>
        {/* Left: drift bars */}
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>{I18N.t("holdings.rebalance.driftVs")} {I18N.t("holdings.rebalance.target")}</div>
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
                    {_rbLabel(b)}
                    <span style={{ fontSize: 10, color: "var(--ink-4)", marginLeft: 2 }}>{isExpanded ? "▲" : "▼"}</span>
                  </button>
                  <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-2)" }}>
                    <Private>{dispSym}{fmtNum(b.current / dispFx / 1000, 1)}k</Private>
                    <span style={{ color: "var(--ink-5)", margin: "0 5px" }}>·</span>
                    <span style={{ color: b.drift > 0 ? "var(--up)" : b.drift < 0 ? "var(--down)" : "var(--ink-3)", fontWeight: 600 }}>{b.curPct.toFixed(1)}%</span>
                    <span style={{ color: "var(--ink-4)" }}> → {b.pct}%</span>
                  </span>
                </div>

                {/* Current bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 3 }}>
                  <span style={{ fontSize: 9, color: "var(--ink-4)", width: 22, textAlign: "right" }}>{I18N.t("base.label.current")}</span>
                  <div style={{ position: "relative", flex: 1, height: 7, background: "var(--bg-deep)", borderRadius: 3 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, width: `${Math.min(b.curPct, 100)}%`, height: "100%", background: b.color, borderRadius: 3 }}/>
                    <div style={{ position: "absolute", left: `${b.pct}%`, top: -3, width: 2, height: 13, background: "var(--ink-3)", borderRadius: 1 }}/>
                  </div>
                </div>

                {/* Target bar */}
                <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 5 }}>
                  <span style={{ fontSize: 9, color: "var(--ink-5)", width: 22, textAlign: "right" }}>{I18N.t("holdings.rebalance.target")}</span>
                  <div style={{ position: "relative", flex: 1, height: 5, background: "var(--bg-deep)", borderRadius: 3 }}>
                    <div style={{ position: "absolute", left: 0, top: 0, width: `${b.pct}%`, height: "100%", background: b.color, opacity: 0.25, borderRadius: 3 }}/>
                    <div style={{ position: "absolute", left: `${b.pct}%`, top: -3, width: 2, height: 11, background: "var(--ink-3)", borderRadius: 1 }}/>
                  </div>
                </div>

                {/* Drift row */}
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, paddingLeft: 28 }}>
                  <span className="mono" style={{ color: fires ? "var(--up)" : "var(--ink-4)", fontWeight: fires ? 600 : 400 }}>
                    {I18N.t("holdings.rebalance.drift")} {b.drift >= 0 ? "+" : ""}{b.drift.toFixed(1)}{I18N.t("holdings.rebalance.pp")}
                    {mode !== "calendar" && <span style={{ color: "var(--ink-4)", fontWeight: 400 }}> · {b.relDrift.toFixed(0)}% {I18N.t("holdings.rebalance.trigger.relative")}</span>}
                    {fires && " ⚠"}
                  </span>
                  <span className="mono" style={{ color: "var(--ink-4)" }}>
                    {I18N.t("holdings.rebalance.suggest")} {b.delta >= 0 ? I18N.t("holdings.rebalance.buy") : I18N.t("holdings.rebalance.sell")} <Private>{dispSym}{fmtNum(Math.abs(b.delta) / dispFx / 1000, 1)}k</Private>
                  </span>
                </div>

                {/* Expanded positions */}
                {isExpanded && (
                  <div style={{ marginTop: 8, marginLeft: 28, padding: "8px 12px", background: "var(--bg-deep)", borderRadius: 6, borderLeft: `3px solid ${b.color}` }}>
                    {b.bPositions.length === 0 ? (
                      <div style={{ fontSize: 11, color: "var(--ink-4)", fontStyle: "italic" }}>
                        {b.isCash ? I18N.t("holdings.rebalance.noCash") : I18N.t("holdings.rebalance.noMatch")}
                      </div>
                    ) : (
                      <>
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: "2px 12px", fontSize: 10, color: "var(--ink-5)", fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", marginBottom: 6 }}>
                          <span>{I18N.t("holdings.txn.symbol").replace(" *","")}</span><span>{I18N.t("holdings.holding.account")}</span><span style={{ textAlign: "right" }}>{I18N.t("holdings.income.amount").replace(" *","")}</span><span style={{ textAlign: "right" }}>%</span>
                        </div>
                        {b.bPositions.map((p, j) => (
                          <div key={j} style={{ display: "grid", gridTemplateColumns: "1fr 1fr auto auto", gap: "3px 12px", fontSize: 11.5, padding: "3px 0", borderTop: j > 0 ? "1px solid var(--line)" : "none", alignItems: "center" }}>
                            <span style={{ fontWeight: 600, color: "var(--ink-2)" }}>{p.code}</span>
                            <span style={{ color: "var(--ink-4)", fontSize: 11 }}>{p.account}</span>
                            <span className="mono" style={{ color: "var(--ink-2)", textAlign: "right" }}><Private>{dispSym}{fmtNum(p.value / dispFx / 1000, 1)}k</Private></span>
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
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 10 }}>{I18N.t("holdings.rebalance.triggers")}</div>

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
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{I18N.t("holdings.rebalance.freq")}</span>
                <Select value={calFreq} onChange={v => setTrigger("calFreq", v)} options={RB_CAL_OPTIONS} style={{ width: 96 }}/>
              </div>
            )}
            {(mode === "absolute" || mode === "hybrid") && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{I18N.t("holdings.rebalance.absThreshold")}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <Input value={String(absDriftPp)} onChange={v => setTrigger("absDriftPp", parseFloat(v) || 5)} inputMode="decimal" style={{ width: 56, textAlign: "right" }}/>
                  <span style={{ fontSize: 12, color: "var(--ink-4)", width: 18 }}>pp</span>
                </div>
              </div>
            )}
            {(mode === "relative" || mode === "hybrid") && (
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{I18N.t("holdings.rebalance.relThreshold")}</span>
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
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>📅 {calLabel} · {I18N.t("holdings.rebalance.trigger.calendar")}</div>
            ) : triggered.length > 0 ? (
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#7A4D0E", marginBottom: 4 }}>⚠ {triggered.length} {I18N.t("holdings.rebalance.triggered")}</div>
                {triggered.map((b, i) => (
                  <div key={i} style={{ fontSize: 11, color: "#7A4D0E" }}>
                    {_rbLabel(b)}：{b.drift >= 0 ? "+" : ""}{b.drift.toFixed(1)}{I18N.t("holdings.rebalance.pp")} ({b.relDrift.toFixed(0)}% {I18N.t("holdings.rebalance.trigger.relative")})
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>✓ {I18N.t("holdings.rebalance.allOk")}</div>
            )}
            {mode === "hybrid" && (
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: triggered.length > 0 ? 6 : 0 }}>
                {calLabel} · &gt;{absDriftPp}pp {I18N.t("holdings.rebalance.trigger.hybrid")}
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
  if (/^\d{6}$/.test(code)) return "CN"; // bare 6-digit = CN stock / fund code
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
            <div style={{ padding: "8px 12px", fontSize: 12, color: "var(--ink-4)" }}>{I18N.t("base.empty.loading")}</div>
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

// ── Benchmark Tab ────────────────────────────────────────────────────────────

const _knownSymbols = () => [
  { value: "SPY",       label: `SPY — ${I18N.t("symbol.SPY")}` },
  { value: "QQQ",       label: `QQQ — ${I18N.t("symbol.QQQ")}` },
  { value: "^HSI",      label: `^HSI — ${I18N.t("symbol.HSI")}` },
  { value: "3033.HK",   label: `3033.HK — ${I18N.t("symbol.HS_TECH")}` },
  { value: "000300.SS", label: `000300.SS — ${I18N.t("symbol.CSI300")}` },
  { value: "000001.SS", label: `000001.SS — ${I18N.t("symbol.SSE_COMP")}` },
  { value: "VT",        label: `VT — ${I18N.t("symbol.VT")}` },
  { value: "BNDW",      label: `BNDW — ${I18N.t("symbol.BNDW")}` },
  { value: "VOO",       label: `VOO — ${I18N.t("symbol.VOO")}` },
  { value: "BSV",       label: `BSV — ${I18N.t("symbol.BSV")}` },
  { value: "BTC-USD",   label: `BTC-USD — ${I18N.t("symbol.BTC")}` },
];

const _CASH_VALUE = "__CASH__";

const CustomSchemeEditor = ({ scheme, onSave, onCancel }) => {
  const knownSymbols = _knownSymbols();
  const [name, setName] = React.useState(scheme?.name || "");
  const [rows, setRows] = React.useState(
    scheme?.allocations?.length
      ? scheme.allocations.map(a => ({ type: "symbol", symbol: a.symbol, pct: String(a.pct) }))
      : [{ type: "symbol", symbol: "SPY", pct: "100" }]
  );
  const [cashPct, setCashPct] = React.useState(String(scheme?.cash_pct ?? 0));
  const [customSymbol, setCustomSymbol] = React.useState({});
  const [editConfirmed, setEditConfirmed] = React.useState(false);

  const isEditMode = !!scheme;
  const allocSum = rows.reduce((s, r) => s + (parseFloat(r.pct) || 0), 0) + (parseFloat(cashPct) || 0);
  const isValid = name.trim() && Math.abs(allocSum - 100) < 0.01 && rows.length > 0 && (!isEditMode || editConfirmed);

  const updateRow = (i, field, val) => setRows(rs => rs.map((r, j) => j === i ? { ...r, [field]: val } : r));
  const removeRow = (i) => setRows(rs => rs.filter((_, j) => j !== i));
  const addRow = () => setRows(rs => [...rs, { type: "symbol", symbol: "SPY", pct: "0" }]);

  const handleSave = () => {
    const allocations = rows.map(r => ({
      symbol: r.type === _CASH_VALUE ? _CASH_VALUE : (customSymbol[rows.indexOf(r)] || r.symbol),
      pct: parseFloat(r.pct) || 0,
    })).filter(a => a.symbol !== _CASH_VALUE);
    onSave({ id: scheme?.id, name: name.trim(), allocations, cash_pct: parseFloat(cashPct) || 0 });
  };

  return (
    <div style={{ background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 8, padding: "14px 16px", marginTop: 10 }}>
      {isEditMode && (
        <div style={{ fontSize: 12, color: "#92400e", background: "#fef3c7", border: "1px solid #fcd34d", borderRadius: 6, padding: "8px 10px", marginBottom: 12 }}>
          <div style={{ marginBottom: 7 }}>⚠ {I18N.t("benchmark.custom.editWarning")}</div>
          <label style={{ display: "flex", alignItems: "center", gap: 7, cursor: "pointer", userSelect: "none" }}>
            <input type="checkbox" checked={editConfirmed} onChange={e => setEditConfirmed(e.target.checked)}
              style={{ width: 14, height: 14, cursor: "pointer", accentColor: "#d97706" }}/>
            <span>{I18N.t("benchmark.custom.editConfirm")}</span>
          </label>
        </div>
      )}
      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em" }}>{I18N.t("benchmark.scheme.name")}</label>
        <input value={name} onChange={e => setName(e.target.value)} autoComplete="off"
          style={{ display: "block", marginTop: 4, width: "100%", fontSize: 13, padding: "6px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", boxSizing: "border-box" }}/>
      </div>
      <div style={{ marginBottom: 10 }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em" }}>{I18N.t("benchmark.scheme.alloc")}</label>
        <div style={{ marginTop: 6, display: "grid", gridTemplateColumns: "1fr 80px 28px", gap: "4px 6px", alignItems: "center" }}>
          {rows.map((r, i) => {
            const knownOpt = knownSymbols.find(s => s.value === r.symbol);
            const isCustomSym = !knownOpt;
            return (
              <React.Fragment key={i}>
                <div>
                  <select value={knownOpt ? r.symbol : "__custom__"} onChange={e => {
                      if (e.target.value === "__custom__") updateRow(i, "symbol", "");
                      else updateRow(i, "symbol", e.target.value);
                    }}
                    style={{ width: "100%", fontSize: 12, padding: "5px 6px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)" }}>
                    {knownSymbols.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                    <option value="__custom__">{I18N.t("benchmark.scheme.customSymbol")}</option>
                  </select>
                  {(!knownOpt) && (
                    <input value={r.symbol} onChange={e => updateRow(i, "symbol", e.target.value.toUpperCase())} autoComplete="off"
                      placeholder="e.g. ARKK" style={{ marginTop: 4, width: "100%", fontSize: 12, padding: "5px 6px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", boxSizing: "border-box" }}/>
                  )}
                </div>
                <input value={r.pct} onChange={e => updateRow(i, "pct", e.target.value)} autoComplete="off"
                  type="number" min="0" max="100" step="1"
                  style={{ fontSize: 12, padding: "5px 6px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", textAlign: "right" }}/>
                <button type="button" onClick={() => removeRow(i)} disabled={rows.length <= 1}
                  style={{ border: "none", background: "none", color: "var(--ink-4)", cursor: rows.length <= 1 ? "default" : "pointer", fontSize: 15, padding: 0, opacity: rows.length <= 1 ? 0.3 : 1 }}>✕</button>
              </React.Fragment>
            );
          })}
        </div>
        <button type="button" onClick={addRow} style={{ marginTop: 6, fontSize: 12, color: "var(--ink-3)", border: "1px dashed var(--line-2)", borderRadius: 6, background: "none", padding: "3px 10px", cursor: "pointer" }}>+ Add</button>
      </div>
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}>
        <label style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em" }}>{I18N.t("benchmark.scheme.cashPct")}</label>
        <input value={cashPct} onChange={e => setCashPct(e.target.value)} autoComplete="off"
          type="number" min="0" max="100" step="1"
          style={{ width: 70, fontSize: 12, padding: "5px 6px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", textAlign: "right" }}/>
        <span style={{ fontSize: 12, color: Math.abs(allocSum - 100) < 0.01 ? "var(--accent)" : "var(--up)", fontWeight: 600 }}>
          {I18N.t("benchmark.scheme.allocSum").replace("{n}", allocSum.toFixed(1))}
        </span>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" onClick={onCancel} style={{ fontSize: 12, padding: "5px 14px", border: "1px solid var(--line)", borderRadius: 6, background: "none", color: "var(--ink-3)", cursor: "pointer" }}>{I18N.t("benchmark.custom.cancel")}</button>
        <button type="button" onClick={handleSave} disabled={!isValid} style={{ fontSize: 12, padding: "5px 14px", border: "none", borderRadius: 6, background: isValid ? "var(--ink)" : "var(--line)", color: isValid ? "#fff" : "var(--ink-4)", cursor: isValid ? "pointer" : "default" }}>{I18N.t("benchmark.custom.save")}</button>
      </div>
    </div>
  );
};

const BenchmarkTab = ({ account, onAccountUpdated }) => {
  const [defaults, setDefaults] = React.useState([]);
  const [results, setResults] = React.useState(null);
  const [customSchemes, setCustomSchemes] = React.useState([]);
  const [history, setHistory] = React.useState(null);
  const [historyView, setHistoryView] = React.useState("trend"); // "trend" | "range" | "diff"
  const [diffRefId, setDiffRefId] = React.useState("sp500");
  const [computing, setComputing] = React.useState(false);
  const [crudLoading, setCrudLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [localEnabled, setLocalEnabled] = React.useState(null); // null = all defaults on
  const [editingCustomId, setEditingCustomId] = React.useState(null);
  const [addingCustom, setAddingCustom] = React.useState(false);
  const today = new Date().toISOString().slice(0, 10);

  React.useEffect(() => {
    let cancelled = false;
    const init = async () => {
      try {
        const [defs, res, customs] = await Promise.all([
          apiGetBenchmarkDefaults(),
          apiGetBenchmarkResults(account.id),
          apiGetCustomSchemes(account.id),
        ]);
        if (cancelled) return;
        setDefaults(defs);
        setCustomSchemes(customs);
        const stored = account.benchmark_schemes;
        const storedEnabled = stored ? (stored.enabled_defaults ?? null) : null;
        setLocalEnabled(storedEnabled);

        // Recompute if: no result today, OR any enabled default/custom scheme is missing
        const enabledIds = storedEnabled === null ? new Set(defs.map(d => d.id)) : new Set(storedEnabled);
        customs.forEach(cs => { if (cs.enabled !== 0) enabledIds.add(String(cs.id)); });
        const computedIds = new Set((res.schemes || []).map(s => s.id));
        const missingScheme = [...enabledIds].some(id => !computedIds.has(id));

        if (!res.computed_date || res.computed_date !== today || missingScheme) {
          setComputing(true);
          const computed = await apiComputeBenchmark(account.id);
          const h = await apiGetBenchmarkHistory(account.id);
          if (!cancelled) { setResults(computed); setHistory(h); setComputing(false); }
        } else {
          setResults(res);
          const h = await apiGetBenchmarkHistory(account.id);
          if (!cancelled) setHistory(h);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      }
    };
    init();
    return () => { cancelled = true; };
  }, [account.id]);

  // Active bench IDs for bar chart + history display
  const activeIds = React.useMemo(() => {
    const ids = localEnabled === null ? new Set(defaults.map(d => d.id)) : new Set(localEnabled);
    customSchemes.forEach(cs => { if (cs.enabled !== 0) ids.add(String(cs.id)); });
    return ids;
  }, [localEnabled, defaults, customSchemes]);

  // Localized name for a default scheme — falls back to d.name if no i18n key exists
  const _defLabel = (d) => {
    const key = `benchmark.default.${d.id}.name`;
    const v = I18N.t(key);
    return v !== key ? v : d.name;
  };
  const defById = React.useMemo(() => {
    const m = {};
    defaults.forEach(d => { m[d.id] = d; });
    return m;
  }, [defaults]);
  const _schemeLabel = (id, fallback) => {
    const d = defById[id];
    return d ? _defLabel(d) : fallback;
  };

  const toggleDefault = async (id) => {
    const current = localEnabled === null ? defaults.map(d => d.id) : [...localEnabled];
    const next = current.includes(id) ? current.filter(i => i !== id) : [...current, id];
    setLocalEnabled(next);
    setComputing(true);
    try {
      await apiUpdateBenchmarkSchemes(account.id, { enabled_defaults: next });
      const computed = await apiComputeBenchmark(account.id);
      const h = await apiGetBenchmarkHistory(account.id);
      setResults(computed);
      setHistory(h);
      if (onAccountUpdated) onAccountUpdated();
    } catch (err) {
      setError(err.message);
    } finally {
      setComputing(false);
    }
  };

  const _reloadAfterCRUD = async () => {
    setComputing(true);
    const [customs, computed] = await Promise.all([
      apiGetCustomSchemes(account.id),
      apiComputeBenchmark(account.id),
    ]);
    const h = await apiGetBenchmarkHistory(account.id);
    setCustomSchemes(customs);
    setResults(computed);
    setHistory(h);
    setComputing(false);
  };

  const handleSaveCustom = async (schemeData) => {
    setCrudLoading(true);
    try {
      if (editingCustomId !== null) {
        await apiUpdateCustomScheme(account.id, editingCustomId, schemeData);
      } else {
        await apiCreateCustomScheme(account.id, schemeData);
      }
      setEditingCustomId(null);
      setAddingCustom(false);
      await _reloadAfterCRUD();
    } catch (err) {
      setError(err.message);
    } finally {
      setCrudLoading(false);
    }
  };

  const handleToggleCustomEnabled = async (id, currentEnabled) => {
    setCrudLoading(true);
    try {
      await apiSetCustomSchemeEnabled(account.id, id, !currentEnabled);
      await _reloadAfterCRUD();
    } catch (err) {
      setError(err.message);
    } finally {
      setCrudLoading(false);
    }
  };

  const _fmtSchemeDesc = (allocations, cashPct) => {
    const parts = (allocations || []).map(a => `${a.symbol} ${a.pct}%`);
    if (cashPct > 0) parts.push(`Cash ${cashPct}%`);
    return parts.join(' · ');
  };

  const _fmtUSD = (v) => {
    if (v == null) return null;
    let s;
    if (v >= 1e6) s = `$${(v / 1e6).toFixed(1)}M`;
    else if (v >= 1e3) s = `$${Math.round(v / 1e3)}k`;
    else s = `$${Math.round(v)}`;
    return maskDigits(s);
  };

  const chartData = React.useMemo(() => {
    const portfolioLabel = I18N.t("benchmark.return.portfolio");
    if (results?.schemes) {
      // Sort: defaults in config order first, then customs
      const defaultOrder = new Map(defaults.map((d, i) => [d.id, i]));
      const sorted = [...results.schemes].sort((a, b) => {
        const aIdx = defaultOrder.has(a.id) ? defaultOrder.get(a.id) : 999;
        const bIdx = defaultOrder.has(b.id) ? defaultOrder.get(b.id) : 999;
        return aIdx - bIdx;
      });
      const visible = sorted.filter(s => activeIds.has(s.id));
      const allLabels = [portfolioLabel, ...visible.map(s => _schemeLabel(s.id, s.name))];
      const cmap = nameColors(allLabels);
      const data = [{
        label: portfolioLabel,
        value: results?.portfolio_xirr ?? null,
        topLabel: _fmtUSD(results?.portfolio_value_usd),
        color: cmap[portfolioLabel],
      }];
      visible.forEach(s => {
        const label = _schemeLabel(s.id, s.name);
        data.push({ label, value: s.xirr, topLabel: _fmtUSD(s.current_value_usd), color: cmap[label] });
      });
      return data;
    }
    return [{ label: portfolioLabel, value: results?.portfolio_xirr ?? null, topLabel: _fmtUSD(results?.portfolio_value_usd), color: nameColor(portfolioLabel) }];
  }, [results, defaults, activeIds, PRIVACY.masked]);

  // Shared dedup color map — same colors in bar chart and line chart
  const sharedColorMap = React.useMemo(
    () => nameColors(chartData.map(d => d.label)),
    [chartData]
  );

  const getXIRR = (id) => results?.schemes?.find(s => s.id === id)?.xirr ?? null;
  const fmtPct = (v) => v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
  const isNonUSD = account.currency && account.currency !== "USD";

  // Delta series for the "diff" tab — XIRR relative to a reference scheme
  const _diffData = React.useMemo(() => {
    if (!history || !history.series.length) return { series: [], ref: null, options: [] };
    const portfolioLabel = I18N.t("benchmark.return.portfolio");
    const allSeries = history.series
      .filter(s => s.id === "__portfolio__" || activeIds.has(s.id))
      .map(s => ({ ...s, name: s.id === "__portfolio__" ? portfolioLabel : _schemeLabel(s.id, s.name) }));
    const options = allSeries.map(s => ({ id: s.id, name: s.name }));
    const refId = allSeries.some(s => s.id === diffRefId) ? diffRefId
      : (allSeries.find(s => s.id === "sp500") || allSeries[0])?.id;
    const refSeries = allSeries.find(s => s.id === refId);
    if (!refSeries) return { series: [], ref: null, options };
    const refMap = {};
    refSeries.data.forEach(d => { if (d.xirr != null) refMap[d.date] = d.xirr; });
    const deltaSeries = allSeries
      .filter(s => s.id !== refId)
      .map(s => ({
        ...s,
        data: s.data
          .filter(d => d.xirr != null && refMap[d.date] != null)
          .map(d => ({ date: d.date, xirr: d.xirr - refMap[d.date] })),
      }))
      .filter(s => s.data.length > 0);
    return { series: deltaSeries, ref: refSeries, options };
  }, [history, diffRefId, activeIds]);

  const _diffStats = React.useMemo(() =>
    _diffData.series.map(s => {
      const diffs = s.data;
      if (!diffs.length) return null;
      const beatCount = diffs.filter(d => d.xirr > 0).length;
      const maxD = diffs.reduce((a, b) => b.xirr > a.xirr ? b : a);
      const minD = diffs.reduce((a, b) => b.xirr < a.xirr ? b : a);
      return { id: s.id, name: s.name, beatPct: beatCount / diffs.length * 100,
        beatDays: beatCount, totalDays: diffs.length,
        maxDiff: maxD.xirr, maxDate: maxD.date, minDiff: minD.xirr, minDate: minD.date };
    }).filter(Boolean),
  [_diffData]);

  if (error) return <Empty text={I18N.t("benchmark.error")}/>;

  return (
    <div style={{ paddingBottom: 24 }}>
      {computing && (
        <div style={{ textAlign: "center", padding: "32px 0", color: "var(--ink-3)", fontSize: 13 }}>
          <div style={{ fontSize: 22, marginBottom: 8 }}>⏳</div>
          {I18N.t("benchmark.computing")}
        </div>
      )}

      {!computing && results && (
        <>
          {/* Bar chart — current snapshot */}
          <div style={{ marginBottom: 4, display: "flex", alignItems: "baseline", gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em" }}>
              {I18N.t("benchmark.chart.title")}
            </span>
            {results?.computed_date && (
              <span style={{ fontSize: 10, color: "var(--ink-4)" }}>
                {I18N.tf("benchmark.chart.asOf", { date: results.computed_date })}
              </span>
            )}
          </div>
          <div style={{ overflowX: "auto", marginBottom: 16 }}>
            <BarChart data={chartData} signed={true} width={Math.max(chartData.length * 90 + 60, 400)} height={160}/>
          </div>

          {/* History charts — Trend line + XIRR Range */}
          {history && history.series.length > 0 && (() => {
            const visibleSeries = history.series
              .filter(s => s.id === "__portfolio__" || activeIds.has(s.id))
              .map(s => s.id === "__portfolio__"
                ? { ...s, name: I18N.t("benchmark.return.portfolio") }
                : { ...s, name: _schemeLabel(s.id, s.name) });
            // currentMap: name → current XIRR for range chart dots
            const currentMap = {};
            chartData.forEach(d => { if (d.value != null) currentMap[d.label] = d.value; });
            const hasEnoughForRange = visibleSeries.some(s => s.data.length >= 2);
            return (
              <div style={{ marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em" }}>
                    {I18N.t("benchmark.history.title")}
                  </span>
                  {hasEnoughForRange && (
                    <Tabs variant="pill" value={historyView} onChange={setHistoryView}
                      tabs={[
                        { id: "trend",  label: I18N.t("benchmark.history.tab.trend") },
                        { id: "range",  label: I18N.t("benchmark.history.tab.range") },
                        { id: "diff",   label: I18N.t("benchmark.history.tab.diff") },
                      ]}/>
                  )}
                </div>
                <div style={{ overflowX: "auto" }}>
                  {historyView === "trend" && (
                    <MultiLineChart
                      series={visibleSeries}
                      granularity={history.granularity} width={560} height={320} colorMap={sharedColorMap}/>
                  )}
                  {historyView === "range" && (
                    <XirrRangeChart
                      series={visibleSeries}
                      currentMap={currentMap}
                      colorMap={sharedColorMap}
                      width={560}/>
                  )}
                  {historyView === "diff" && (() => {
                    const { series: ds, ref: refS, options: refOpts } = _diffData;
                    const diffColorMap = nameColors(ds.map(s => s.name));
                    return (
                      <div>
                        {/* Reference selector */}
                        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                          <span style={{ fontSize: 11, color: "var(--ink-3)" }}>{I18N.t("benchmark.diff.ref")}:</span>
                          <select value={diffRefId} onChange={e => setDiffRefId(e.target.value)} autoComplete="off"
                            style={{ fontSize: 11, padding: "3px 6px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)", cursor: "pointer" }}>
                            {refOpts.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}
                          </select>
                        </div>
                        {ds.length > 0 ? (<>
                          <MultiLineChart series={ds} granularity={history.granularity} width={560} height={240} colorMap={diffColorMap}/>
                          {/* Stats table */}
                          <div style={{ marginTop: 14, display: "inline-block", minWidth: 460 }}>
                            <div style={{ display: "grid", gridTemplateColumns: "180px 110px 140px 140px", gap: 6, padding: "4px 0", borderBottom: "1px solid var(--line)", fontSize: 10.5, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em" }}>
                              <span>{I18N.t("benchmark.diff.scheme")}</span>
                              <span style={{ textAlign: "right" }}>{I18N.t("benchmark.diff.beat")}</span>
                              <span style={{ textAlign: "right" }}>{I18N.t("benchmark.diff.maxOut")}</span>
                              <span style={{ textAlign: "right" }}>{I18N.t("benchmark.diff.maxLag")}</span>
                            </div>
                            {_diffStats.map(st => (
                              <div key={st.id} style={{ display: "grid", gridTemplateColumns: "180px 110px 140px 140px", gap: 6, padding: "7px 0", borderBottom: "1px solid var(--line)", fontSize: 12, alignItems: "center" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                                  <div style={{ width: 8, height: 8, borderRadius: "50%", background: diffColorMap[st.name] || nameColor(st.name), flexShrink: 0 }}/>
                                  <span>{st.name}</span>
                                </div>
                                <span className="mono" style={{ textAlign: "right", color: st.beatPct >= 50 ? "var(--up)" : "var(--down)", fontWeight: 600 }}>
                                  {st.beatPct.toFixed(0)}%
                                  <span style={{ fontSize: 10, color: "var(--ink-4)", fontWeight: 400, marginLeft: 3 }}>({st.beatDays}/{st.totalDays})</span>
                                </span>
                                <div style={{ textAlign: "right" }}>
                                  <span className="mono" style={{ color: "var(--up)", fontWeight: 600 }}>+{st.maxDiff.toFixed(1)}pp</span>
                                  <div style={{ fontSize: 10, color: "var(--ink-4)" }}>{st.maxDate}</div>
                                </div>
                                <div style={{ textAlign: "right" }}>
                                  <span className="mono" style={{ color: "var(--down)", fontWeight: 600 }}>{st.minDiff.toFixed(1)}pp</span>
                                  <div style={{ fontSize: 10, color: "var(--ink-4)" }}>{st.minDate}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        </>) : (
                          <div style={{ color: "var(--ink-4)", fontSize: 12, padding: "16px 0" }}>{I18N.t("benchmark.diff.noData")}</div>
                        )}
                      </div>
                    );
                  })()}
                </div>
              </div>
            );
          })()}

          {/* Warnings */}
          {results.excluded_deposits > 0 && (
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 10, background: "var(--paper-2)", borderRadius: 6, padding: "6px 10px" }}>
              ⚠ {I18N.t("benchmark.excludedDeposits").replace("{n}", results.excluded_deposits)}
            </div>
          )}
          {isNonUSD && (
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 14, background: "var(--paper-2)", borderRadius: 6, padding: "6px 10px" }}>
              ℹ {I18N.t("benchmark.disclaimer")}
            </div>
          )}
        </>
      )}

      {!computing && !results && (
        <div style={{ color: "var(--ink-4)", fontSize: 13, padding: "16px 0" }}>{I18N.t("benchmark.noDeposits")}</div>
      )}

      {/* Scheme table — defaults + customs share the same row layout */}
      {(defaults.length > 0 || customSchemes.length > 0 || true) && (() => {
        const rowStyle = { display: "flex", alignItems: "center", gap: 10, padding: "6px 0", borderBottom: "1px solid var(--line)" };
        const xirrStyle = { fontSize: 13, fontWeight: 600, fontFamily: "monospace", width: 58, textAlign: "right", flexShrink: 0 };
        const sectionHead = (label, hint) => (
          <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 4, marginTop: 16 }}>
            {label}{hint && <span style={{ fontWeight: 400, marginLeft: 8, color: "var(--ink-4)" }}>{hint}</span>}
          </div>
        );
        return (
          <div style={{ marginBottom: 20 }}>
            {/* Default schemes */}
            {defaults.length > 0 && (
              <>
                {sectionHead(I18N.t("benchmark.defaults.title"), I18N.t("benchmark.defaults.hint"))}
                {defaults.map(d => {
                  const xirr = getXIRR(d.id);
                  const active = activeIds.has(d.id);
                  const label = _defLabel(d);
                  return (
                    <div key={d.id} style={rowStyle}>
                      <div style={{ width: 8, height: 8, borderRadius: 2, background: sharedColorMap[label] || nameColor(label), flexShrink: 0 }}/>
                      <div style={{ minWidth: 0, maxWidth: 220, overflow: "hidden" }}>
                        <div style={{ fontSize: 13, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{label}</div>
                        {d.description && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{d.description}</div>}
                      </div>
                      <span style={{ ...xirrStyle, color: active && xirr != null ? (xirr >= 0 ? "var(--up)" : "var(--down)") : "var(--ink-4)" }}>
                        {active ? fmtPct(xirr) : "—"}
                      </span>
                      <Toggle value={active} onChange={() => toggleDefault(d.id)} size="sm" disabled={computing || crudLoading}/>
                    </div>
                  );
                })}
              </>
            )}

            {/* Custom schemes */}
            {sectionHead(I18N.t("benchmark.custom.title"))}
            {customSchemes.map(cs => {
              const csEnabled = cs.enabled !== 0;
              const xirr = csEnabled ? getXIRR(String(cs.id)) : null;
              const desc = _fmtSchemeDesc(cs.allocations, cs.cash_pct);
              return (
                <div key={cs.id}>
                  <div style={{ ...rowStyle, opacity: csEnabled ? 1 : 0.45 }}>
                    <div style={{ width: 8, height: 8, borderRadius: 2, background: sharedColorMap[cs.name] || nameColor(cs.name), flexShrink: 0 }}/>
                    <div style={{ minWidth: 0, maxWidth: 220, overflow: "hidden" }}>
                      <div style={{ fontSize: 13, color: "var(--ink)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{cs.name}</div>
                      {desc && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{desc}</div>}
                    </div>
                    <span style={{ ...xirrStyle, color: csEnabled && xirr != null ? (xirr >= 0 ? "var(--up)" : "var(--down)") : "var(--ink-4)" }}>
                      {csEnabled ? fmtPct(xirr) : "—"}
                    </span>
                    <button type="button" onClick={() => { setEditingCustomId(cs.id); setAddingCustom(false); }}
                      disabled={crudLoading}
                      style={{ fontSize: 12, color: "var(--ink-3)", border: "1px solid var(--line)", borderRadius: 5, background: "none", padding: "2px 8px", cursor: crudLoading ? "default" : "pointer", flexShrink: 0 }}>
                      {I18N.t("benchmark.custom.edit")}
                    </button>
                    <Toggle value={csEnabled} onChange={() => handleToggleCustomEnabled(cs.id, csEnabled)} size="sm" disabled={crudLoading}/>
                  </div>
                  {editingCustomId === cs.id && (
                    <CustomSchemeEditor scheme={cs} onSave={handleSaveCustom} onCancel={() => setEditingCustomId(null)}/>
                  )}
                </div>
              );
            })}
            {addingCustom && (
              <CustomSchemeEditor scheme={null} onSave={handleSaveCustom} onCancel={() => setAddingCustom(false)}/>
            )}
            {!addingCustom && (
              <button type="button" onClick={() => { setAddingCustom(true); setEditingCustomId(null); }}
                style={{ marginTop: 8, fontSize: 12, color: "var(--ink-3)", border: "1px dashed var(--line-2)", borderRadius: 6, background: "none", padding: "4px 12px", cursor: "pointer" }}>
                {I18N.t("benchmark.custom.add")}
              </button>
            )}
          </div>
        );
      })()}

    </div>
  );
};

const _ADV_KEY = "fin_acct_adv";
const _getAdv = () => localStorage.getItem(_ADV_KEY) === "1";
const _setAdv = (v) => localStorage.setItem(_ADV_KEY, v ? "1" : "0");

const AccountModal = ({ onClose, onSaved }) => {
  const [form, set] = useForm({ name: "", currency: "CNY", note: "", cutoff_date: "", benchmark_enabled: false });
  const [advOpen, setAdvOpen] = React.useState(_getAdv);
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setErr(I18N.t("holdings.acct.nameEmpty")); return; }
    setSaving(true); setErr(null);
    try {
      const saved = await apiCreateAccount({
        name: form.name.trim(), currency: form.currency,
        note: form.note || null,
        cutoff_date: form.cutoff_date.trim() || null,
        benchmark_enabled: form.benchmark_enabled,
      });
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };
  return (
    <Modal open={true} onClose={onClose} title={I18N.t("holdings.acct.new.title")} width={400}>
      <form onSubmit={submit} autoComplete="off" style={{ padding: "18px 20px" }}>
        <FormRow label={I18N.t("holdings.acct.new.name")}><Input value={form.name} onChange={v => set("name", v)} placeholder="IBKR / Questrade / Wealthsimple"/></FormRow>
        <FormRow label={I18N.t("holdings.acct.new.currency")}>
          <Select value={form.currency} onChange={v => set("currency", v)} options={CURRENCY_OPTIONS()}/>
        </FormRow>
        <FormRow label={I18N.t("holdings.acct.new.note")}><Input value={form.note} onChange={v => set("note", v)} placeholder={`(${I18N.t("base.label.optional")})`}/></FormRow>
        <div style={{ marginBottom: 14 }}>
          <button type="button" onClick={() => setAdvOpen(v => { _setAdv(!v); return !v; })}
            style={{ background: "none", border: "none", padding: "4px 0", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, width: "100%" }}>
            <span style={{ fontSize: 8, display: "inline-block", transform: advOpen ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▶</span>
            {I18N.t("holdings.acct.advanced")}
          </button>
          {advOpen && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6 }}>
                {I18N.t("holdings.acct.new.cutoff")}
              </div>
              <DateInput value={form.cutoff_date} onChange={v => set("cutoff_date", v)} style={{ marginBottom: 6 }}/>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 14, lineHeight: 1.5 }}>
                {I18N.t("holdings.acct.cutoff.hint")}
              </div>
              <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                <Toggle value={form.benchmark_enabled} onChange={v => set("benchmark_enabled", v)} size="sm"/>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)", lineHeight: 1.3 }}>{I18N.t("benchmark.acct.toggle")}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2, lineHeight: 1.5 }}>{I18N.t("benchmark.acct.toggleHint")}</div>
                </div>
              </div>
            </div>
          )}
        </div>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? I18N.t("holdings.acct.new.creating") : I18N.t("holdings.acct.new.create")}</Button>
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
    benchmark_enabled: !!account.benchmark_enabled,
  });
  const [advOpen, setAdvOpen] = React.useState(() => {
    const stored = localStorage.getItem(_ADV_KEY);
    return stored !== null ? stored === "1" : !!account.cutoff_date || !!Object.keys(account.symbol_markets || {}).length || !!account.benchmark_enabled;
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
    if (!form.name.trim()) { setErr(I18N.t("holdings.acct.nameEmpty")); return; }
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
        benchmark_enabled: form.benchmark_enabled,
      });
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={`${I18N.t("holdings.acct.edit.title")} · ${account.name}`} width={420}>
      <form onSubmit={submit} autoComplete="off" style={{ padding: "18px 20px" }}>
        <FormRow label={I18N.t("holdings.acct.edit.name")}><Input value={form.name} onChange={v => set("name", v)} placeholder="IBKR"/></FormRow>
        <FormRow label={I18N.t("holdings.acct.edit.currency")}>
          <Select value={form.currency} onChange={v => set("currency", v)} options={CURRENCY_OPTIONS()}/>
        </FormRow>
        <FormRow label={I18N.t("holdings.acct.edit.balAcct")}>
          <Select value={form.balance_account_id} onChange={v => { set("balance_account_id", v); set("balance_sub_account_id", ""); }}
            options={[{ value: "", label: I18N.t("holdings.acct.noSelect") }, ...balParents.map(a => ({ value: String(a.id), label: a.name }))]}/>
        </FormRow>
        <FormRow label={I18N.t("holdings.acct.edit.balSub")}>
          <Select value={form.balance_sub_account_id} onChange={v => set("balance_sub_account_id", v)}
            options={[{ value: "", label: I18N.t("holdings.acct.noSelect") }, ...balSubs.map(a => ({ value: String(a.id), label: a.name }))]}
            style={{ opacity: balSubs.length === 0 ? 0.5 : 1, pointerEvents: balSubs.length === 0 ? "none" : "auto" }}/>
        </FormRow>
        <div style={{ fontSize: 11, color: "var(--ink-4)", margin: "-8px 0 12px 98px", lineHeight: 1.5 }}>
          {I18N.t("holdings.acct.edit.balLink.hint")}
        </div>
        <FormRow label={I18N.t("holdings.acct.edit.note")}><Input value={form.note} onChange={v => set("note", v)} placeholder={`(${I18N.t("base.label.optional")})`}/></FormRow>

        <div style={{ marginBottom: 14 }}>
          <button type="button" onClick={() => setAdvOpen(v => { _setAdv(!v); return !v; })}
            style={{ background: "none", border: "none", padding: "4px 0", fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, width: "100%" }}>
            <span style={{ fontSize: 8, display: "inline-block", transform: advOpen ? "rotate(90deg)" : "none", transition: "transform .15s" }}>▶</span>
            {I18N.t("holdings.acct.advanced")}
          </button>
          {advOpen && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6 }}>
                {I18N.t("holdings.acct.edit.cutoff")}
              </div>
              <DateInput value={form.cutoff_date} onChange={v => set("cutoff_date", v)} style={{ marginBottom: 6 }}/>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 14, lineHeight: 1.5 }}>
                {I18N.t("holdings.acct.cutoff.hint")}
              </div>
              <div style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 8 }}>
                {I18N.t("holdings.acct.edit.marketOverride")}
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 8, lineHeight: 1.5 }}>
                {I18N.t("holdings.acct.edit.marketOverride.hint")}
              </div>
              {smRows.length > 0 && (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 120px 28px", gap: 6, marginBottom: 6 }}>
                  {smRows.map((r, i) => (
                    <React.Fragment key={i}>
                      <input value={r.code} onChange={e => setSmRows(rows => rows.map((x, j) => j === i ? { ...x, code: e.target.value } : x))}
                        placeholder="symbol" autoComplete="off"
                        style={{ fontSize: 13, padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)" }}/>
                      <select value={r.market} onChange={e => setSmRows(rows => rows.map((x, j) => j === i ? { ...x, market: e.target.value } : x))}
                        style={{ fontSize: 13, padding: "5px 8px", border: "1px solid var(--line)", borderRadius: 6, background: "var(--paper)", color: "var(--ink)" }}>
                        <option value="US">{I18N.t("base.market.us")}</option>
                        <option value="HK">{I18N.t("base.market.hk")}</option>
                        <option value="CN">{I18N.t("base.market.cn")}</option>
                        <option value="CA">{I18N.t("base.market.ca")}</option>
                        <option value="CRYPTO">{I18N.t("base.market.crypto")}</option>
                      </select>
                      <button type="button" onClick={() => setSmRows(rows => rows.filter((_, j) => j !== i))}
                        style={{ border: "none", background: "none", color: "var(--ink-4)", cursor: "pointer", fontSize: 15, padding: 0 }}>✕</button>
                    </React.Fragment>
                  ))}
                </div>
              )}
              <button type="button" onClick={() => setSmRows(rows => [...rows, { code: "", market: "HK" }])}
                style={{ fontSize: 12, color: "var(--ink-3)", border: "1px dashed var(--line-2)", borderRadius: 6, background: "none", padding: "4px 10px", cursor: "pointer" }}>
                {I18N.t("holdings.acct.edit.addMapping")}
              </button>
              <div style={{ marginTop: 16, display: "flex", alignItems: "flex-start", gap: 10 }}>
                <Toggle value={form.benchmark_enabled} onChange={v => set("benchmark_enabled", v)} size="sm"/>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)", lineHeight: 1.3 }}>{I18N.t("benchmark.acct.toggle")}</div>
                  <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2, lineHeight: 1.5 }}>{I18N.t("benchmark.acct.toggleHint")}</div>
                </div>
              </div>
            </div>
          )}
        </div>

        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? I18N.t("holdings.acct.edit.saving") : I18N.t("base.btn.save")}</Button>
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
      { value: "", label: I18N.t("holdings.acct.noSelect") },
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
  const initDate = editing?.snapshot_name || today;
  const [isCash, setIsCash] = React.useState(editing?.code === "CASH");
  const [form, set, setForm] = useForm({
    code: initCode,
    market: initMarket,
    currency: editing?.currency || MARKET_CCY[initMarket],
    account: editing?.account || defaultAccount || "",
    snapshot_name: initDate,
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
      if (!form.shares || parseFloat(form.shares) <= 0) { setErr(I18N.t("balance.item.amountInvalid")); return; }
    } else {
      if (!form.code.trim())                            { setErr(I18N.t("holdings.txn.symbol").replace(" *","") + " required"); return; }
      if (!form.shares || parseFloat(form.shares) <= 0) { setErr(I18N.t("holdings.holding.shares").replace(" *","") + " > 0"); return; }
      if (form.avg_cost === "" || parseFloat(form.avg_cost) < 0) { setErr(I18N.t("holdings.holding.avgCost").replace(" *","") + " required"); return; }
    }
    if (!form.snapshot_name.trim()) { setErr(I18N.t("holdings.holding.snapDate").replace(" *","") + " required"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        shares: parseFloat(form.shares),
        avg_cost: isCash ? 1 : parseFloat(form.avg_cost),
        account: form.account || null,
      };
      const isVirtual = editing && String(editing.id).startsWith("virtual_");
      const saved = (editing && !isVirtual) ? await apiUpdateHolding(editing.id, payload) : await apiCreateHolding(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? I18N.t("holdings.holding.edit.title") : I18N.t("holdings.holding.add.title")} width={440}>
      <form onSubmit={submit} autoComplete="off" style={{ padding: "18px 20px" }}>
        <FormRow label={I18N.t("holdings.holding.account")}>
          {!editing && defaultAccount
            ? <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", padding: "7px 0" }}>{form.account}</div>
            : <AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/>}
        </FormRow>
        <FormRow label={I18N.t("holdings.holding.type")}>
          <Tabs variant="pill" value={isCash ? "cash" : "stock"} onChange={v => toggleCash(v === "cash")}
            tabs={[{id:"stock",label:I18N.t("holdings.holding.type.stock")},{id:"cash",label:I18N.t("holdings.holding.type.cash")}]}/>
        </FormRow>
        {isCash ? (
          <>
            <FormRow label={I18N.t("holdings.holding.currency")}>
              <Select value={form.currency} onChange={setCashCurrency}
                options={CURRENCY_OPTIONS()}/>
            </FormRow>
            <FormRow label={I18N.t("holdings.holding.amount")}><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="10000" suffix={form.currency}/></FormRow>
          </>
        ) : (
          <>
            <FormRow label={I18N.t("holdings.holding.code")}>
              <SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA"/>
              {/^\d{6}$/.test(form.code) && <div style={{fontSize:11,color:"var(--ink-3)",marginTop:3}}>{I18N.t("holdings.holding.fundCode.hint")}</div>}
            </FormRow>
            <FormRow label={I18N.t("holdings.holding.market")}>
              <Select value={form.market} onChange={setMarket} options={[{value:"US",label:I18N.t("base.market.us")},{value:"HK",label:I18N.t("base.market.hk")},{value:"CN",label:I18N.t("base.market.cn")},{value:"CA",label:I18N.t("base.market.ca")},{value:"CRYPTO",label:I18N.t("base.market.crypto")}]}/>
            </FormRow>
            <FormRow label={I18N.t("holdings.holding.shares")}><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="100"/></FormRow>
            <FormRow label={I18N.t("holdings.holding.avgCost")}><Input value={form.avg_cost} onChange={v => set("avg_cost", v)} inputMode="decimal" placeholder="120.00" suffix={form.currency}/></FormRow>
          </>
        )}
        <FormRow label={I18N.t("holdings.holding.snapDate")}><DateInput value={form.snapshot_name} onChange={v => set("snapshot_name", v)}/></FormRow>
        <FormRow label={I18N.t("holdings.holding.note")}><Input value={form.note} onChange={v => set("note", v)} placeholder={`(${I18N.t("base.label.optional")})`}/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? I18N.t("base.btn.saving") : I18N.t("base.btn.save")}</Button>
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
    realized: editing?.realized ?? "",
    note: editing?.note || "",
  });
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);
  const [realizedUnknown, setRealizedUnknown] = React.useState(editing ? editing.realized == null && editing.side === "sell" : false);

  const setCode = (sym) => {
    const c = (typeof sym === "string" ? sym : sym.code || "").toUpperCase();
    set("code", c);
    set("currency", (typeof sym === "object" && sym.currency) || ccyFromCode(c));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.date.trim())                            { setErr(I18N.t("holdings.txn.date").replace(" *","") + " required"); return; }
    if (!form.code.trim())                            { setErr(I18N.t("holdings.txn.symbol").replace(" *","") + " required"); return; }
    if (!form.shares || parseFloat(form.shares) <= 0) { setErr(I18N.t("holdings.txn.shares").replace(" *","") + " > 0"); return; }
    if (form.price === "" || parseFloat(form.price) < 0) { setErr(I18N.t("holdings.txn.price").replace(" *","") + " required"); return; }
    const realizedStr = String(form.realized).trim();
    if (form.side === "sell" && !realizedUnknown && realizedStr === "") { setErr(I18N.t("holdings.txn.realized") + " required on sell"); return; }
    if (realizedStr !== "" && Number.isNaN(parseFloat(realizedStr))) { setErr(I18N.t("holdings.txn.realized") + " must be a number"); return; }
    setSaving(true); setErr(null);
    try {
      const payload = {
        ...form,
        code: form.code.toUpperCase(),
        shares: parseFloat(form.shares),
        price: parseFloat(form.price),
        account: form.account || null,
        realized: realizedStr === "" ? null : parseFloat(realizedStr),
        realized_unknown: form.side === "sell" && realizedUnknown,
      };
      const saved = editing ? await apiUpdateTransaction(editing.id, payload) : await apiCreateTransaction(payload);
      onSaved(saved);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={editing ? I18N.t("holdings.txn.edit.title") : I18N.t("holdings.txn.add.title")} width={440}>
      <form onSubmit={submit} autoComplete="off" style={{ padding: "18px 20px" }}>
        <FormRow label={I18N.t("holdings.txn.account")}>
          {!editing && defaultAccount
            ? <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", padding: "7px 0" }}>{form.account}</div>
            : <AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/>}
        </FormRow>
        <FormRow label={I18N.t("holdings.txn.date")}><DateInput value={form.date} onChange={v => set("date", v)}/></FormRow>
        <FormRow label={I18N.t("holdings.txn.side")}>
          <Select value={form.side} onChange={v => set("side", v)} options={[{value:"buy",label:I18N.t("holdings.txn.side.buy")},{value:"sell",label:I18N.t("holdings.txn.side.sell")}]}/>
        </FormRow>
        <FormRow label={I18N.t("holdings.txn.symbol")}><SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA"/></FormRow>
        <FormRow label={I18N.t("holdings.txn.shares")}><Input value={form.shares} onChange={v => set("shares", v)} inputMode="decimal" placeholder="100"/></FormRow>
        <FormRow label={I18N.t("holdings.txn.price")}><Input value={form.price} onChange={v => set("price", v)} inputMode="decimal" placeholder="120.00" suffix={form.currency}/></FormRow>
        {form.side === "sell" && (
          <FormRow label={I18N.t("holdings.txn.realized") + (!realizedUnknown ? " *" : "")}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <Input value={realizedUnknown ? "" : form.realized} onChange={v => set("realized", v)} inputMode="decimal" placeholder={I18N.t("holdings.txn.realized.ph.sell")} suffix={form.currency} disabled={realizedUnknown}/>
              <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--ink-3)", cursor: "pointer", userSelect: "none" }}>
                <input type="checkbox" checked={realizedUnknown} onChange={e => { setRealizedUnknown(e.target.checked); if (e.target.checked) set("realized", ""); }} style={{ cursor: "pointer", margin: 0 }}/>
                {I18N.t("holdings.txn.realized.unknown")}
                {realizedUnknown && <span style={{ color: "var(--ink-4)" }}>— {I18N.t("holdings.txn.realized.unknown.warn")}</span>}
              </label>
            </div>
          </FormRow>
        )}
        <FormRow label={I18N.t("holdings.txn.note")}><Input value={form.note} onChange={v => set("note", v)} placeholder={`(${I18N.t("base.label.optional")})`}/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? I18N.t("base.btn.saving") : I18N.t("base.btn.save")}</Button>
        </div>
      </form>
    </Modal>
  );
};

const IncomeModal = ({ editing, accounts, defaultAccount, defaultCategory = "dividend", allowedCategories = null, onClose, onSaved }) => {
  const today = new Date().toISOString().slice(0, 10);
  const ccyFromCode = (code) => {
    const sym = SYMBOL_INDEX[(code || "").toUpperCase()];
    return sym ? (MARKET_CCY[sym.market] || "USD") : "USD";
  };
  const catLabels = { dividend: I18N.t("holdings.income.cat.dividend"), interest: I18N.t("holdings.income.cat.interest"), option: I18N.t("holdings.income.cat.option"), deposit: I18N.t("holdings.income.cat.deposit"), withdrawal: I18N.t("holdings.income.cat.withdrawal") };
  const ccyOptions = CURRENCY_OPTIONS();
  const acctCcy = accounts.find(a => a.name === (editing?.account || defaultAccount))?.currency || null;

  const [form, set] = useForm({
    date: editing?.date || today,
    code: editing?.code || "",
    source: editing?.source || "",
    category: editing?.category || defaultCategory,
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
    if (!form.date.trim())                            { setErr(I18N.t("holdings.income.date").replace(" *","") + " required"); return; }
    if (!form.source.trim())                          { setErr(I18N.t("holdings.income.source").replace(" *","") + " required"); return; }
    if (!form.amount || parseFloat(form.amount) <= 0) { setErr(I18N.t("balance.item.amountInvalid")); return; }
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
    <Modal open={true} onClose={onClose} title={editing ? I18N.t("holdings.income.edit.title") : I18N.t("holdings.income.add.title")} width={440}>
      <form onSubmit={submit} autoComplete="off" style={{ padding: "18px 20px" }}>
        <FormRow label={I18N.t("holdings.income.account")}>
          {!editing && defaultAccount
            ? <div style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-2)", padding: "7px 0" }}>{form.account}</div>
            : <AccountSelect accounts={accounts} value={form.account} onChange={v => set("account", v)}/>}
        </FormRow>
        <FormRow label={I18N.t("holdings.income.date")}><DateInput value={form.date} onChange={v => set("date", v)}/></FormRow>
        <FormRow label={I18N.t("holdings.income.type")}>
          <Select value={form.category} onChange={v => set("category", v)} options={Object.entries(catLabels).filter(([value]) => !allowedCategories || allowedCategories.includes(value)).map(([value,label]) => ({value,label}))}/>
        </FormRow>
        <FormRow label={I18N.t("holdings.income.source")}><Input value={form.source} onChange={v => set("source", v)} placeholder={I18N.t(allowedCategories?.includes("deposit") ? "holdings.cashflows.source.ph" : "holdings.income.source.ph")}/></FormRow>
        {!isTransfer && <FormRow label={I18N.t("holdings.income.symbol")}><SymbolCombobox value={form.code} onChange={setCode} placeholder="NVDA"/></FormRow>}
        <FormRow label={I18N.t("holdings.income.amount")}>
          <div style={{ display: "flex", gap: 8 }}>
            <Input value={form.amount} onChange={v => set("amount", v)} inputMode="decimal" placeholder="320.00"
              suffix={!isTransfer ? form.currency : undefined} style={{ flex: 1 }}/>
            {isTransfer && <Select value={form.currency} onChange={v => set("currency", v)} options={ccyOptions} style={{ width: 90 }}/>}
          </div>
        </FormRow>
        <FormRow label={I18N.t("holdings.income.note")}><Input value={form.note} onChange={v => set("note", v)} placeholder={`(${I18N.t("base.label.optional")})`}/></FormRow>
        {err && <div style={{ fontSize: 12, color: "var(--up)", marginBottom: 10 }}>{err}</div>}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" type="submit" disabled={saving}>{saving ? I18N.t("base.btn.saving") : I18N.t("base.btn.save")}</Button>
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
      <span style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-2)", textTransform: "uppercase", letterSpacing: ".1em" }}>{I18N.t("base.roadmap")} · {module}</span>
    </div>
    <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
      {features.map(f => <span key={f} style={{ fontSize: 12, padding: "4px 10px", background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 6, color: "var(--ink-3)" }}>{f}</span>)}
    </div>
  </div>
);

window.Holdings = Holdings;
window.ComingSoonBanner = ComingSoonBanner;
