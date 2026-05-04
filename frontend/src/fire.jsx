/* Module 05 — FIRE 退休计划 (extracted from Balance Sheet)
   Standalone page: header + KPI tiles + chart + parameters + milestones
   Net worth is read from the latest balance-sheet snapshot.
*/

const Fire = () => {
  // Pull current net worth from latest balance-sheet snapshot
  const latest = BS_SNAPSHOTS[BS_SNAPSHOTS.length - 1];
  const items = BS_ITEMS.filter(it => it.inSnapshot.includes(latest.id));
  const inCNY = (it) => it.amount * (FX[it.currency] || 1);
  const assets      = items.filter(i => i.side === "asset")    .reduce((s, i) => s + inCNY(i), 0);
  const liabilities = items.filter(i => i.side === "liability").reduce((s, i) => s + inCNY(i), 0);
  const netWorth = assets - liabilities;

  const [age, setAge] = React.useState(32);
  const [monthlyExp, setMonthlyExp] = React.useState(15000);
  const [cagr, setCagr] = React.useState(10);
  const [monthly, setMonthly] = React.useState(8000);
  const [scenario, setScenario] = React.useState("base"); // base | conservative | aggressive

  const fireNumber = monthlyExp * 12 * 25;
  const project = React.useMemo(() => {
    const out = [];
    let v = netWorth;
    let yr = age;
    while (yr <= 75) {
      out.push({ age: yr, value: v });
      v = v * (1 + cagr/100) + monthly * 12;
      yr++;
    }
    return out;
  }, [netWorth, cagr, age, monthly]);

  const fireYear = project.find(p => p.value >= fireNumber);
  const fireAge = fireYear ? fireYear.age : null;
  const yearsToFire = fireAge ? fireAge - age : null;

  // Scenario presets
  const applyScenario = (s) => {
    setScenario(s);
    if (s === "conservative") { setCagr(6);  setMonthly(6000);  }
    if (s === "base")         { setCagr(10); setMonthly(8000);  }
    if (s === "aggressive")   { setCagr(13); setMonthly(12000); }
  };

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 05 · FIRE"
        title="FIRE 退休计划"
        subtitle="Financial Independence, Retire Early · 月投入 + 复利 · 25× 年支出法则 · 净资产取自资产负债最新快照"
        right={
          <div style={{ display: "flex", gap: 6, padding: 3, background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 7 }}>
            {[
              { id: "conservative", label: "保守 6%" },
              { id: "base",         label: "基准 10%" },
              { id: "aggressive",   label: "激进 13%" },
            ].map(s => (
              <button key={s.id} onClick={() => applyScenario(s.id)} style={{
                padding: "5px 10px", fontSize: 11.5, fontWeight: 500, border: "none",
                background: scenario === s.id ? "var(--ink)" : "transparent",
                color: scenario === s.id ? "#fff" : "var(--ink-3)",
                borderRadius: 5, cursor: "pointer",
              }}>{s.label}</button>
            ))}
          </div>
        }
      />

      {/* KPI tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 14 }}>
        <FireTile label="FIRE NUMBER" value={`¥${(fireNumber/1000000).toFixed(1)}M`} sub="25× 年支出"/>
        <FireTile label="CURRENT" value={`¥${(netWorth/1000000).toFixed(2)}M`} sub={`${(netWorth/fireNumber*100).toFixed(0)}% 已达成 · 来自 ${latest.label}`}/>
        <FireTile label="FIRE AGE" value={fireAge ? `${fireAge}` : "—"} sub={fireAge ? `${yearsToFire}y from now` : "Out of range"} accent={fireAge ? "var(--up)" : "var(--down)"}/>
        <FireTile label="EXPECTED CAGR" value={`${cagr.toFixed(1)}%`} sub="预期年化收益"/>
      </div>

      {/* Chart + Parameters */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card padding={20}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>净资产时间轴 Net Worth Timeline</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Projected · age {age}–75</div>
            </div>
            <div style={{ display: "flex", gap: 10, fontSize: 11 }}>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 14, height: 2, background: "var(--ink)" }}/>Projection</span>
              <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><span style={{ width: 14, height: 2, background: "var(--up)", borderTop: "1px dashed var(--up)" }}/>FIRE target</span>
            </div>
          </div>
          <FireChart data={project} fireNumber={fireNumber} fireAge={fireAge}/>
        </Card>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700, marginBottom: 14 }}>参数 Parameters</div>
          <FireSlider label="当前年龄" value={age} onChange={setAge} min={20} max={60} suffix="岁"/>
          <FireSlider label="月支出" value={monthlyExp} onChange={setMonthlyExp} min={3000} max={50000} step={500} suffix="¥"/>
          <FireSlider label="预期年化 CAGR" value={cagr} onChange={setCagr} min={3} max={20} step={0.5} suffix="%"/>
          <FireSlider label="月度投入" value={monthly} onChange={setMonthly} min={0} max={30000} step={500} suffix="¥"/>
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
            <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 6, textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>当前净资产</div>
            <div className="mono" style={{ fontSize: 18, fontWeight: 700 }}>¥{(netWorth/1000000).toFixed(2)}M</div>
            <div style={{ fontSize: 11, color: "var(--ink-4)" }}>自动取自资产负债最新快照 · {latest.label}</div>
          </div>
        </Card>
      </div>

      {/* Milestones */}
      <div style={{ marginTop: 14 }}>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 14 }}>关键里程碑 Milestones</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
            {[
              { label: "Lean FIRE", multiplier: 15, color: "var(--info)",   blurb: "极简退休 · 仅覆盖基本生活" },
              { label: "FIRE",      multiplier: 25, color: "var(--up)",     blurb: "标准退休 · 维持当前生活水准" },
              { label: "Fat FIRE",  multiplier: 40, color: "var(--warn)",   blurb: "充裕退休 · 旅行 + 通胀缓冲" },
              { label: "Coast FIRE",multiplier: 12, color: "var(--violet)", blurb: "停止投入 · 复利达到 FIRE 即可" },
            ].map(m => {
              const target = monthlyExp * 12 * m.multiplier;
              const yr = project.find(p => p.value >= target);
              const reached = yr && yr.age <= age + 60;
              return (
                <div key={m.label} style={{ background: "var(--paper-2)", border: "1px solid var(--line)", borderRadius: 10, padding: 14 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: m.color }}/>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{m.label}</span>
                    <span className="mono" style={{ fontSize: 9.5, color: "var(--ink-4)", marginLeft: "auto" }}>{m.multiplier}×</span>
                  </div>
                  <div className="mono" style={{ fontSize: 18, fontWeight: 700, marginTop: 6 }}>¥{(target/1000000).toFixed(1)}M</div>
                  <div style={{ fontSize: 11, color: reached ? "var(--up)" : "var(--ink-3)", marginTop: 2, fontWeight: reached ? 500 : 400 }}>
                    {yr ? `→ age ${yr.age} · ${yr.age - age}y` : "Out of range"}
                  </div>
                  <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 4, lineHeight: 1.4 }}>{m.blurb}</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      {/* Withdrawal scenarios */}
      <div style={{ marginTop: 14 }}>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 4 }}>提取率敏感性 Withdrawal Rate Sensitivity</div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 14 }}>不同提取率下的所需 FIRE 数字 · 当前月支出 ¥{fmtNum(monthlyExp,0)}</div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 10 }}>
            {[3.0, 3.5, 4.0, 4.5, 5.0].map(rate => {
              const required = (monthlyExp * 12) / (rate / 100);
              const yr = project.find(p => p.value >= required);
              const isStandard = rate === 4.0;
              return (
                <div key={rate} style={{
                  background: isStandard ? "var(--ink)" : "transparent",
                  color: isStandard ? "#fff" : "var(--ink)",
                  border: "1px solid " + (isStandard ? "var(--ink)" : "var(--line)"),
                  borderRadius: 8, padding: 12,
                }}>
                  <div className="mono" style={{ fontSize: 11, opacity: .7, fontWeight: 600 }}>SWR {rate.toFixed(1)}%</div>
                  <div className="mono" style={{ fontSize: 17, fontWeight: 700, marginTop: 4 }}>¥{(required/1000000).toFixed(1)}M</div>
                  <div style={{ fontSize: 10.5, opacity: .7, marginTop: 2 }}>{yr ? `age ${yr.age}` : "—"}</div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <ComingSoonBanner module="FIRE" features={["蒙特卡洛模拟", "通胀调整 (real return)", "提取阶段建模 4% rule", "税务影响 / 社保接续"]}/>
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

const FireChart = ({ data, fireNumber, fireAge }) => {
  const width = 800, height = 240;
  const padL = 50, padR = 16, padT = 16, padB = 30;
  const w = width - padL - padR, h = height - padT - padB;
  const max = Math.max(fireNumber * 1.1, ...data.map(d => d.value));
  const xs = (i) => padL + (i / (data.length - 1)) * w;
  const ys = (v) => padT + h - (v / max) * h;
  const path = "M " + data.map((d, i) => `${xs(i).toFixed(1)},${ys(d.value).toFixed(1)}`).join(" L ");
  const fill = path + ` L ${(padL + w).toFixed(1)},${(padT + h).toFixed(1)} L ${padL.toFixed(1)},${(padT + h).toFixed(1)} Z`;
  const fireY = ys(fireNumber);
  const fireIdx = data.findIndex(d => d.age === fireAge);
  return (
    <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {[0, .25, .5, .75, 1].map((p, i) => (
        <g key={i}>
          <line x1={padL} x2={padL+w} y1={padT + h - p*h} y2={padT + h - p*h} stroke="var(--line)" strokeDasharray="2 3"/>
          <text x={padL - 8} y={padT + h - p*h + 3} fontSize="10" fill="var(--ink-4)" textAnchor="end" className="mono">¥{((max*p)/1000000).toFixed(1)}M</text>
        </g>
      ))}
      <line x1={padL} x2={padL+w} y1={fireY} y2={fireY} stroke="var(--up)" strokeDasharray="4 3" strokeWidth="1.5"/>
      <text x={padL+w-4} y={fireY-5} fontSize="10" fill="var(--up)" textAnchor="end" fontWeight="600">FIRE ¥{(fireNumber/1000000).toFixed(1)}M</text>
      <path d={fill} fill="var(--ink)" fillOpacity=".06"/>
      <path d={path} stroke="var(--ink)" strokeWidth="2" fill="none"/>
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

window.Fire = Fire;
