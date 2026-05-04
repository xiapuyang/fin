/* Module 04 — Balance Sheet (replaces Plan + Retire)
   - Items can be assets or liabilities, categorized
   - Each item belongs to one or more historical snapshots
   - Latest snapshot shown by default; user can switch to a historical one
   - Bottom: FIRE projection driven by current net worth
*/

const BalanceSheet = () => {
  // Latest snapshot is last in array
  const latest = BS_SNAPSHOTS[BS_SNAPSHOTS.length - 1];
  const [snapId, setSnapId] = React.useState(latest.id);
  const [side, setSide]     = React.useState("all"); // all | asset | liability
  const [showSnapMenu, setShowSnapMenu] = React.useState(false);

  const snap = BS_SNAPSHOTS.find(s => s.id === snapId) || latest;
  const isLatest = snap.id === latest.id;

  // Items in this snapshot
  const itemsAll = BS_ITEMS.filter(it => it.inSnapshot.includes(snap.id));

  const inCNY = (it) => it.amount * (FX[it.currency] || 1);
  const totalAssets      = itemsAll.filter(i => i.side === "asset")    .reduce((s, i) => s + inCNY(i), 0);
  const totalLiabilities = itemsAll.filter(i => i.side === "liability").reduce((s, i) => s + inCNY(i), 0);
  const netWorth = totalAssets - totalLiabilities;

  // Historical net worth series (each snapshot)
  const series = BS_SNAPSHOTS.map(s => {
    const its = BS_ITEMS.filter(it => it.inSnapshot.includes(s.id));
    const a = its.filter(i => i.side === "asset")    .reduce((sum, i) => sum + inCNY(i), 0);
    const l = its.filter(i => i.side === "liability").reduce((sum, i) => sum + inCNY(i), 0);
    return { ...s, assets: a, liabilities: l, net: a - l };
  });
  const idx  = series.findIndex(s => s.id === snap.id);
  const prev = idx > 0 ? series[idx - 1] : null;
  const delta = prev ? netWorth - prev.net : 0;
  const deltaPct = prev && prev.net ? (delta / prev.net) * 100 : 0;

  // Category aggregation for current snapshot
  const aggCat = (whichSide) => {
    const cats = BS_CATEGORIES[whichSide];
    return cats.map(cat => {
      const v = itemsAll.filter(i => i.side === whichSide && i.category === cat).reduce((s, i) => s + inCNY(i), 0);
      const ct = itemsAll.filter(i => i.side === whichSide && i.category === cat).length;
      return { label: cat, value: v, count: ct, color: BS_CAT_COLORS[cat] };
    }).filter(c => c.value > 0 || c.count > 0);
  };
  const assetCats = aggCat("asset");
  const liabCats  = aggCat("liability");

  // Filter for table
  const filtered = side === "all" ? itemsAll : itemsAll.filter(i => i.side === side);

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 04 · BALANCE SHEET"
        title="资产负债"
        subtitle="Net Worth Tracker · 随时新增条目 · 多版本快照 · 底部 FIRE 推演"
        right={<div style={{ display: "flex", gap: 8 }}>
          <Button variant="secondary" icon="plus">新增条目</Button>
          <Button variant="primary" icon="archive">保存为新快照</Button>
        </div>}
      />

      {/* Snapshot selector + status banner */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, gap: 16, padding: "10px 14px", background: isLatest ? "var(--paper)" : "var(--warn-soft)", border: "1px solid " + (isLatest ? "var(--line)" : "var(--warn)"), borderRadius: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <Icon name={isLatest ? "clock" : "archive"} size={16} style={{ color: isLatest ? "var(--ink-3)" : "#7A4D0E" }}/>
          <div>
            <div style={{ fontSize: 12, fontWeight: 600, color: isLatest ? "var(--ink-3)" : "#7A4D0E", letterSpacing: ".05em", textTransform: "uppercase" }}>
              {isLatest ? "VIEWING LATEST · 当前最新版" : "VIEWING HISTORICAL · 历史快照"}
            </div>
            <div style={{ fontSize: 13.5, marginTop: 2 }}>
              <span className="mono" style={{ fontWeight: 600 }}>{snap.date}</span>
              <span style={{ margin: "0 8px", color: "var(--ink-4)" }}>·</span>
              <span>{snap.label}</span>
              {snap.note && <span style={{ marginLeft: 8, color: "var(--ink-3)", fontSize: 12 }}>— {snap.note}</span>}
            </div>
          </div>
        </div>
        <div style={{ position: "relative" }}>
          <Button variant="secondary" iconRight="chevron-down" onClick={() => setShowSnapMenu(v => !v)}>
            切换快照 · {BS_SNAPSHOTS.length} versions
          </Button>
          {showSnapMenu && (
            <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 10, boxShadow: "var(--shadow-lg)", padding: 6, width: 360, zIndex: 50 }}>
              {[...BS_SNAPSHOTS].reverse().map(s => {
                const sel = s.id === snap.id;
                const its = BS_ITEMS.filter(it => it.inSnapshot.includes(s.id));
                const a = its.filter(i => i.side === "asset")    .reduce((sum, i) => sum + i.amount * (FX[i.currency]||1), 0);
                const l = its.filter(i => i.side === "liability").reduce((sum, i) => sum + i.amount * (FX[i.currency]||1), 0);
                return (
                  <button key={s.id} onClick={() => { setSnapId(s.id); setShowSnapMenu(false); }} style={{
                    display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", width: "100%",
                    background: sel ? "var(--bg-deep)" : "transparent", border: "none", borderRadius: 8,
                    cursor: "pointer", textAlign: "left",
                  }}>
                    <span style={{ width: 6, height: 6, borderRadius: 3, background: sel ? "var(--ink)" : "var(--line-strong)", flexShrink: 0 }}/>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
                        <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11.5, fontWeight: 500 }}>{s.date}</span>
                        <span>{s.label}</span>
                        {s.id === latest.id && <Badge tone="up" size="sm" solid>最新</Badge>}
                      </div>
                      <div className="mono" style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>net ¥{((a-l)/1000000).toFixed(2)}M · {its.length} items</div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Summary tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>NET WORTH · 净资产</div>
          <div className="mono" style={{ fontSize: 38, fontWeight: 700, marginTop: 6 }}>
            ¥{(netWorth/1000000).toFixed(2)}<span style={{ fontSize: 18, color: "var(--ink-3)" }}>M</span>
          </div>
          {prev && (
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4, display: "flex", alignItems: "center", gap: 8 }}>
              <ChangeNum value={deltaPct} size="sm"/>
              <span>vs {prev.date} ({delta >= 0 ? "+" : "−"}¥{fmtNum(Math.abs(delta), 0)})</span>
            </div>
          )}
          {/* Net worth trend */}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
            <NetWorthTrend series={series} highlightId={snap.id}/>
          </div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL ASSETS · 资产</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--down)" }}>+¥{(totalAssets/1000000).toFixed(2)}M</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{itemsAll.filter(i=>i.side==="asset").length} 项 · {assetCats.length} 类</div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL LIABILITIES · 负债</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--up)" }}>−¥{(totalLiabilities/1000000).toFixed(2)}M</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{itemsAll.filter(i=>i.side==="liability").length} 项 · 负债率 {(totalLiabilities/totalAssets*100).toFixed(0)}%</div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>LIQUIDITY · 流动性</div>
          {(() => {
            const liquid = itemsAll.filter(i => i.side === "asset" && (i.category === "现金" || i.category === "投资")).reduce((s, i) => s + inCNY(i), 0);
            return (
              <>
                <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6 }}>¥{(liquid/1000000).toFixed(2)}M</div>
                <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>现金 + 投资 · {(liquid/totalAssets*100).toFixed(0)}% of assets</div>
              </>
            );
          })()}
        </Card>
      </div>

      {/* Category breakdowns */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 18 }}>
        <CategoryCard title="资产分类 Asset Breakdown" cats={assetCats} total={totalAssets} tone="down"/>
        <CategoryCard title="负债分类 Liability Breakdown" cats={liabCats} total={totalLiabilities} tone="up"/>
      </div>

      {/* Detail table */}
      <Card padding={0} style={{ marginBottom: 18 }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>明细 Items</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>每条记录可纳入一个或多个资产负债快照</div>
          </div>
          <Tabs variant="pill" value={side} onChange={setSide} tabs={[
            {id:"all", label:`全部 ${itemsAll.length}`},
            {id:"asset", label:`资产 ${itemsAll.filter(i=>i.side==="asset").length}`},
            {id:"liability", label:`负债 ${itemsAll.filter(i=>i.side==="liability").length}`},
          ]}/>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "1.4fr 110px 90px 130px 110px 1fr 120px 50px", gap: 10, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
          <span>NAME</span><span>CATEGORY</span><span>资产/负债</span>
          <span style={{ textAlign: "right" }}>AMOUNT</span>
          <span style={{ textAlign: "right" }}>≈ CNY</span>
          <span>NOTE</span>
          <span>SNAPSHOTS</span>
          <span></span>
        </div>
        {filtered.sort((a,b) => inCNY(b) - inCNY(a)).map((it, i, arr) => {
          const cny = inCNY(it);
          return (
            <div key={it.id} style={{ display: "grid", gridTemplateColumns: "1.4fr 110px 90px 130px 110px 1fr 120px 50px", gap: 10, padding: "12px 18px", alignItems: "center", borderBottom: i < arr.length - 1 ? "1px solid var(--line)" : "none", fontSize: 12.5 }}>
              <div>
                <div style={{ fontWeight: 600 }}>{it.name}</div>
                <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 2 }}>updated {it.updated}</div>
              </div>
              <span><span style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "2px 8px", background: BS_CAT_COLORS[it.category] + "1A", color: BS_CAT_COLORS[it.category], borderRadius: 4, fontSize: 11, fontWeight: 600 }}>{it.category}</span></span>
              <span><Badge tone={it.side === "asset" ? "down" : "up"} size="sm" solid={false}>{it.side === "asset" ? "资产" : "负债"}</Badge></span>
              <span className="mono" style={{ textAlign: "right", fontWeight: 600 }}>{fmtMoney(it.amount, it.currency, 0)}</span>
              <span className="mono" style={{ textAlign: "right", color: "var(--ink-3)" }}>¥{fmtNum(cny, 0)}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 12 }}>{it.note || "—"}</span>
              <span style={{ display: "flex", gap: 3, flexWrap: "wrap" }}>
                {it.inSnapshot.map(sid => {
                  const s = BS_SNAPSHOTS.find(s => s.id === sid);
                  const isCur = sid === snap.id;
                  return <span key={sid} className="mono" title={s.label} style={{
                    fontSize: 10, padding: "1px 5px", borderRadius: 3,
                    background: isCur ? "var(--ink)" : "var(--bg-deep)",
                    color: isCur ? "#fff" : "var(--ink-4)",
                  }}>{sid.replace("s","")}</span>;
                })}
              </span>
              <button style={{ width: 24, height: 24, background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-4)" }}><Icon name="edit" size={13}/></button>
            </div>
          );
        })}
      </Card>

      {/* FIRE projection moved to its own MODULE 05 page */}

      <ComingSoonBanner module="Balance Sheet" features={["定期提醒梳理", "差异审计 / item drift", "汇率历史折算", "导出 PDF 报告"]}/>
    </div>
  );
};

// =============================================================================
const CategoryCard = ({ title, cats, total, tone }) => (
  <Card padding={20}>
    <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>{title}</div>
    {/* segmented bar */}
    <div style={{ display: "flex", height: 10, borderRadius: 5, overflow: "hidden", marginBottom: 14, background: "var(--bg-deep)" }}>
      {cats.map(c => <div key={c.label} style={{ flex: c.value, background: c.color }} title={`${c.label} ¥${fmtNum(c.value,0)}`}/>)}
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
      {cats.map(c => {
        const pct = (c.value / total) * 100;
        return (
          <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 0" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: c.color, flexShrink: 0 }}/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>{c.label} <span style={{ color: "var(--ink-4)", fontWeight: 400 }}>· {c.count}</span></div>
              <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>¥{fmtNum(c.value/1000, 1)}k <span style={{ color: "var(--ink-4)" }}>· {pct.toFixed(0)}%</span></div>
            </div>
          </div>
        );
      })}
    </div>
  </Card>
);

// =============================================================================
const NetWorthTrend = ({ series, highlightId }) => {
  const W = 380, H = 90, pad = 14;
  const max = Math.max(...series.map(s => s.assets));
  const min = Math.min(0, ...series.map(s => -s.liabilities));
  const range = max - min || 1;
  const x = (i) => pad + (i / (series.length - 1)) * (W - pad*2);
  const y = (v) => pad + (1 - (v - min) / range) * (H - pad*2);

  const netPath = "M " + series.map((s, i) => `${x(i).toFixed(1)},${y(s.net).toFixed(1)}`).join(" L ");
  const fillPath = netPath + ` L ${x(series.length - 1).toFixed(1)},${y(0).toFixed(1)} L ${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const hi = series.findIndex(s => s.id === highlightId);

  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 6 }}>HISTORY · {series.length} 个快照</div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
        <line x1={pad} x2={W-pad} y1={y(0)} y2={y(0)} stroke="var(--line-2)" strokeDasharray="2 3"/>
        <path d={fillPath} fill="var(--ink)" fillOpacity=".06"/>
        <path d={netPath} stroke="var(--ink)" strokeWidth="1.8" fill="none"/>
        {series.map((s, i) => (
          <circle key={s.id} cx={x(i)} cy={y(s.net)} r={i === hi ? 4 : 2.5} fill={i === hi ? "var(--up)" : "var(--ink)"} stroke="#fff" strokeWidth="1"/>
        ))}
      </svg>
    </div>
  );
};

window.BalanceSheet = BalanceSheet;
