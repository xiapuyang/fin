/* Module 05 — FIRE 退休计划
   Standalone page: header + KPI tiles + chart + parameters + milestones
   Investable capital and MWRR are loaded live from the portfolio (holdings) page.
*/

// Fetch all expense ledger items for the past 3 years and return avg monthly CNY total.
// Returns null if no data is available.
const _avgMonthlyExpense = async () => {
  const now = new Date();
  const start = new Date(now);
  start.setFullYear(start.getFullYear() - 3);
  const startDate = start.toISOString().split("T")[0];

  let all = [];
  let page = 1;
  while (true) {
    const r = await fetch(`/api/ledger?direction=expense&start_date=${startDate}&page=${page}&page_size=200`)
      .then(res => res.json()).catch(() => ({ items: [], pages: 1 }));
    all = all.concat(r.items || []);
    if (page >= (r.pages || 1)) break;
    page++;
  }
  if (all.length === 0) return null;

  const totalCNY = all.reduce((sum, it) => sum + it.amount * (FX[it.currency] || 1), 0);
  const earliest = all.reduce((min, it) => it.date < min ? it.date : min, all[0].date);
  const monthSpan = Math.max(1, Math.round(
    (now - new Date(earliest)) / (1000 * 60 * 60 * 24 * 30.44)
  ));
  const months = Math.min(36, monthSpan);
  return Math.round(totalCNY / months / 100) * 100;
};

const _calcAge = (birthDate) => {
  if (!birthDate) return null;
  const b = new Date(birthDate);
  if (isNaN(b)) return null;
  const now = new Date();
  let a = now.getFullYear() - b.getFullYear();
  const m = now.getMonth() - b.getMonth();
  if (m < 0 || (m === 0 && now.getDate() < b.getDate())) a--;
  return a > 0 && a < 120 ? a : null;
};

const _LIQUID_CATS = new Set(["现金", "存款", "理财", "期权", "社保"]);

const Fire = ({ currency = "CNY", birthDate = "" }) => {
  usePrivacyMasked(); // re-render KPI tiles + chart amounts on privacy toggle
  const [loading, setLoading] = React.useState(true);

  const [manualAge,       setManualAge]       = React.useState(32);
  const [monthlyExp,      setMonthlyExp]      = React.useState(15000);
  const [ledgerAvgExp,    setLedgerAvgExp]    = React.useState(null);
  const [portfolioValue,  setPortfolioValue]  = React.useState(null); // from holdings, null until prices arrive
  const [portfolioMwrr,   setPortfolioMwrr]   = React.useState(null); // MWRR reference for CAGR reset
  const [liquidAssets,    setLiquidAssets]    = React.useState(0);    // 现金/存款/理财/期权/社保 from balance sheet (0% real return)
  const [cagr,            setCagr]            = React.useState(10);
  const [inflation,       setInflation]       = React.useState(3);
  const [monthly,         setMonthly]         = React.useState(8000);
  const [swr,             setSwr]             = React.useState(4);
  const [targetRetireAge, setTargetRetireAge] = React.useState(50);
  const [mcSigma,         setMcSigma]         = React.useState(15);
  const [lifeExpectancy,  setLifeExpectancy]  = React.useState(80);

  React.useEffect(() => {
    Promise.all([
      apiGetAccounts(), apiGetHoldings(), apiGetTransactions(), apiGetIncome(),
      fetch("/api/settings").then(r => r.json()).catch(() => ({})),
      _avgMonthlyExpense(),
    ]).then(([_accts, h, t, inc, s, avgExp]) => {
      // settings
      if (s.fire_cagr     != null) setCagr(s.fire_cagr);
      if (s.fire_inflation != null) setInflation(s.fire_inflation);
      if (s.fire_monthly   != null) setMonthly(s.fire_monthly);
      if (s.fire_swr       != null) setSwr(s.fire_swr);
      if (s.fire_manual_age  != null) setManualAge(s.fire_manual_age);
      if (s.fire_target_age  != null) setTargetRetireAge(s.fire_target_age);
      if (s.fire_mc_sigma       != null) setMcSigma(s.fire_mc_sigma);
      if (s.fire_life_expectancy != null) setLifeExpectancy(s.fire_life_expectancy);

      // monthly expense — ledger avg always shown as reference
      if (avgExp != null) {
        setLedgerAvgExp(avgExp);
        if (s.fire_monthly_exp == null) setMonthlyExp(avgExp);
      }
      if (s.fire_monthly_exp != null) setMonthlyExp(s.fire_monthly_exp);

      // portfolio value + MWRR — fetched async after basic load
      const codes = [...new Set([...h, ...t].map(r => r.code).filter(Boolean))];
      const priceP = codes.length > 0 ? apiGetPrices(codes) : Promise.resolve({});
      priceP.then(prices => {
        const positions = computePositions(h, t, prices);
        const total = positions.reduce((sum, p) => sum + p.value, 0);
        setPortfolioValue(total);
        const mwrr = computeAccountXIRR(inc, positions);
        if (mwrr != null && isFinite(mwrr) && mwrr > 0) {
          const rounded = Math.round(mwrr * 10) / 10;
          setPortfolioMwrr(rounded);
          if (s.fire_cagr == null) setCagr(rounded);
        }
      }).catch(() => setPortfolioValue(0));

      // liquid assets from balance sheet (0% real return — maintains purchasing power)
      apiGetBalanceSnapshots().then(snaps => {
        if (snaps.length === 0) return;
        return apiGetBalanceItems(snaps[snaps.length - 1].id).then(items => {
          const liquid = items
            .filter(i => i.side === "asset" && _LIQUID_CATS.has(i.category))
            .reduce((sum, i) => sum + i.amount * (FX[i.currency] || 1), 0);
          setLiquidAssets(liquid);
        });
      }).catch(() => {});
    }).finally(() => setLoading(false));
  }, []);

  // Debounced settings save — merges patches so rapid multi-setter calls (e.g. applyScenario) all persist
  const _saveTimer = React.useRef(null);
  const _pendingPatch = React.useRef({});
  const saveSettings = (patch) => {
    Object.assign(_pendingPatch.current, patch);
    if (_saveTimer.current) clearTimeout(_saveTimer.current);
    _saveTimer.current = setTimeout(() => {
      const p = { ..._pendingPatch.current };
      _pendingPatch.current = {};
      fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p) })
        .catch((err) => {
          console.warn("Settings save failed:", err);
          _pendingPatch.current = { ...p, ..._pendingPatch.current };
        });
    }, 600);
  };

  // Persisting setters
  const persist = (setter, key) => (v) => { setter(v); saveSettings({ [key]: v }); };
  const setMonthlyExpP      = persist(setMonthlyExp,      "fire_monthly_exp");
  const setCagrP            = persist(setCagr,            "fire_cagr");
  const setInflationP       = persist(setInflation,       "fire_inflation");
  const setMonthlyP         = persist(setMonthly,         "fire_monthly");
  const setSwrP             = persist(setSwr,             "fire_swr");
  const setManualAgeP       = persist(setManualAge,       "fire_manual_age");
  const setTargetRetireAgeP = persist(setTargetRetireAge, "fire_target_age");
  const setMcSigmaP         = persist(setMcSigma,         "fire_mc_sigma");
  const setLifeExpectancyP  = persist(setLifeExpectancy,  "fire_life_expectancy");

  const investable = portfolioValue ?? 0;

  const sym    = CURRENCY_SYMBOL[currency] || "¥";
  const toDisp = (cny) => cny / (FX[currency] || 1);
  const fmtM   = (cny, dp = 1) => PRIVACY.masked ? `${sym}•.•M` : `${sym}${(toDisp(cny) / 1_000_000).toFixed(dp)}M`;

  const derivedAge = _calcAge(birthDate);
  const age = derivedAge ?? manualAge;

  // SWR drives the multiplier — changing the card changes FIRE NUMBER
  const multiplier = Math.round(100 / swr);
  const fireNumber = monthlyExp * 12 * multiplier;
  // Projection uses real CAGR (inflation-adjusted) so values stay in today's purchasing power
  const realCagr = Math.max(0, cagr - inflation);
  // Liquid assets (0% real return) reduce the portfolio target directly
  const effectiveFireTarget = Math.max(0, fireNumber - liquidAssets);

  const project = React.useMemo(() => {
    const out = [];
    let v = investable;
    let yr = age;
    let fired = false;
    while (yr <= 75) {
      if (!fired && v >= effectiveFireTarget) fired = true;
      out.push({ age: yr, value: v, fired });
      // Pre-FIRE: accumulate with monthly contributions
      // Post-FIRE: drawdown — withdraw annual expenses, no new contributions
      v = fired
        ? Math.max(0, v * (1 + realCagr / 100) - monthlyExp * 12)
        : v * (1 + realCagr / 100) + monthly * 12;
      yr++;
    }
    return out;
  }, [investable, realCagr, age, monthly, monthlyExp, effectiveFireTarget]);

  // Debounce MC inputs so slider drags don't trigger a full simulation on every pixel
  const [simInputs, setSimInputs] = React.useState(null);
  React.useEffect(() => {
    const id = setTimeout(() => setSimInputs({
      investable, realCagr, age, monthly, monthlyExp,
      effectiveFireTarget, fireNumber, targetRetireAge, inflation, mcSigma, lifeExpectancy,
    }), 150);
    return () => clearTimeout(id);
  }, [investable, realCagr, age, monthly, monthlyExp, effectiveFireTarget, fireNumber, targetRetireAge, inflation, mcSigma, lifeExpectancy]);

  const monteCarlo = React.useMemo(() => {
    if (!simInputs) return null;
    const { investable, realCagr, age, monthly, monthlyExp, effectiveFireTarget,
            fireNumber, targetRetireAge, inflation, mcSigma, lifeExpectancy } = simInputs;
    if (investable <= 0 && monthly <= 0) return null;
    const N = 500, SIGMA = mcSigma / 100;
    const targetYears = Math.max(1, targetRetireAge - age);
    const totalYears  = Math.max(targetYears + 2, lifeExpectancy - age + 1);
    const paths = [];

    for (let i = 0; i < N; i++) {
      let v = investable;
      const path = [v];
      let ruinAge = null;
      for (let y = 1; y < totalYears; y++) {
        const u1 = Math.max(1e-10, Math.random()), u2 = Math.random();
        const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
        if (y <= targetYears) {
          // Accumulation: grow with monthly contributions
          v = Math.max(0, v * (1 + realCagr / 100 + SIGMA * z) + monthly * 12);
        } else {
          // Withdrawal: pay annual expenses
          v = v * (1 + realCagr / 100 + SIGMA * z) - monthlyExp * 12;
          if (v <= 0 && ruinAge == null) ruinAge = age + y;
          v = Math.max(0, v);
        }
        path.push(v);
      }
      paths.push({ path, ruinAge });
    }

    // Fan chart bands across full lifespan — transpose once, then sort each year row
    const ps = [10, 25, 50, 75, 90];
    const bands = ps.map(() => []);
    for (let i = 0; i < totalYears; i++) {
      const col = new Array(N);
      for (let j = 0; j < N; j++) col[j] = paths[j].path[i];
      col.sort((a, b) => a - b);
      ps.forEach((p, k) => {
        bands[k].push(col[Math.min(N - 1, Math.floor(p / 100 * N))]);
      });
    }

    // Success rate: % reaching effectiveFireTarget by targetRetireAge
    const successRate = paths.filter(({ path }) =>
      path.slice(0, targetYears + 1).some(v => v >= effectiveFireTarget)
    ).length / N;

    // FIRE age distribution
    const fireAges = paths
      .map(({ path }) => { const idx = path.findIndex(v => v >= effectiveFireTarget); return idx >= 0 ? age + idx : null; })
      .filter(a => a != null).sort((a, b) => a - b);
    const pAge = (p) => fireAges.length > 0
      ? fireAges[Math.min(fireAges.length - 1, Math.floor(p / 100 * fireAges.length))]
      : null;
    const fireAgePcts = { p25: pAge(25), p50: pAge(50), p90: pAge(90) };

    // Withdrawal sustainability: ruin age per path (null = outlasts lifeExpectancy)
    const ruinAges = paths.map(p => p.ruinAge);
    const sortedRuins = [...ruinAges].sort((a, b) => (a ?? Infinity) - (b ?? Infinity));
    const pRuin = (pct) => sortedRuins[Math.min(Math.floor(pct / 100 * N), N - 1)];
    const sustainability = {
      p25: pRuin(25), p50: pRuin(50), p90: pRuin(90),
      survivalRate: ruinAges.filter(a => a == null).length / N,
    };

    // Minimum nominal CAGR — same formula as dashboard
    let minNomCagr = fireNumber <= 0 || investable >= fireNumber ? 0 : null;
    if (fireNumber > 0 && investable < fireNumber) {
      const canReach = (nomCagr) => {
        const real = nomCagr - inflation;
        let v = investable;
        for (let y = 1; y <= targetYears; y++) {
          v = v * (1 + real / 100) + monthly * 12;
          if (v >= fireNumber) return true;
        }
        return false;
      };
      if (canReach(40)) {
        let lo = 0, hi = 40;
        for (let iter = 0; iter < 24; iter++) {
          const mid = (lo + hi) / 2;
          if (canReach(mid)) hi = mid; else lo = mid;
        }
        minNomCagr = Math.round(hi * 10) / 10;
      }
    }

    return { bands, successRate, fireAgePcts, minNomCagr, sustainability, years: totalYears };
  }, [simInputs]);

  const fireYear = project.find(p => p.value >= effectiveFireTarget);
  const fireAge = fireYear ? fireYear.age : null;
  const yearsToFire = fireAge ? fireAge - age : null;

  // Scenario: derived from cagr + monthly — no separate state needed
  const activeScenario =
    (cagr === 6  && monthly === 6000  && swr === 3) ? "conservative" :
    (cagr === 10 && monthly === 8000  && swr === 4) ? "base" :
    (cagr === 13 && monthly === 12000 && swr === 5) ? "aggressive" : null;

  const applyScenario = (s) => {
    if (s === "conservative") { setCagrP(6);  setMonthlyP(6000);  setSwrP(3); }
    if (s === "base")         { setCagrP(10); setMonthlyP(8000);  setSwrP(4); }
    if (s === "aggressive")   { setCagrP(13); setMonthlyP(12000); setSwrP(5); }
  };

  if (loading) return (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: 320, color: "var(--ink-3)", fontSize: 14 }}>
      Loading…
    </div>
  );


  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 05 · FIRE"
        title="FIRE 退休计划"
        subtitle={`Financial Independence, Retire Early · 月投入 + 复利 · ${multiplier}× 年支出法则（SWR ${swr}%）· 投资数据取自投资组合页面`}
        right={
          <div style={{ display: "flex", gap: 4, padding: 3, background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 8 }}>
            {[
              { id: "conservative", label: "保守", cagr: 6,  monthly: 6000,  swr: 3, color: "#2563EB" },
              { id: "base",         label: "基准", cagr: 10, monthly: 8000,  swr: 4, color: "#16A34A" },
              { id: "aggressive",   label: "激进", cagr: 13, monthly: 12000, swr: 5, color: "#D97706" },
            ].map(s => {
              const active = activeScenario === s.id;
              return (
                <button key={s.id} onClick={() => applyScenario(s.id)} style={{
                  padding: "5px 10px 6px", borderRadius: 6, cursor: "pointer",
                  border: active ? "none" : `1.5px solid ${s.color}33`,
                  background: active ? s.color : `${s.color}12`,
                  color: active ? "#fff" : s.color,
                  textAlign: "center", transition: "all .15s",
                }}>
                  <div style={{ fontSize: 11.5, fontWeight: 700, lineHeight: 1 }}>{s.label}</div>
                  <div style={{ fontSize: 9.5, opacity: active ? .75 : .8, marginTop: 2, letterSpacing: ".01em" }}>
                    {s.cagr}% · ¥{(s.monthly/1000).toFixed(0)}k · {s.swr}%
                  </div>
                </button>
              );
            })}
          </div>
        }
      />

      {/* KPI tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 14 }}>
        <FireTile label="FIRE NUMBER" value={fmtM(fireNumber)} sub={`月 ${sym}${fmtNum(toDisp(monthlyExp), 0)} × 12 × ${multiplier} (SWR ${swr}%)`}/>
        <FireTile label="CURRENT" value={portfolioValue != null ? fmtM(investable + liquidAssets, 2) : "—"} sub={portfolioValue != null ? `${((investable+liquidAssets)/fireNumber*100).toFixed(0)}% 已达成 · 投资 + 流动资产` : "加载中…"}/>
        <FireTile label="FIRE AGE" value={fireAge ? `${fireAge}` : "—"} sub={fireAge ? `${yearsToFire}y from now` : "Out of range"} accent={fireAge ? "var(--up)" : "var(--down)"}/>
        <FireTile label="REAL CAGR" value={`${realCagr.toFixed(1)}%`} sub={`名义 ${cagr.toFixed(1)}% − 通胀 ${inflation}% · 投影使用实际收益率`}/>
      </div>

      {/* Chart + Parameters */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card padding={20}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>净资产时间轴 Net Worth Timeline</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Projected · age {age}–{lifeExpectancy}</div>
            </div>
            <div style={{ display: "flex", gap: 10, fontSize: 11 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 14, height: 2, background: "var(--ink)" }}/>Accumulation</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 14, height: 0, borderTop: "2px dashed var(--ink)", opacity: .45 }}/>Drawdown</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 14, height: 2, background: "var(--up)", borderTop: "1px dashed var(--up)" }}/>FIRE target</span>
            </div>
          </div>
          <FireChart data={project} fireNumber={fireNumber} effectiveFireTarget={effectiveFireTarget} liquidAssets={liquidAssets} fireAge={fireAge} currency={currency}/>

          {monteCarlo && (
            <div style={{ marginTop: 18, paddingTop: 14, borderTop: "1px dashed var(--line)" }}>
              {/* Header: title + target age picker */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div>
                  <div className="serif-cn" style={{ fontSize: 14, fontWeight: 700 }}>蒙特卡洛模拟 Monte Carlo</div>
                  <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>500 次模拟 · 年收益正态分布 μ={realCagr.toFixed(1)}% σ={mcSigma}%</div>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: 5, alignItems: "flex-end" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontSize: 10.5, color: "var(--ink-4)", whiteSpace: "nowrap" }}>目标退休</span>
                    {[45, 50, 55, 60].map(a => (
                      <button key={a} onClick={() => setTargetRetireAgeP(a)} style={{
                        padding: "2px 7px", fontSize: 11, fontWeight: 500, cursor: "pointer", borderRadius: 5, border: "1px solid",
                        borderColor: targetRetireAge === a ? "var(--ink)" : "var(--line-2)",
                        background:  targetRetireAge === a ? "var(--ink)" : "transparent",
                        color:       targetRetireAge === a ? "#fff" : "var(--ink-3)",
                      }}>{a}</button>
                    ))}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontSize: 10.5, color: "var(--ink-4)", whiteSpace: "nowrap" }}>波动率 σ</span>
                    {[10, 15, 20, 25].map(s => (
                      <button key={s} onClick={() => setMcSigmaP(s)} style={{
                        padding: "2px 7px", fontSize: 11, fontWeight: 500, cursor: "pointer", borderRadius: 5, border: "1px solid",
                        borderColor: mcSigma === s ? "var(--ink)" : "var(--line-2)",
                        background:  mcSigma === s ? "var(--ink)" : "transparent",
                        color:       mcSigma === s ? "#fff" : "var(--ink-3)",
                      }}>{s}%</button>
                    ))}
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontSize: 10.5, color: "var(--ink-4)", whiteSpace: "nowrap" }}>预期寿命</span>
                    {[70, 80, 90].map(a => (
                      <button key={a} onClick={() => setLifeExpectancyP(a)} style={{
                        padding: "2px 7px", fontSize: 11, fontWeight: 500, cursor: "pointer", borderRadius: 5, border: "1px solid",
                        borderColor: lifeExpectancy === a ? "var(--ink)" : "var(--line-2)",
                        background:  lifeExpectancy === a ? "var(--ink)" : "transparent",
                        color:       lifeExpectancy === a ? "#fff" : "var(--ink-3)",
                      }}>{a}</button>
                    ))}
                  </div>
                </div>
              </div>
              {/* 4 stat tiles */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr 1.3fr 1fr", gap: 8, marginBottom: 12 }}>
                <div style={{ background: "var(--paper-2)", borderRadius: 8, padding: "10px 12px", border: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginBottom: 4 }}>达标率 · age {targetRetireAge}</div>
                  <div className="mono" style={{
                    fontSize: 22, fontWeight: 700,
                    color: monteCarlo.successRate >= 0.7 ? "var(--up)" : monteCarlo.successRate >= 0.4 ? "var(--warn)" : "var(--down)",
                  }}>{(monteCarlo.successRate * 100).toFixed(0)}%</div>
                  <div style={{ fontSize: 10, color: "var(--ink-5)", marginTop: 2 }}>500 条路径</div>
                </div>
                <div style={{ background: "var(--paper-2)", borderRadius: 8, padding: "10px 12px", border: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginBottom: 4 }}>FIRE 年龄区间</div>
                  {monteCarlo.fireAgePcts.p50 != null ? (
                    <div style={{ display: "flex", gap: 10, alignItems: "baseline" }}>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 9.5, color: "var(--ink-4)" }}>P25</div>
                        <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-3)" }}>{monteCarlo.fireAgePcts.p25}</div>
                      </div>
                      <div style={{ textAlign: "center", flex: 1 }}>
                        <div style={{ fontSize: 9.5, color: "var(--ink-4)" }}>P50</div>
                        <div className="mono" style={{ fontSize: 20, fontWeight: 700 }}>{monteCarlo.fireAgePcts.p50}</div>
                      </div>
                      <div style={{ textAlign: "center" }}>
                        <div style={{ fontSize: 9.5, color: "var(--ink-4)" }}>P90</div>
                        <div className="mono" style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-3)" }}>{monteCarlo.fireAgePcts.p90}</div>
                      </div>
                    </div>
                  ) : <div style={{ fontSize: 13, color: "var(--ink-4)", paddingTop: 6 }}>—</div>}
                  <div style={{ fontSize: 10, color: "var(--ink-5)", marginTop: 3 }}>成功路径退休年龄分布</div>
                </div>
                <div style={{ background: "var(--paper-2)", borderRadius: 8, padding: "10px 12px", border: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginBottom: 4 }}>最低名义 CAGR</div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>
                    {monteCarlo.minNomCagr != null ? `${monteCarlo.minNomCagr.toFixed(1)}%` : "—"}
                  </div>
                  <div style={{ fontSize: 10, color: "var(--ink-5)", marginTop: 2 }}>
                    {monteCarlo.minNomCagr != null
                      ? `实际 ${Math.max(0, monteCarlo.minNomCagr - inflation).toFixed(1)}% · 确定性计算`
                      : "超出范围"}
                  </div>
                </div>
                {/* Sustainability tile */}
                <div style={{ background: "var(--paper-2)", borderRadius: 8, padding: "10px 12px", border: "1px solid var(--line)" }}>
                  <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginBottom: 4 }}>撑过 {lifeExpectancy} 岁概率</div>
                  {(() => {
                    const { p25, p50, p90, survivalRate } = monteCarlo.sustainability;
                    const fmt = (v) => v == null ? `>${lifeExpectancy}` : `${v}`;
                    const sr = (survivalRate * 100).toFixed(0);
                    const srColor = survivalRate >= 0.8 ? "#16A34A" : survivalRate >= 0.5 ? "#D97706" : "var(--down)";
                    return (
                      <>
                        <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: srColor, lineHeight: 1.1 }}>
                          {sr}<span style={{ fontSize: 13 }}>%</span>
                        </div>
                        <div style={{ display: "flex", gap: 8, marginTop: 5, alignItems: "baseline" }}>
                          {[["P25", fmt(p25), "#D97706"], ["P50", fmt(p50), "var(--ink-3)"], ["P90", fmt(p90), "#16A34A"]].map(([label, val, color]) => (
                            <div key={label} style={{ textAlign: "center" }}>
                              <div style={{ fontSize: 9, color: "var(--ink-5)" }}>{label}</div>
                              <div className="mono" style={{ fontSize: 11, fontWeight: 600, color }}>{val}<span style={{ fontSize: 8 }}>岁</span></div>
                            </div>
                          ))}
                        </div>
                      </>
                    );
                  })()}
                  <div style={{ fontSize: 10, color: "var(--ink-5)", marginTop: 4 }}>提取阶段 · {targetRetireAge}岁退休后</div>
                </div>
              </div>
              <MonteCarloChart
                bands={monteCarlo.bands} years={monteCarlo.years}
                age={age} fireTarget={effectiveFireTarget} currency={currency}
                medFireAge={monteCarlo.fireAgePcts.p50}
                targetRetireAge={targetRetireAge} lifeExpectancy={lifeExpectancy}
              />
              <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 10.5, color: "var(--ink-4)", flexWrap: "wrap" }}>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 20, height: 7, background: "var(--ink)", opacity: .12, display: "inline-block", borderRadius: 1 }}/> P10–P90
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 20, height: 7, background: "var(--ink)", opacity: .22, display: "inline-block", borderRadius: 1 }}/> P25–P75
                </span>
                <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <span style={{ width: 20, height: 2, background: "var(--ink)", opacity: .7, display: "inline-block" }}/> 中位数 P50
                </span>
              </div>
            </div>
          )}
        </Card>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700, marginBottom: 14 }}>参数 Parameters</div>

          {/* Age */}
          {derivedAge != null ? (
            <div style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                <span style={{ fontSize: 12, color: "var(--ink-3)" }}>当前年龄</span>
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{derivedAge} 岁</span>
              </div>
              <div style={{ fontSize: 11, color: "var(--ink-4)" }}>根据出生日期自动计算 · 在设置中修改</div>
            </div>
          ) : (
            <FireSlider label="当前年龄" value={manualAge} onChange={setManualAgeP} min={20} max={60} suffix="岁"/>
          )}

          {/* Monthly expense — label row: [月支出] [3yr avg hint] [current value] */}
          <div style={{ marginBottom: 12 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 4 }}>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>月支出</span>
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                {ledgerAvgExp != null && (
                  <span style={{ fontSize: 10.5, color: "var(--ink-4)" }}>
                    过去3年均 <span className="mono" style={{ fontWeight: 600 }}>{sym}{fmtNum(toDisp(ledgerAvgExp), 0)}</span>
                    {monthlyExp !== ledgerAvgExp && (
                      <button onClick={() => setMonthlyExpP(ledgerAvgExp)} style={{
                        marginLeft: 6, fontSize: 9.5, padding: "1px 4px", borderRadius: 3, cursor: "pointer",
                        border: "1px solid var(--line-2)", background: "transparent", color: "var(--ink-4)",
                      }}>还原</button>
                    )}
                  </span>
                )}
                {(ledgerAvgExp == null || monthlyExp !== ledgerAvgExp) && (
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{sym}{fmtNum(toDisp(monthlyExp), 0)}</span>
                )}
              </div>
            </div>
            <input type="range" min={3000} max={50000} step={500} value={monthlyExp}
              onChange={e => setMonthlyExpP(parseFloat(e.target.value))} style={{ width: "100%" }}/>
            <div style={{
              marginTop: 7, padding: "7px 10px", borderRadius: 6,
              background: "#FFFBEB", border: "1px solid #FDE68A",
              fontSize: 10.5, color: "#78350F", lineHeight: 1.55,
            }}>
              提前退休需自缴社保约 <span className="mono" style={{ fontWeight: 700 }}>{sym}{fmtNum(toDisp(2000), 0)}/月</span>（城镇职工医保 + 养老），约 10 年后至 60 岁可停缴并领养老金。当前计算暂不考虑养老金收入，社保按永久支出处理，FIRE 数字偏保守。
              <button onClick={() => setMonthlyExpP(Math.min(50000, monthlyExp + 2000))} style={{
                marginLeft: 7, fontSize: 9.5, padding: "1px 5px", borderRadius: 3,
                border: "1px solid #D97706", background: "transparent", color: "#D97706", cursor: "pointer",
              }}>+{sym}{fmtNum(toDisp(2000), 0)}</button>
            </div>
          </div>

          {/* SWR — 3 compact cards */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>提取率 SWR</span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{swr}% · {multiplier}×</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 6 }}>
              {[
                { rate: 3, label: "保守", blurb: "40+ 年退休" },
                { rate: 4, label: "标准", blurb: "Bengen 法则" },
                { rate: 5, label: "激进", blurb: "有其他收入" },
              ].map(({ rate, label, blurb }) => {
                const mult = Math.round(100 / rate);
                const active = swr === rate;
                return (
                  <div key={rate} onClick={() => setSwrP(rate)} style={{
                    padding: "8px 10px", borderRadius: 7, cursor: "pointer",
                    border: "1px solid " + (active ? "var(--ink)" : "var(--line)"),
                    background: active ? "var(--ink)" : "var(--paper-2)",
                    color: active ? "#fff" : "var(--ink)",
                    transition: "background .12s",
                  }}>
                    <div style={{ fontSize: 11, fontWeight: 600, opacity: .75 }}>{label} {rate}%</div>
                    <div className="mono" style={{ fontSize: 15, fontWeight: 700, margin: "2px 0" }}>{mult}×</div>
                    <div style={{ fontSize: 10, opacity: .55, lineHeight: 1.3 }}>{blurb}</div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* CAGR — quick buttons + slider */}
          <div style={{ marginBottom: 6 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>预期年化 CAGR <span style={{ color: "var(--ink-5)", fontWeight: 400 }}>名义</span></span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{cagr % 1 === 0 ? cagr : cagr.toFixed(1)}%</span>
            </div>
            <div style={{ display: "flex", gap: 4, marginBottom: 7 }}>
              {[4, 6, 8, 10, 13, 15].map(v => (
                <button key={v} onClick={() => setCagrP(v)} style={{
                  flex: 1, padding: "3px 0", fontSize: 11, fontWeight: 500, cursor: "pointer",
                  border: "1px solid", borderRadius: 5,
                  borderColor: cagr === v ? "var(--ink)" : "var(--line-2)",
                  background:  cagr === v ? "var(--ink)" : "transparent",
                  color:       cagr === v ? "#fff" : "var(--ink-3)",
                }}>{v}%</button>
              ))}
            </div>
            <input type="range" min={3} max={20} step={0.5} value={cagr}
              onChange={e => setCagrP(parseFloat(e.target.value))} style={{ width: "100%" }}/>
            <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 4 }}>
              实际收益率 <span className="mono" style={{ fontWeight: 600 }}>{cagr % 1 === 0 ? cagr : cagr.toFixed(1)}% − {inflation}% = {realCagr.toFixed(1)}%</span> · 投影使用实际值
            </div>
            {portfolioMwrr != null && (
              <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 3, marginBottom: 10 }}>
                投资组合 MWRR <span className="mono" style={{ fontWeight: 600 }}>{portfolioMwrr.toFixed(1)}%</span>
                {Math.abs(cagr - portfolioMwrr) > 0.05 && (
                  <button onClick={() => setCagrP(portfolioMwrr)} style={{
                    marginLeft: 8, fontSize: 10, padding: "1px 5px", borderRadius: 3, cursor: "pointer",
                    border: "1px solid var(--line-2)", background: "transparent", color: "var(--ink-4)",
                  }}>还原</button>
                )}
              </div>
            )}
          </div>

          {/* Inflation rate — quick buttons only */}
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
              <span style={{ fontSize: 12, color: "var(--ink-3)" }}>通胀率 Inflation</span>
              <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{inflation}%</span>
            </div>
            <div style={{ display: "flex", gap: 4 }}>
              {[1, 2, 3, 4, 5].map(v => (
                <button key={v} onClick={() => setInflationP(v)} style={{
                  flex: 1, padding: "3px 0", fontSize: 11, fontWeight: 500, cursor: "pointer",
                  border: "1px solid", borderRadius: 5,
                  borderColor: inflation === v ? "var(--ink)" : "var(--line-2)",
                  background:  inflation === v ? "var(--ink)" : "transparent",
                  color:       inflation === v ? "#fff" : "var(--ink-3)",
                }}>{v}%</button>
              ))}
            </div>
          </div>

          {/* Monthly contribution */}
          <FireSlider label="月度投入" value={monthly} onChange={setMonthlyP} min={0} max={30000} step={500} suffix="¥"/>

          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 8, textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>资产构成</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>投资组合 TOTAL VALUE</span>
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{portfolioValue != null ? fmtM(investable, 2) : "—"}</span>
              </div>
              {liquidAssets > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 11.5, color: "var(--ink-3)" }}>现金/存款/理财/期权/社保</span>
                  <span className="mono" style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)" }}>{fmtM(liquidAssets, 2)}</span>
                </div>
              )}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: 5, borderTop: "1px solid var(--line)" }}>
                <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink)" }}>合计</span>
                <span className="mono" style={{ fontSize: 13, fontWeight: 700 }}>{fmtM(investable + liquidAssets, 2)}</span>
              </div>
            </div>
            {liquidAssets > 0 && (
              <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 6 }}>
                流动资产按通胀率增长（实际收益 0%）· 投资组合缺口 {fmtM(effectiveFireTarget, 2)}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Milestones */}
      {(() => {
        // Coast FIRE: amount needed TODAY so portfolio reaches fireNumber by 65 with zero contributions
        const coastRetireAge = 65;
        const coastYearsLeft = Math.max(1, coastRetireAge - age);
        const coastTarget = fireNumber / Math.pow(1 + realCagr / 100, coastYearsLeft);
        const coastAlready = (investable + liquidAssets) >= coastTarget;
        const coastYr = coastAlready ? null : project.find(p => p.value >= coastTarget);

        const milestones = [
          {
            label: "Lean FIRE", color: "var(--info)",
            target: monthlyExp * 12 * 15,
            multiplierLabel: "15×",
            desc: "极简生活退休",
            detail: "仅覆盖衣食住行基本开支，无旅行娱乐预算。适合低消费生活方式或低物价地区。",
          },
          {
            label: "FIRE", color: "var(--up)",
            target: monthlyExp * 12 * 25,
            multiplierLabel: "25×",
            desc: "标准退休（4% 法则）",
            detail: "退休后维持当前生活水准。Bengen 1994 研究证明按 4% 提取，30 年成功率约 95%。",
          },
          {
            label: "Fat FIRE", color: "var(--warn)",
            target: monthlyExp * 12 * 40,
            multiplierLabel: "40×",
            desc: "富裕退休（2.5% 提取率）",
            detail: "有充足缓冲可应对通胀、医疗、旅行及馈赠，无需在退休后精打细算。",
          },
          {
            label: "Coast FIRE", color: "var(--violet)",
            target: coastTarget,
            multiplierLabel: `到 ${coastRetireAge} 岁`,
            desc: "停止投入，靠复利滑行",
            detail: `今天达到此金额后即可停止定投，复利自然增长至 ${coastRetireAge} 岁时覆盖 FIRE 目标。`,
            coastMode: true,
            coastAlready,
            coastYr,
          },
        ];

        return (
          <div style={{ marginTop: 14 }}>
            <Card padding={20}>
              <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>关键里程碑 Milestones</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
                {milestones.map(m => {
                  const yr = m.coastMode
                    ? (m.coastAlready ? null : m.coastYr)
                    : project.find(p => p.value >= m.target);
                  const reached = m.coastMode ? m.coastAlready : (investable + liquidAssets) >= m.target;
                  return (
                    <div key={m.label} style={{ background: "var(--paper-2)", border: `1px solid ${reached ? m.color : "var(--line)"}`, borderRadius: 10, padding: 14 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
                        <span style={{ width: 8, height: 8, borderRadius: 2, background: m.color, flexShrink: 0 }}/>
                        <span style={{ fontSize: 12, fontWeight: 600 }}>{m.label}</span>
                        <span className="mono" style={{ fontSize: 9, color: "var(--ink-5)", marginLeft: "auto" }}>{m.multiplierLabel}</span>
                      </div>
                      <div style={{ fontSize: 11, fontWeight: 600, color: m.color, marginBottom: 4 }}>{m.desc}</div>
                      <div className="mono" style={{ fontSize: 17, fontWeight: 700 }}>{fmtM(m.target)}</div>
                      <div style={{ fontSize: 11, color: reached ? m.color : "var(--ink-3)", marginTop: 3, fontWeight: reached ? 600 : 400 }}>
                        {reached
                          ? "✓ 已达成"
                          : yr ? `→ age ${yr.age} · ${yr.age - age}y` : "Out of range"}
                      </div>
                      <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 6, lineHeight: 1.5 }}>{m.detail}</div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>
        );
      })()}

      {/* SWR scenario comparison — read-only, all three rates side by side */}
      <div style={{ marginTop: 14 }}>
        <Card padding={20}>
          <div style={{ marginBottom: 14 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>提取率场景推演 SWR Scenarios</div>
              <div style={{ fontSize: 11, color: "var(--ink-4)" }}>当前月支出 · 三种提取率下的目标与退休时间对比</div>
            </div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
              退休后每年从投资组合提取的比例。越保守所需本金越高，但资金安全性更强。当前选中方案高亮显示。
            </div>
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
            {[
              { rate: 3, label: "保守", blurb: "本金更安全，可支撑 40+ 年退休" },
              { rate: 4, label: "标准", blurb: "Bengen 1994 四十年实证黄金法则" },
              { rate: 5, label: "激进", blurb: "所需本金少，适合有其他收入来源" },
            ].map(({ rate, label, blurb }) => {
              const mult = Math.round(100 / rate);
              const annualExp = monthlyExp * 12;
              const required = annualExp / (rate / 100);
              const effTarget = Math.max(0, required - liquidAssets);
              const yr = project.find(p => p.value >= effTarget);
              const active = swr === rate;
              return (
                <div key={rate} onClick={() => setSwrP(rate)} style={{
                  background: active ? "var(--ink)" : "var(--paper-2)",
                  color:      active ? "#fff" : "var(--ink)",
                  border: "1px solid " + (active ? "var(--ink)" : "var(--line)"),
                  borderRadius: 10, padding: 16, cursor: "pointer",
                  transition: "background .12s, border-color .12s",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, opacity: .7 }}>{label} SWR {rate}%</span>
                    <span className="mono" style={{ fontSize: 11, opacity: .6 }}>{mult}×</span>
                  </div>
                  <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6 }}>{fmtM(required)}</div>
                  <div style={{ fontSize: 11, opacity: .7, marginTop: 4 }}>
                    {yr ? `age ${yr.age} · ${yr.age - age}y` : "—"} · {sym}{fmtNum(toDisp(annualExp), 0)} ÷ {rate}%
                  </div>
                  <div style={{ fontSize: 10.5, opacity: .55, marginTop: 5, lineHeight: 1.4 }}>{blurb}</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <ComingSoonBanner module="FIRE" features={["税务影响 / 社保接续"]}/>
    </div>
  );
};

// Tiles + helpers (renamed to avoid collisions if balance.jsx still has them)
const FireTile = ({ label, value, sub, accent }) => (
  <Card padding={16}>
    <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".12em" }}>{label}</div>
    <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: accent || "var(--ink)" }}>{value}</div>
    <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>{sub}</div>
  </Card>
);

const FireSlider = ({ label, value, onChange, min, max, step = 1, suffix }) => (
  <div style={{ marginBottom: 12 }}>
    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
      <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{label}</span>
      <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{value}{suffix}</span>
    </div>
    <input type="range" min={min} max={max} step={step} value={value} onChange={e => onChange(parseFloat(e.target.value))} style={{ width: "100%" }}/>
  </div>
);

const FireChart = ({ data, fireNumber, effectiveFireTarget, liquidAssets = 0, fireAge, currency = "CNY" }) => {
  const chartSym  = CURRENCY_SYMBOL[currency] || "¥";
  const chartRate = FX[currency] || 1;
  const toD = (cny) => cny / chartRate;

  const width = 800, height = 240;
  const padL = 50, padR = 16, padT = 16, padB = 30;
  const w = width - padL - padR, h = height - padT - padB;
  const projMax = Math.max(...data.map(d => d.value));
  const max = Math.max(projMax, fireNumber) * 1.08;
  // Log scale: compresses exponential tail so early and late phases are both readable
  const logFloor = Math.max((data[0]?.value || 1) * 0.3, 10_000);
  const _sl = (v) => Math.log(Math.max(v, logFloor));
  const _logMin = _sl(logFloor), _logMax = _sl(max);
  const xs = (i) => padL + (i / (data.length - 1)) * w;
  const ys = (v) => padT + h - (_sl(v) - _logMin) / (_logMax - _logMin) * h;
  const _fmtG = (cny) => { const v = toD(cny)/1e6; return v>=1000?`${chartSym}${(v/1e3).toFixed(1)}B`:`${chartSym}${v>=10?v.toFixed(0):v.toFixed(1)}M`; };
  const _logGrids = (() => {
    const e0 = Math.floor(Math.log10(logFloor)), e1 = Math.ceil(Math.log10(max)), vs = [];
    for (let e = e0; e <= e1; e++) for (const m of [1, 2, 5]) { const v = m*10**e; if (v >= logFloor*0.8 && v <= max*1.05) vs.push(v); }
    return [...new Set(vs)].sort((a,b) => a-b);
  })();
  // Split path at FIRE point: accumulation (solid) vs drawdown (dashed)
  const fireIdx = data.findIndex(d => d.fired);
  const accData  = fireIdx > 0 ? data.slice(0, fireIdx + 1) : (fireIdx < 0 ? data : []);
  const drawData = fireIdx >= 0 ? data.slice(fireIdx) : [];
  const mkPath = (pts, si) => pts.length < 2 ? null :
    "M " + pts.map((d, i) => `${xs(si + i).toFixed(1)},${ys(d.value).toFixed(1)}`).join(" L ");
  const accPath  = mkPath(accData, 0);
  const drawPath = mkPath(drawData, Math.max(0, fireIdx));
  const fullPath = "M " + data.map((d, i) => `${xs(i).toFixed(1)},${ys(d.value).toFixed(1)}`).join(" L ");
  const fill = fullPath + ` L ${(padL + w).toFixed(1)},${(padT + h).toFixed(1)} L ${padL.toFixed(1)},${(padT + h).toFixed(1)} Z`;
  // Show FIRE target line; if liquid assets exist, also show portfolio-only target
  const hasLiquid = liquidAssets > 0;
  const fireY = ys(fireNumber);
  const effY  = hasLiquid ? ys(effectiveFireTarget) : null;
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {_logGrids.map((v, i) => { const y = ys(v); if (y < padT-4 || y > padT+h+4) return null; return (
        <g key={i}>
          <line x1={padL} x2={padL+w} y1={y} y2={y} stroke="var(--line)" strokeDasharray="2 3"/>
          <text x={padL-8} y={y+3} fontSize="10" fill="var(--ink-4)" textAnchor="end" className="mono">{_fmtG(v)}</text>
        </g>
      ); })}
      <text x={padL-8} y={padT+h+13} fontSize="9" fill="var(--ink-5)" textAnchor="end">log</text>
      {/* FIRE total target line */}
      <line x1={padL} x2={padL+w} y1={fireY} y2={fireY} stroke="var(--up)" strokeDasharray="4 3" strokeWidth="1.5"/>
      <text x={padL+w-4} y={fireY-5} fontSize="10" fill="var(--up)" textAnchor="end" fontWeight="600">FIRE {chartSym}{(toD(fireNumber)/1000000).toFixed(1)}M</text>
      {/* Portfolio-only target line — label flips below the line when too close to FIRE label */}
      {hasLiquid && effY != null && (
        <>
          <line x1={padL} x2={padL+w} y1={effY} y2={effY} stroke="var(--up)" strokeDasharray="2 5" strokeWidth="1" strokeOpacity=".45"/>
          <text x={padL+w-4} y={Math.abs(effY - fireY) < 18 ? effY+11 : effY-5} fontSize="9.5" fill="var(--up)" fillOpacity=".7" textAnchor="end">投资组合目标 {chartSym}{(toD(effectiveFireTarget)/1000000).toFixed(1)}M</text>
        </>
      )}
      <path d={fill} fill="var(--ink)" fillOpacity=".06"/>
      {accPath  && <path d={accPath}  stroke="var(--ink)" strokeWidth="2"   fill="none"/>}
      {drawPath && <path d={drawPath} stroke="var(--ink)" strokeWidth="1.5" fill="none" strokeDasharray="5 3" strokeOpacity=".5"/>}
      {/* Start point label */}
      {data.length > 0 && (() => {
        const sx = xs(0), sy = ys(data[0].value);
        const label = `${chartSym}${(toD(data[0].value)/1000000).toFixed(2)}M`;
        const labelW = label.length * 6 + 10;
        // place label above the dot, shift right so it doesn't overlap y-axis
        const lx = sx + 6, ly = sy - 8;
        return (
          <g>
            <circle cx={sx} cy={sy} r="4" fill="var(--ink)" fillOpacity=".5"/>
            <rect x={lx} y={ly - 11} width={labelW} height={15} rx="3" fill="var(--ink)" fillOpacity=".08"/>
            <text x={lx + 5} y={ly} fontSize="10" fill="var(--ink-3)" className="mono" fontWeight="500">{label}</text>
          </g>
        );
      })()}
      {fireIdx >= 0 && (
        <g>
          <line x1={xs(fireIdx)} x2={xs(fireIdx)} y1={padT} y2={padT+h} stroke="var(--up)" strokeWidth="1" strokeDasharray="2 3"/>
          <circle cx={xs(fireIdx)} cy={ys(data[fireIdx].value)} r="5" fill="var(--up)"/>
          <rect x={xs(fireIdx)-22} y={padT-2} width="44" height="18" rx="3" fill="var(--up)"/>
          <text x={xs(fireIdx)} y={padT+11} fontSize="11" fill="#fff" textAnchor="middle" fontWeight="600">Age {data[fireIdx].age}</text>
        </g>
      )}
      {data.filter((_, i) => i % 5 === 0 || i === data.length - 1).map((d, i) => {
        const idx = data.indexOf(d);
        return <text key={i} x={xs(idx)} y={height-8} fontSize="10" fill="var(--ink-4)" textAnchor="middle" className="mono">{d.age}</text>;
      })}
    </svg>
  );
};

const MonteCarloChart = ({ bands, years, age, fireTarget, currency = "CNY", medFireAge, targetRetireAge, lifeExpectancy }) => {
  const chartSym  = CURRENCY_SYMBOL[currency] || "¥";
  const chartRate = FX[currency] || 1;
  const toD = (cny) => cny / chartRate;

  const width = 800, height = 180;
  const padL = 50, padR = 16, padT = 12, padB = 26;
  const w = width - padL - padR, h = height - padT - padB;

  const maxVal = Math.max(Math.max(...bands[4]), fireTarget) * 1.08;
  const _mcFloor = Math.max((bands[0][0] || 1) * 0.3, 10_000);
  const _slM = (v) => Math.log(Math.max(v, _mcFloor));
  const _logMinM = _slM(_mcFloor), _logMaxM = _slM(maxVal);
  const xs = (i) => padL + (i / (years - 1)) * w;
  const ys = (v) => padT + h - (_slM(v) - _logMinM) / (_logMaxM - _logMinM) * h;
  const _fmtGM = (cny) => { const v = toD(cny)/1e6; return v>=1000?`${chartSym}${(v/1e3).toFixed(1)}B`:`${chartSym}${v>=10?v.toFixed(0):v.toFixed(1)}M`; };
  const _logGridsM = (() => {
    const e0 = Math.floor(Math.log10(_mcFloor)), e1 = Math.ceil(Math.log10(maxVal)), vs = [];
    for (let e = e0; e <= e1; e++) for (const m of [1, 2, 5]) { const v = m*10**e; if (v >= _mcFloor*0.8 && v <= maxVal*1.05) vs.push(v); }
    return [...new Set(vs)].sort((a,b) => a-b);
  })();

  const areaPath = (upper, lower) =>
    "M " + upper.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" L ") +
    " L " + [...lower].reverse().map((v, i) => `${xs(years - 1 - i).toFixed(1)},${ys(v).toFixed(1)}`).join(" L ") + " Z";
  const linePath = (arr) =>
    "M " + arr.map((v, i) => `${xs(i).toFixed(1)},${ys(v).toFixed(1)}`).join(" L ");

  const fireY = ys(fireTarget);

  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {_logGridsM.map((v, i) => { const y = ys(v); if (y < padT-4 || y > padT+h+4) return null; return (
        <g key={i}>
          <line x1={padL} x2={padL+w} y1={y} y2={y} stroke="var(--line)" strokeDasharray="2 3"/>
          <text x={padL-8} y={y+3} fontSize="10" fill="var(--ink-4)" textAnchor="end" className="mono">{_fmtGM(v)}</text>
        </g>
      ); })}
      <text x={padL-8} y={padT+h+14} fontSize="9" fill="var(--ink-5)" textAnchor="end">log</text>
      {/* Withdrawal zone shading */}
      {targetRetireAge != null && (() => {
        const retireIdx = targetRetireAge - age;
        if (retireIdx < 0 || retireIdx >= years) return null;
        const rx = xs(retireIdx);
        return (
          <g>
            <rect x={rx} y={padT} width={padL + w - rx} height={h} fill="var(--ink)" fillOpacity=".03"/>
            <line x1={rx} x2={rx} y1={padT} y2={padT+h} stroke="var(--ink-3)" strokeWidth="1" strokeDasharray="3 3" strokeOpacity=".5"/>
            <text x={rx+4} y={padT+10} fontSize="9.5" fill="var(--ink-3)" fontWeight="600">提取</text>
          </g>
        );
      })()}
      {/* FIRE target line */}
      <line x1={padL} x2={padL+w} y1={fireY} y2={fireY} stroke="var(--up)" strokeDasharray="4 3" strokeWidth="1.5"/>
      <text x={padL+w-4} y={fireY-5} fontSize="10" fill="var(--up)" textAnchor="end" fontWeight="600">
        FIRE {PRIVACY.masked ? `${chartSym}•.•M` : `${chartSym}${(toD(fireTarget)/1_000_000).toFixed(1)}M`}
      </text>
      {/* P10–P90 band */}
      <path d={areaPath(bands[4], bands[0])} fill="var(--ink)" fillOpacity=".08"/>
      {/* P25–P75 band */}
      <path d={areaPath(bands[3], bands[1])} fill="var(--ink)" fillOpacity=".15"/>
      {/* P50 median line */}
      <path d={linePath(bands[2])} stroke="var(--ink)" strokeWidth="1.5" fill="none" strokeOpacity=".75"/>
      {/* Median FIRE age marker */}
      {medFireAge != null && (() => {
        const idx = medFireAge - age;
        if (idx < 0 || idx >= years) return null;
        const mx = xs(idx);
        return (
          <g>
            <line x1={mx} x2={mx} y1={padT} y2={padT+h} stroke="var(--up)" strokeWidth="1" strokeDasharray="2 3" strokeOpacity=".6"/>
            <rect x={mx-22} y={padT-2} width="44" height="17" rx="3" fill="var(--up)" fillOpacity=".85"/>
            <text x={mx} y={padT+10} fontSize="10.5" fill="#fff" textAnchor="middle" fontWeight="600">Age {medFireAge}</text>
          </g>
        );
      })()}
      {/* X-axis labels */}
      {Array.from({ length: years }, (_, i) => age + i)
        .filter((_, i) => i % 5 === 0 || i === years - 1)
        .map(a => {
          const i = a - age;
          return <text key={a} x={xs(i)} y={height - 8} fontSize="10" fill="var(--ink-4)" textAnchor="middle" className="mono">{a}</text>;
        })}
    </svg>
  );
};

window.Fire = Fire;
