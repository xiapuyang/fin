/* Module 02 — Holdings: positions + transactions + manual income */

const Holdings = () => {
  const [tab, setTab] = React.useState("positions");

  // === Compute positions from TRANSACTIONS (avg cost & realized PnL) ========
  const computed = React.useMemo(() => {
    // group by code in chronological order
    const byCode = {};
    [...TRANSACTIONS].sort((a,b) => a.date.localeCompare(b.date)).forEach(t => {
      const k = t.code;
      if (!byCode[k]) byCode[k] = { shares: 0, cost: 0, realized: 0, txns: [] };
      const p = byCode[k];
      if (t.side === "buy") {
        p.cost += t.shares * t.price;
        p.shares += t.shares;
      } else {
        const avg = p.shares ? p.cost / p.shares : 0;
        p.realized += (t.price - avg) * t.shares;
        p.cost -= avg * t.shares;
        p.shares -= t.shares;
      }
      p.txns.push(t);
    });
    // build positions list
    const positions = HOLDINGS.map(h => {
      const sym = SYMBOL_INDEX[h.code] || h;
      const ccy = sym.currency || h.currency || "USD";
      const fx = FX[ccy] || 1;
      const c = byCode[h.code] || { shares: h.shares, cost: h.cost * h.shares, realized: 0, txns: [] };
      const avgCost = c.shares ? c.cost / c.shares : h.cost;
      const value = sym.price * c.shares * fx;
      const cost  = avgCost * c.shares * fx;
      const pnl = value - cost;
      const pnlPct = cost ? (pnl / cost) * 100 : 0;
      const dayChange = ((sym.price - sym.prevClose) / sym.prevClose) * 100;
      const realizedCNY = c.realized * fx;
      // first buy date for IRR
      const firstBuy = c.txns.find(t => t.side === "buy");
      const days = firstBuy ? (new Date("2026-05-03") - new Date(firstBuy.date)) / 86400000 : 1;
      const years = days / 365;
      const totalReturn = (value + realizedCNY - cost) / cost;
      const irr = years > 0.1 && cost > 0 ? (Math.pow(1 + totalReturn, 1 / years) - 1) * 100 : null;
      return { ...h, sym, ccy, fx, shares: c.shares, avgCost, value, cost, pnl, pnlPct, dayChange, realizedCNY, irr, txnCount: c.txns.length };
    });
    return positions;
  }, []);

  const positions = computed;
  const total = positions.reduce((s, p) => s + p.value, 0);
  const totalCost = positions.reduce((s, p) => s + p.cost, 0);
  const totalUnrealized = total - totalCost;
  const totalRealized = positions.reduce((s, p) => s + p.realizedCNY, 0);
  const incomeTotal = HOLDINGS_INCOME.reduce((s, i) => s + i.amount * (FX[i.ccy] || 1), 0);

  // Weighted IRR (by cost)
  const weightedIRR = (() => {
    const valid = positions.filter(p => p.irr != null && isFinite(p.irr));
    const totalC = valid.reduce((s, p) => s + p.cost, 0);
    return totalC ? valid.reduce((s, p) => s + p.irr * p.cost, 0) / totalC : null;
  })();

  const dayPnl = positions.reduce((s, p) => s + p.value * p.dayChange / 100, 0);

  const byMarket = ["US", "HK", "CN"].map(m => {
    const v = positions.filter(p => p.market === m).reduce((s, p) => s + p.value, 0);
    return { label: m === "US" ? "美股" : m === "HK" ? "港股" : "A股", value: v, color: { US: "#1F4FE0", HK: "#B8447B", CN: "#C8460F" }[m] };
  });

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 02 · PORTFOLIO"
        title="投资组合"
        subtitle="Portfolio Tracker · 平均成本 & 累积盈亏 & 年化 IRR"
        right={<div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon="plus">买入 / 卖出</Button>
          <Button variant="secondary" icon="plus">手动收入</Button>
          <Button variant="primary" icon="mail">发送周报</Button>
        </div>}
      />

      {/* Top stats — 4 tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL VALUE · 总市值</div>
          <div className="mono" style={{ fontSize: 34, fontWeight: 700, marginTop: 4 }}>¥{(total/1000000).toFixed(2)}<span style={{ fontSize: 18, color: "var(--ink-3)" }}>M</span></div>
          <div style={{ display: "flex", gap: 16, marginTop: 6 }}>
            <div><span style={{ fontSize: 11, color: "var(--ink-4)" }}>累计未实现 </span><ChangeNum value={(totalUnrealized/totalCost)*100} size="sm"/></div>
            <div><span style={{ fontSize: 11, color: "var(--ink-4)" }}>今日 </span><ChangeNum value={dayPnl/total*100} size="sm"/></div>
          </div>
          <div style={{ marginTop: 14 }}>
            <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden" }}>
              {byMarket.map(b => <div key={b.label} style={{ flex: b.value, background: b.color }}/>)}
            </div>
            <div style={{ display: "flex", gap: 14, marginTop: 8, fontSize: 11, color: "var(--ink-3)" }}>
              {byMarket.map(b => <span key={b.label} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 8, height: 8, background: b.color, borderRadius: 2 }}/>{b.label} {(b.value/total*100).toFixed(0)}%</span>)}
            </div>
          </div>
        </Card>
        <StatTile
          label="UNREALIZED P&L"
          value={`${totalUnrealized >= 0 ? "+" : "−"}¥${(Math.abs(totalUnrealized)/1000).toFixed(0)}k`}
          tone={totalUnrealized >= 0 ? "up" : "down"}
          sub={`vs cost ¥${(totalCost/1000000).toFixed(2)}M`}
        />
        <StatTile
          label="REALIZED + 收入"
          value={`+¥${((totalRealized + incomeTotal)/1000).toFixed(1)}k`}
          tone="up"
          sub={`已实现 ¥${(totalRealized/1000).toFixed(1)}k · 收入 ¥${(incomeTotal/1000).toFixed(1)}k`}
        />
        <StatTile
          label="平均年化 IRR"
          value={weightedIRR != null ? `${weightedIRR.toFixed(1)}%` : "—"}
          tone={weightedIRR != null && weightedIRR >= 0 ? "up" : "down"}
          sub="加权平均，自首次买入起"
        />
      </div>

      {/* Tabs */}
      <div style={{ marginBottom: 14 }}>
        <Tabs
          variant="underline"
          value={tab} onChange={setTab}
          tabs={[
            { id: "positions",   label: "持仓 Positions",     count: positions.length },
            { id: "transactions",label: "交易记录 Trades",    count: TRANSACTIONS.length },
            { id: "income",      label: "手动收入 Income",     count: HOLDINGS_INCOME.length },
            { id: "rebalance",   label: "再平衡 Rebalance",    icon: "spark" },
          ]}
        />
      </div>

      {tab === "positions"    && <PositionsTable positions={positions} total={total}/>}
      {tab === "transactions" && <TransactionsTable txns={TRANSACTIONS}/>}
      {tab === "income"       && <IncomeTable items={HOLDINGS_INCOME} total={incomeTotal}/>}
      {tab === "rebalance"    && <RebalancePanel positions={positions} total={total}/>}

      <ComingSoonBanner module="Holdings" features={["Auto-import 券商 CSV", "Tax-loss harvesting hints", "Dividend tracking", "Cost basis FIFO/LIFO"]} />
    </div>
  );
};

const StatTile = ({ label, value, sub, tone }) => (
  <Card padding={20}>
    <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{label}</div>
    <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: tone === "up" ? "var(--up)" : tone === "down" ? "var(--down)" : "var(--ink)" }}>{value}</div>
    <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{sub}</div>
  </Card>
);

// ============================================================================
const PositionsTable = ({ positions, total }) => (
  <Card padding={0}>
    <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
      <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>持仓明细 Positions</div>
      <Tabs variant="pill" value="all" onChange={()=>{}} tabs={[{id:"all",label:"全部"},{id:"us",label:"美股"},{id:"hk",label:"港股"},{id:"cn",label:"A股"}]}/>
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "30px 1.4fr 70px 95px 90px 80px 95px 100px 80px 60px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
      <span></span><span>POSITION</span>
      <span style={{ textAlign: "right" }}>SHARES</span>
      <span style={{ textAlign: "right" }}>AVG COST</span>
      <span style={{ textAlign: "right" }}>PRICE</span>
      <span style={{ textAlign: "right" }}>DAY</span>
      <span style={{ textAlign: "right" }}>VALUE (¥)</span>
      <span style={{ textAlign: "right" }}>未实现 P&L</span>
      <span style={{ textAlign: "right" }}>IRR</span>
      <span></span>
    </div>
    {[...positions].sort((a,b) => b.value - a.value).map((p, i, arr) => (
      <div key={p.code} style={{ display: "grid", gridTemplateColumns: "30px 1.4fr 70px 95px 90px 80px 95px 100px 80px 60px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < arr.length - 1 ? "1px solid var(--line)" : "none" }}>
        <MarketDot market={p.market}/>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="mono" style={{ fontWeight: 600 }}>{p.code}</span>
            <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{p.sym.name}</span>
            <span style={{ fontSize: 10, color: "var(--ink-4)", padding: "1px 6px", border: "1px solid var(--line)", borderRadius: 4 }}>{p.txnCount} 笔</span>
          </div>
          <div style={{ marginTop: 4 }}><Sparkline data={p.sym.spark} width={140} height={20} fill={true}/></div>
        </div>
        <span className="mono" style={{ textAlign: "right", fontSize: 12 }}>{p.shares}</span>
        <span className="mono" style={{ textAlign: "right", fontSize: 12, color: "var(--ink-3)" }}>{fmtMoney(p.avgCost, p.ccy, 2)}</span>
        <span className="mono" style={{ textAlign: "right", fontSize: 13, fontWeight: 600 }}>{fmtMoney(p.sym.price, p.ccy, 2)}</span>
        <span style={{ textAlign: "right" }}><ChangeNum value={p.dayChange} size="sm"/></span>
        <span className="mono" style={{ textAlign: "right", fontSize: 13, fontWeight: 600 }}>¥{fmtNum(p.value, 0)}</span>
        <div style={{ textAlign: "right" }}>
          <ChangeNum value={p.pnlPct} size="sm"/>
          <div className="mono" style={{ fontSize: 10.5, color: p.pnl >= 0 ? "var(--up)" : "var(--down)", marginTop: 1 }}>
            {p.pnl >= 0 ? "+" : "−"}¥{fmtNum(Math.abs(p.pnl), 0)}
          </div>
        </div>
        <span className="mono" style={{ textAlign: "right", fontSize: 12, fontWeight: 600, color: p.irr == null ? "var(--ink-4)" : p.irr >= 0 ? "var(--up)" : "var(--down)" }}>
          {p.irr == null ? "—" : (p.irr >= 0 ? "+" : "") + p.irr.toFixed(1) + "%"}
        </span>
        <button style={iconBtn2} title="查看交易历史"><Icon name="edit" size={13}/></button>
      </div>
    ))}
  </Card>
);

// ============================================================================
const TransactionsTable = ({ txns }) => {
  const sorted = [...txns].sort((a,b) => b.date.localeCompare(a.date));
  return (
    <Card padding={0}>
      <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>交易记录 Transactions</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>买入 & 卖出 · 用于计算平均成本和已实现盈亏</div>
        </div>
        <Button size="sm" variant="secondary" icon="plus">新增记录</Button>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "100px 80px 1.2fr 80px 100px 110px 130px 1fr", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
        <span>DATE</span><span>TYPE</span><span>SYMBOL</span>
        <span style={{ textAlign: "right" }}>SHARES</span>
        <span style={{ textAlign: "right" }}>PRICE</span>
        <span style={{ textAlign: "right" }}>AMOUNT</span>
        <span style={{ textAlign: "right" }}>REALIZED</span>
        <span>NOTE</span>
      </div>
      {sorted.map((t, i) => {
        const sym = SYMBOL_INDEX[t.code] || {};
        const amt = t.shares * t.price;
        return (
          <div key={t.id} style={{ display: "grid", gridTemplateColumns: "100px 80px 1.2fr 80px 100px 110px 130px 1fr", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < sorted.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
            <span className="mono" style={{ color: "var(--ink-3)" }}>{t.date}</span>
            <Badge tone={t.side === "buy" ? "up" : "down"} solid={false} size="sm">{t.side === "buy" ? "买入" : "卖出"}</Badge>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
              <span className="mono" style={{ fontWeight: 600 }}>{t.code}</span>
              <span style={{ color: "var(--ink-3)" }}>{sym.name || ""}</span>
            </span>
            <span className="mono" style={{ textAlign: "right" }}>{t.shares}</span>
            <span className="mono" style={{ textAlign: "right" }}>{fmtMoney(t.price, t.ccy, 2)}</span>
            <span className="mono" style={{ textAlign: "right", fontWeight: 600 }}>{fmtMoney(amt, t.ccy, 0)}</span>
            <span className="mono" style={{ textAlign: "right", color: t.realized >= 0 ? "var(--up)" : t.realized != null ? "var(--down)" : "var(--ink-4)", fontWeight: 600 }}>
              {t.realized != null ? (t.realized >= 0 ? "+" : "−") + fmtMoney(Math.abs(t.realized), t.ccy, 0) : "—"}
            </span>
            <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{t.note || ""}</span>
          </div>
        );
      })}
    </Card>
  );
};

// ============================================================================
const IncomeTable = ({ items, total }) => {
  const sorted = [...items].sort((a,b) => b.date.localeCompare(a.date));
  const byCat = items.reduce((acc, i) => {
    const cny = i.amount * (FX[i.ccy] || 1);
    acc[i.category] = (acc[i.category] || 0) + cny;
    return acc;
  }, {});
  const catColors = { dividend: "#1F8A4C", interest: "#2D5BD9", option: "#6B4FB8" };
  const catLabels = { dividend: "分红 Dividend", interest: "利息 Interest", option: "期权 Option" };
  return (
    <div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 14 }}>
        {Object.entries(byCat).map(([cat, v]) => (
          <Card key={cat} padding={16}>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ width: 8, height: 8, borderRadius: 2, background: catColors[cat] }}/>
              <span style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-3)" }}>{catLabels[cat]}</span>
            </div>
            <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: "var(--up)" }}>+¥{fmtNum(v, 0)}</div>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>累计 {items.filter(i => i.category === cat).length} 笔</div>
          </Card>
        ))}
      </div>
      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>手动收入记录</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>分红 / 利息 / 期权权利金 — 累计 ¥{fmtNum(total, 0)}</div>
          </div>
          <Button size="sm" variant="secondary" icon="plus">添加收入</Button>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "100px 90px 1.4fr 130px 130px 1fr", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
          <span>DATE</span><span>TYPE</span><span>SOURCE</span>
          <span style={{ textAlign: "right" }}>AMOUNT</span>
          <span style={{ textAlign: "right" }}>≈ CNY</span>
          <span>NOTE</span>
        </div>
        {sorted.map((i, idx) => {
          const cny = i.amount * (FX[i.ccy] || 1);
          return (
            <div key={i.id} style={{ display: "grid", gridTemplateColumns: "100px 90px 1.4fr 130px 130px 1fr", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: idx < sorted.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
              <span className="mono" style={{ color: "var(--ink-3)" }}>{i.date}</span>
              <Badge tone={i.category === "dividend" ? "down" : i.category === "option" ? "violet" : "info"} size="sm">{catLabels[i.category]}</Badge>
              <span>{i.source}</span>
              <span className="mono" style={{ textAlign: "right", fontWeight: 600, color: "var(--up)" }}>+{fmtMoney(i.amount, i.ccy, 2)}</span>
              <span className="mono" style={{ textAlign: "right", color: "var(--ink-3)" }}>+¥{fmtNum(cny, 0)}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{i.note || "—"}</span>
            </div>
          );
        })}
      </Card>
    </div>
  );
};

// ============================================================================
const RebalancePanel = ({ positions, total }) => {
  // Target allocation (mock — would be user-defined)
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
  // remainder counts as cash bucket
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
            const curPct = (t.current / total) * 100;
            const drift = curPct - t.pct;
            const deltaCny = (t.pct/100 * total) - t.current;
            return (
              <div key={label} style={{ marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13 }}>
                    <span style={{ width: 8, height: 8, background: t.color, borderRadius: 2 }}/>
                    {label}
                  </span>
                  <span className="mono" style={{ fontSize: 12, color: "var(--ink-3)" }}>{curPct.toFixed(1)}% / {t.pct}%</span>
                </div>
                <div style={{ position: "relative", height: 8, background: "var(--bg-deep)", borderRadius: 4 }}>
                  <div style={{ position: "absolute", left: 0, top: 0, width: `${curPct}%`, height: "100%", background: t.color, borderRadius: 4, opacity: .5 }}/>
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

const iconBtn2 = { width: 24, height: 24, background: "transparent", border: "none", borderRadius: 4, color: "var(--ink-3)", cursor: "pointer", display: "inline-flex", alignItems: "center", justifyContent: "center" };

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
