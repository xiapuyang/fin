/* Charts — donut, bars, area, calendar heatmap. Pure SVG, no deps. */

// === Donut ================================================================
const Donut = ({ data, size = 220, thickness = 28, centerLabel, centerValue, centerSub }) => {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  const r = size / 2 - thickness / 2 - 2;
  const cx = size / 2, cy = size / 2;
  let cum = 0;
  const arcs = data.map((d, i) => {
    const start = (cum / total) * Math.PI * 2 - Math.PI / 2;
    cum += d.value;
    const end = (cum / total) * Math.PI * 2 - Math.PI / 2;
    const large = end - start > Math.PI ? 1 : 0;
    const x1 = cx + Math.cos(start) * r, y1 = cy + Math.sin(start) * r;
    const x2 = cx + Math.cos(end) * r, y2 = cy + Math.sin(end) * r;
    return { d: `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`, color: d.color, key: d.label || i };
  });
  return (
    <svg width={size} height={size} style={{ display: "block" }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--line)" strokeWidth={thickness} />
      {arcs.map(a => <path key={a.key} d={a.d} stroke={a.color} strokeWidth={thickness} fill="none" strokeLinecap="butt" />)}
      {centerValue && (
        <foreignObject x="0" y="0" width={size} height={size}>
          <div style={{ width: size, height: size, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", textAlign: "center" }}>
            {centerLabel && <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>{centerLabel}</div>}
            <div className="mono" style={{ fontSize: 28, fontWeight: 700, color: "var(--ink)", letterSpacing: "-.01em", marginTop: 2 }}>{centerValue}</div>
            {centerSub && <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{centerSub}</div>}
          </div>
        </foreignObject>
      )}
    </svg>
  );
};

// === Area chart ===========================================================
const AreaChart = ({ data, width = 560, height = 200, color = "var(--ink)", fillOpacity = .08, showAxis = true, yLabels = 4 }) => {
  if (!data || data.length < 2) return null;
  const padL = showAxis ? 44 : 4, padR = 8, padT = 12, padB = showAxis ? 22 : 4;
  const w = width - padL - padR, h = height - padT - padB;
  const min = Math.min(...data.map(d => d.value));
  const max = Math.max(...data.map(d => d.value));
  const range = max - min || 1;
  const step = w / (data.length - 1);
  const pts = data.map((d, i) => [padL + i * step, padT + h - ((d.value - min) / range) * h]);
  const path = "M " + pts.map(p => p.map(v => v.toFixed(1)).join(",")).join(" L ");
  const fill = path + ` L ${(padL + w).toFixed(1)},${(padT + h).toFixed(1)} L ${padL},${(padT + h).toFixed(1)} Z`;
  const yTicks = [];
  for (let i = 0; i <= yLabels; i++) {
    const v = min + (range * i) / yLabels;
    const y = padT + h - (i / yLabels) * h;
    yTicks.push({ v, y });
  }
  const xLabels = data.filter((_, i) => i % Math.ceil(data.length / 6) === 0);
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {showAxis && yTicks.map((t, i) => (
        <g key={i}>
          <line x1={padL} x2={padL + w} y1={t.y} y2={t.y} stroke="var(--line)" strokeDasharray="2 3" />
          <text x={padL - 6} y={t.y + 3} fontSize="10" fill="var(--ink-4)" textAnchor="end" className="mono">{Math.round(t.v).toLocaleString()}</text>
        </g>
      ))}
      <path d={fill} fill={color} fillOpacity={fillOpacity} />
      <path d={path} stroke={color} strokeWidth="2" fill="none" />
      {pts.filter((_, i) => i === pts.length - 1).map((p, i) => (
        <circle key={i} cx={p[0]} cy={p[1]} r="3.5" fill={color}/>
      ))}
      {showAxis && xLabels.map((d, i) => {
        const idx = data.indexOf(d);
        const x = padL + idx * step;
        return <text key={i} x={x} y={height - 6} fontSize="10" fill="var(--ink-4)" textAnchor="middle" className="mono">{d.label}</text>;
      })}
    </svg>
  );
};

// === Bar chart ============================================================
const BarChart = ({ data, width = 560, height = 180, color = "var(--ink)", showAxis = true }) => {
  const padL = showAxis ? 44 : 4, padR = 8, padT = 8, padB = 22;
  const w = width - padL - padR, h = height - padT - padB;
  const max = Math.max(...data.map(d => Math.abs(d.value))) || 1;
  const bw = w / data.length * 0.7;
  const gap = w / data.length * 0.3;
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      {showAxis && [0, .25, .5, .75, 1].map((p, i) => (
        <line key={i} x1={padL} x2={padL + w} y1={padT + h - p * h} y2={padT + h - p * h} stroke="var(--line)" strokeDasharray="2 3"/>
      ))}
      {data.map((d, i) => {
        const x = padL + i * (bw + gap) + gap / 2;
        const bh = (Math.abs(d.value) / max) * h;
        const y = padT + h - bh;
        const c = d.color || color;
        return (
          <g key={i}>
            <rect x={x} y={y} width={bw} height={bh} fill={c} rx="2"/>
            <text x={x + bw / 2} y={height - 6} fontSize="10" fill="var(--ink-4)" textAnchor="middle">{d.label}</text>
          </g>
        );
      })}
    </svg>
  );
};

// === Trigger timeline (for alerts module) =================================
const TriggerTimeline = ({ events, width = 560, height = 110, days = 14 }) => {
  const padL = 8, padR = 8, padB = 24;
  const w = width - padL - padR;
  const lineY = height - padB;
  const dayW = w / days;

  // Normalize to local midnight so events near day boundaries land correctly
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - days + 1);
  startDate.setHours(0, 0, 0, 0);

  // Group by dayIdx → { symbol → events[] }
  const evMap = {};
  events.forEach(e => {
    const d = new Date(e.time || e.date);
    d.setHours(0, 0, 0, 0);
    const dayIdx = Math.round((d - startDate) / 86400000);
    if (dayIdx < 0 || dayIdx >= days) return;
    if (!evMap[dayIdx]) evMap[dayIdx] = {};
    if (!evMap[dayIdx][e.code]) evMap[dayIdx][e.code] = [];
    evMap[dayIdx][e.code].push(e);
  });

  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <line x1={padL} x2={padL + w} y1={lineY} y2={lineY} stroke="var(--line-2)" strokeWidth="1"/>
      {Array.from({ length: days }).map((_, i) => {
        const d = new Date(startDate);
        d.setDate(startDate.getDate() + i);
        const isWeekend = d.getDay() === 0 || d.getDay() === 6;
        const cx = padL + i * dayW + dayW / 2;
        const symGroups = evMap[i] || {};
        const syms = Object.keys(symGroups);
        // Show label on first, last, and every other day
        const showLabel = i === 0 || i === days - 1 || i % 2 === 0;
        return (
          <g key={i}>
            <line x1={cx} x2={cx} y1={lineY - 3} y2={lineY + 3}
              stroke={isWeekend ? "var(--ink-5)" : "var(--ink-4)"} strokeWidth="1"/>
            {showLabel && (
              <text x={cx} y={lineY + 14} fontSize="9.5" fill="var(--ink-4)" textAnchor="middle" className="mono">
                {(d.getMonth() + 1) + "/" + d.getDate()}
              </text>
            )}
            {syms.map((sym, si) => {
              const evs = symGroups[sym];
              const isUp = evs[0].cond === "price_gte" || evs[0].cond === "change_gte";
              const color = isUp ? "var(--up)" : "var(--down)";
              const count = evs.length;
              const dotY = lineY - 18 - si * 26;
              const tip = evs.map(e =>
                `${e.code}  ${e.name}  @${e.time}\nprice ${e.actual?.toFixed(2)}  chg ${e.change_pct?.toFixed(2)}%`
              ).join("\n");
              return (
                <g key={sym}>
                  <title>{tip}</title>
                  <line x1={cx} x2={cx} y1={lineY} y2={dotY + 6} stroke={color} strokeWidth="1.5" opacity="0.4"/>
                  <circle cx={cx} cy={dotY} r={count > 1 ? 8 : 5.5} fill={color}/>
                  {count > 1
                    ? <text x={cx} y={dotY + 4} fontSize="8.5" fill="white" textAnchor="middle" fontWeight="700">{count}</text>
                    : null}
                  <text x={cx} y={dotY - 11} fontSize="9" fill={color} textAnchor="middle" fontWeight="600" className="mono">{sym}</text>
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
};

// === Progress ring =========================================================
const ProgressRing = ({ value = 0, size = 56, thickness = 5, color = "var(--ink)" }) => {
  const r = size / 2 - thickness / 2;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(1, value)));
  return (
    <svg width={size} height={size} style={{ display: "block", transform: "rotate(-90deg)" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="var(--line)" strokeWidth={thickness}/>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={thickness} strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round" style={{ transition: "stroke-dashoffset .4s ease" }}/>
    </svg>
  );
};

// === Stacked bar ==========================================================
const StackedBar = ({ data, width = 560, height = 18, gap = 2 }) => {
  const total = data.reduce((s, d) => s + d.value, 0) || 1;
  let acc = 0;
  return (
    <div style={{ display: "flex", width, height, gap, borderRadius: 4, overflow: "hidden" }}>
      {data.map((d, i) => {
        const w = (d.value / total) * (width - gap * (data.length - 1));
        return <div key={i} title={`${d.label} ${(d.value/total*100).toFixed(0)}%`} style={{ width: w, height: "100%", background: d.color, borderRadius: 2 }}/>;
      })}
    </div>
  );
};

Object.assign(window, { Donut, AreaChart, BarChart, TriggerTimeline, ProgressRing, StackedBar });
