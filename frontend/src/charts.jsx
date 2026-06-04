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
            <div className="mono" style={{ fontSize: centerValue.length > 10 ? 13 : centerValue.length > 7 ? 16 : 22, fontWeight: 700, color: "var(--ink)", letterSpacing: "-.01em", marginTop: 2 }}>{centerValue}</div>
            {centerSub && <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{centerSub}</div>}
          </div>
        </foreignObject>
      )}
    </svg>
  );
};

// === Area chart ===========================================================
const AreaChart = ({ data, width = 560, height = 200, color = "var(--ink)", fillOpacity = .08, showAxis = true, yLabels = 4, yFormat }) => {
  if (!data || data.length < 2) return null;
  const padL = showAxis ? 56 : 4, padR = 8, padT = 12, padB = showAxis ? 22 : 4;
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
          <text x={padL - 6} y={t.y + 3} fontSize="10" fill="var(--ink-4)" textAnchor="end" className="mono">{yFormat ? yFormat(t.v) : Math.round(t.v).toLocaleString()}</text>
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
        const isLast = idx === data.length - 1;
        return <text key={i} x={x} y={height - 6} fontSize="10" fill="var(--ink-4)" textAnchor={isLast ? "end" : "middle"} className="mono">{d.label}</text>;
      })}
    </svg>
  );
};

// === Bar chart ============================================================
const _fmtBarK = (v) => {
  if (v >= 1000000) return (v / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
  if (v >= 10000) return (v / 1000).toFixed(0) + "k";
  if (v >= 1000) return (v / 1000).toFixed(1).replace(/\.0$/, "") + "k";
  return v.toFixed(2);
};

// CJK-aware visual width (each CJK char counts as 2)
const _cjkW = (s) => [...(s||"")].reduce((n, c) => n + (c.charCodeAt(0) > 0x2E7F ? 2 : 1), 0);

// Wrap a single space-free token; never splits a run of [0-9%/.] mid-way
const _wrapWord = (w, maxW) => {
  const lines = []; let line = "", lineW = 0, numRunStart = -1;
  for (const c of w) {
    const cw = c.charCodeAt(0) > 0x2E7F ? 2 : 1;
    const isNum = /[0-9%\/.]/.test(c);
    if (!isNum) numRunStart = -1;
    else if (numRunStart < 0) numRunStart = line.length;
    if (lineW + cw > maxW && lineW > 0) {
      if (numRunStart > 0) {
        // back up to before the number run started
        const carry = line.slice(numRunStart);
        lines.push(line.slice(0, numRunStart));
        line = carry + c; lineW = _cjkW(line); numRunStart = 0;
      } else {
        lines.push(line); line = c; lineW = cw; numRunStart = isNum ? 0 : -1;
      }
    } else { line += c; lineW += cw; }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [w];
};

// Wrap string into lines of at most maxW visual units.
// Breaks at spaces first; falls back to _wrapWord for tokens that still exceed maxW.
const _wrapLabel = (s, maxW = 10) => {
  const words = s.split(" ").filter(Boolean);
  const lines = []; let line = "", lineW = 0;
  for (const word of words) {
    const ww = _cjkW(word);
    if (lineW === 0) {
      if (ww > maxW) {
        const sub = _wrapWord(word, maxW);
        for (let i = 0; i < sub.length - 1; i++) lines.push(sub[i]);
        line = sub[sub.length - 1]; lineW = _cjkW(line);
      } else { line = word; lineW = ww; }
    } else if (lineW + 1 + ww <= maxW) {
      line += " " + word; lineW += 1 + ww;
    } else {
      lines.push(line);
      if (ww > maxW) {
        const sub = _wrapWord(word, maxW);
        for (let i = 0; i < sub.length - 1; i++) lines.push(sub[i]);
        line = sub[sub.length - 1]; lineW = _cjkW(line);
      } else { line = word; lineW = ww; }
    }
  }
  if (line) lines.push(line);
  return lines.length ? lines : [""];
};

const BarChart = ({ data, width = 560, height = 180, color = "var(--ink)", showAxis = true, signed = false }) => {
  const padL = showAxis ? 44 : 4, padR = 8, padT = 20;
  const sqSz = 8, sqGap = 4, lineH = 12;

  if (signed) {
    // Pre-compute wrapped labels to size padB dynamically
    const wrappedLabels = data.map(d => _wrapLabel(d.label));
    const maxLines = Math.max(...wrappedLabels.map(ls => ls.length));
    const padB = 18 + maxLines * lineH;
    const hasTopLabels = data.some(d => d.topLabel);
    const padT = hasTopLabels ? 34 : 20;
    const svgH = height + (maxLines - 1) * lineH;
    const w = width - padL - padR, h = svgH - padT - padB;
    const bw = Math.min(w / data.length * 0.7, 48);
    const gap = w / data.length - bw;
    const maxAbs = Math.max(...data.map(d => Math.abs(d.value ?? 0))) || 1;
    const zeroY = padT + h / 2;

    return (
      <svg width={width} height={svgH} style={{ display: "block" }}>
        {showAxis && (
          <line x1={padL} x2={padL + w} y1={zeroY} y2={zeroY} stroke="var(--line-2)" strokeWidth="1"/>
        )}
        {data.map((d, i) => {
          const x = padL + i * (bw + gap) + gap / 2;
          const cx = x + bw / 2;
          const v = d.value ?? 0;
          const bh = (Math.abs(v) / maxAbs) * (h / 2);
          const isNeg = v < 0;
          const barY = isNeg ? zeroY : zeroY - bh;
          const c = d.color || (isNeg ? "var(--down)" : color);
          const labelText = d.value == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;
          const rawValueY = isNeg ? zeroY + bh + 11 : barY - 3;
          const valueY = Math.min(rawValueY, zeroY - 3);
          const lines = wrappedLabels[i];
          const widestLine = Math.max(...lines.map(_cjkW));
          const groupW = sqSz + sqGap + widestLine * 3.8;
          const groupX = cx - groupW / 2;
          const baseY = height - padB + lineH - 2;
          return (
            <g key={i}>
              {bh > 0 && <rect x={x} y={barY} width={bw} height={bh} fill={c} rx="2"/>}
              {d.topLabel && (
                <text x={cx} y={valueY - 12} fontSize="8.5" fill="var(--ink-3)" textAnchor="middle" className="mono">
                  {d.topLabel}
                </text>
              )}
              <text x={cx} y={valueY} fontSize="9.5" fill={c} textAnchor="middle" className="mono">
                {labelText}
              </text>
              {d.color && <rect x={groupX} y={baseY - sqSz + 1} width={sqSz} height={sqSz} fill={d.color} rx="1"/>}
              <text fontSize="10" fill="var(--ink-4)" textAnchor="start">
                {lines.map((l, li) => (
                  <tspan key={li} x={groupX + sqSz + sqGap} dy={li === 0 ? baseY : lineH}>{l}</tspan>
                ))}
              </text>
            </g>
          );
        })}
      </svg>
    );
  }

  const padB = 22;
  const w = width - padL - padR, h = height - padT - padB;
  const bw = Math.min(w / data.length * 0.7, 48);
  const gap = w / data.length - bw;

  const max = Math.max(...data.map(d => Math.abs(d.value))) || 1;
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
            {d.value > 0 && (
              <text x={x + bw / 2} y={y - 3} fontSize="9.5" fill="var(--ink-3)" textAnchor="middle" className="mono">
                {_fmtBarK(d.value)}
              </text>
            )}
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

// === Multi-series line chart (for benchmark history) =========================

const _LINE_COLORS = [
  "#3b82f6", // blue
  "#e5484d", // red
  "#10b981", // emerald
  "#f59e0b", // amber
  "#8b5cf6", // purple
  "#06b6d4", // cyan
  "#f97316", // orange
  "#ec4899", // pink
  "#84cc16", // lime
  "#14b8a6", // teal
  "#6366f1", // indigo
  "#f43f5e", // rose
  "#a78bfa", // violet
  "#22d3ee", // sky
  "#fbbf24", // yellow
];

// Deterministic color from series name — consistent across chart types and rerenders
const nameColor = (name) => {
  let h = 5381;
  for (let i = 0; i < name.length; i++) h = ((h << 5) - h + name.charCodeAt(i)) | 0;
  return _LINE_COLORS[Math.abs(h) % _LINE_COLORS.length];
};

// Dedup-aware color map for a set of names. Each name gets its preferred hash
// color if available; collisions get the next unused color in the palette.
const nameColors = (names) => {
  const used = new Set();
  const result = {};
  // First pass: claim preferred colors
  for (const name of names) {
    const c = nameColor(name);
    if (!used.has(c)) { result[name] = c; used.add(c); }
  }
  // Second pass: resolve collisions with the next available color
  for (const name of names) {
    if (result[name]) continue;
    for (const c of _LINE_COLORS) {
      if (!used.has(c)) { result[name] = c; used.add(c); break; }
    }
    if (!result[name]) result[name] = nameColor(name); // palette exhausted
  }
  return result;
};

const MultiLineChart = ({ series = [], width = 600, height = 200, granularity = "month", colorMap = null }) => {
  const [hover, setHover] = React.useState(null);
  const [hidden, setHidden] = React.useState(new Set());
  const clipId = React.useRef("mlc-" + Math.random().toString(36).slice(2, 7)).current;

  const toggleSeries = (id) => setHidden(h => {
    const next = new Set(h);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  const padT = 14, padR = 16, padB = 30, padL = 44;
  const w = width - padL - padR;
  const h = height - padT - padB;

  // Only visible series affect axis scale
  const visible = series.filter(s => !hidden.has(s.id));
  const allDates = [...new Set(visible.flatMap(s => s.data.map(d => d.date)))].sort();
  if (allDates.length === 0) return <svg width={width} height={height}/>;

  const allValues = visible.flatMap(s => s.data.map(d => d.xirr).filter(v => v != null));
  if (allValues.length === 0) return <svg width={width} height={height}/>;

  // Percentile fence: clip to p5–p95 so extreme early-period XIRR spikes
  // (when portfolio has few deposits, XIRR is very noisy) don't compress
  // the stable region. Lines outside the fence are clipped by SVG clipPath.
  const sv = [...allValues].sort((a, b) => a - b);
  const rawMin = Math.min(...allValues), rawMax = Math.max(...allValues);
  const p5  = sv[Math.max(0, Math.floor(sv.length * 0.05))];
  const p95 = sv[Math.min(sv.length - 1, Math.floor(sv.length * 0.95))];
  const pRange = Math.max(p95 - p5, 1);
  const fenceMin = p5  - pRange * 0.15;
  const fenceMax = p95 + pRange * 0.15;
  const minV = Math.max(rawMin, fenceMin);
  const maxV = Math.min(rawMax, fenceMax);
  const vPad = (maxV - minV) * 0.08 || 2;
  const yMin = minV - vPad, yMax = maxV + vPad;

  const dateIndex = new Map(allDates.map((d, i) => [d, i]));
  const xOf = (date) => allDates.length === 1
    ? padL + w / 2
    : padL + ((dateIndex.get(date) ?? 0) / (allDates.length - 1)) * w;
  const yOf = (v) => padT + h - ((v - yMin) / Math.max(yMax - yMin, 0.0001)) * h;

  const yRange = yMax - yMin;
  // Target ~7 gridlines; pick the smallest "nice" step that keeps ≤8 ticks.
  const _niceSteps = [1, 2, 5, 10, 20, 50, 100];
  const yStep = _niceSteps.find(s => yRange / s <= 8) || 100;
  const yTicks = [];
  for (let y = Math.ceil(yMin / yStep) * yStep; y <= yMax + 0.001; y += yStep) yTicks.push(y);

  const xStep = Math.max(1, Math.floor(allDates.length / 5));
  const xTicks = allDates.filter((_, i) => i % xStep === 0 || i === allDates.length - 1);

  const _months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const fmtX = (d) => {
    const parts = d.split("-");
    if (allDates.length === 1) {
      const mo = _months[+parts[1] - 1];
      return parts[2] ? `${mo} ${+parts[2]}, ${parts[0]}` : `${mo} ${parts[0]}`;
    }
    if (granularity === "month") return `${_months[+parts[1]-1]} '${parts[0].slice(2)}`;
    return d.slice(5);
  };

  const _colorMap = colorMap || nameColors(series.map(s => s.name));
  const seriesColor = (name) => _colorMap[name] || nameColor(name);

  // Per-date lookup for hover (includes hidden series in tooltip)
  const dateMap = React.useMemo(() => {
    const m = new Map();
    series.forEach(s => {
      if (hidden.has(s.id)) return;
      s.data.forEach(d => {
        if (d.xirr != null) {
          if (!m.has(d.date)) m.set(d.date, []);
          m.get(d.date).push({ name: s.name, color: seriesColor(s.name), xirr: d.xirr });
        }
      });
    });
    return m;
  }, [series, hidden]);

  const handleMouseMove = (e) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    let nearestIdx = 0, nearestDist = Infinity;
    allDates.forEach((d, i) => {
      const dist = Math.abs(mx - xOf(d));
      if (dist < nearestDist) { nearestDist = dist; nearestIdx = i; }
    });
    const date = allDates[nearestIdx];
    const entries = (dateMap.get(date) || []).slice().sort((a, b) => b.xirr - a.xirr);
    if (entries.length) setHover({ date, x: xOf(date), entries });
  };

  const TIP_W = 164;
  const tipEntries = hover ? hover.entries : [];
  const tipH = tipEntries.length * 17 + 22;
  const tipX = hover ? (hover.x + 8 + TIP_W > width ? hover.x - TIP_W - 8 : hover.x + 8) : 0;

  return (
    <div>
      <svg width={width} height={height} style={{ display: "block", overflow: "visible", cursor: "crosshair" }}
        onMouseMove={handleMouseMove} onMouseLeave={() => setHover(null)}>
        <defs>
          <clipPath id={clipId}>
            <rect x={padL} y={padT} width={w} height={h}/>
          </clipPath>
        </defs>
        {/* y-axis grid + labels */}
        {yTicks.map(y => (
          <g key={y}>
            <line x1={padL} x2={padL + w} y1={yOf(y)} y2={yOf(y)} stroke="var(--line)" strokeWidth="1" strokeDasharray="3,3"/>
            <text x={padL - 4} y={yOf(y) + 4} textAnchor="end" fontSize="9.5" fill="var(--ink-4)">
              {y > 0 ? `+${y}%` : `${y}%`}
            </text>
          </g>
        ))}
        {yMin < 0 && yMax > 0 && (
          <line x1={padL} x2={padL + w} y1={yOf(0)} y2={yOf(0)} stroke="var(--line-2)" strokeWidth="1.5"/>
        )}
        {xTicks.map(d => (
          <text key={d} x={xOf(d)} y={padT + h + 16} textAnchor="middle" fontSize="9.5" fill="var(--ink-4)">{fmtX(d)}</text>
        ))}
        {/* series lines — clipped to chart area */}
        <g clipPath={`url(#${clipId})`}>
          {visible.map((s) => {
            const color = seriesColor(s.name);
            const pts = s.data.filter(d => d.xirr != null).map(d => `${xOf(d.date)},${yOf(d.xirr)}`).join(" ");
            return pts ? <polyline key={s.id} points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/> : null;
          })}
        </g>
        {/* terminal dots + labels */}
        {!hover && visible.map((s) => {
          const color = seriesColor(s.name);
          const last = s.data.filter(d => d.xirr != null).at(-1);
          if (!last) return null;
          const cy = yOf(last.xirr);
          // Don't render terminal label if point is outside the clipped area
          if (cy < padT || cy > padT + h) return null;
          return (
            <g key={s.id}>
              <circle cx={xOf(last.date)} cy={cy} r={3} fill={color}/>
              <text x={xOf(last.date) + 6} y={cy + 4} fontSize="9" fill={color} fontFamily="monospace">
                {last.xirr >= 0 ? `+${last.xirr.toFixed(1)}` : last.xirr.toFixed(1)}%
              </text>
            </g>
          );
        })}
        {/* hover crosshair + tooltip */}
        {hover && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={padT} y2={padT + h}
              stroke="var(--ink-3)" strokeWidth="1" strokeDasharray="3,2" opacity="0.5"/>
            {tipEntries.map(e => {
              const cy = yOf(e.xirr);
              return (cy >= padT && cy <= padT + h)
                ? <circle key={e.name} cx={hover.x} cy={cy} r={3.5} fill={e.color}/>
                : null;
            })}
            <g transform={`translate(${tipX},${padT + 2})`}>
              <rect width={TIP_W} height={tipH} rx={5} fill="var(--paper)"
                stroke="var(--line-2)" strokeWidth="1" style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,.08))" }}/>
              <text x={7} y={15} fontSize="9.5" fill="var(--ink-3)" fontFamily="monospace">
                {(() => {
                  const p = hover.date.split("-");
                  return p.length === 2
                    ? `${_months[+p[1]-1]} ${p[0]}`
                    : `${_months[+p[1]-1]} ${+p[2]}, ${p[0]}`;
                })()}
              </text>
              {tipEntries.map((e, i) => (
                <g key={e.name} transform={`translate(7,${20 + i * 17})`}>
                  <rect width={7} height={7} rx={1.5} y={0} fill={e.color}/>
                  <text x={11} y={7.5} fontSize="10" fill="var(--ink-2)">{e.name}</text>
                  <text x={TIP_W - 10} y={7.5} fontSize="10" fill={e.color}
                    textAnchor="end" fontFamily="monospace" fontWeight="600">
                    {e.xirr >= 0 ? `+${e.xirr.toFixed(1)}` : e.xirr.toFixed(1)}%
                  </text>
                </g>
              ))}
            </g>
          </g>
        )}
      </svg>
      {/* clickable legend — click to hide/show a series */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", marginTop: 6, paddingLeft: padL }}>
        {series.map((s) => {
          const color = seriesColor(s.name);
          const isHidden = hidden.has(s.id);
          return (
            <div key={s.id} onClick={() => toggleSeries(s.id)}
              style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, cursor: "pointer",
                color: isHidden ? "var(--ink-4)" : "var(--ink-3)",
                opacity: isHidden ? 0.45 : 1, userSelect: "none" }}>
              <div style={{ width: 8, height: 8, borderRadius: 2,
                background: isHidden ? "var(--ink-4)" : color, flexShrink: 0 }}/>
              <span style={{ textDecoration: isHidden ? "line-through" : "none" }}>{s.name}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

// ── XIRR Range Chart ─────────────────────────────────────────────────────────
// Horizontal range bars showing min–max XIRR per scheme with current value dot.
const _fmtMonthDate = (d) => {
  if (!d) return "";
  const _mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  if (d.length === 7) { const [y,m] = d.split("-"); return `${_mn[+m-1]} '${y.slice(2)}`; }
  const [y,m,day] = d.split("-"); return `${_mn[+m-1]} ${+day} '${y.slice(2)}`;
};

const XirrRangeChart = ({ series = [], currentMap = {}, colorMap = null, width = 560 }) => {
  const [hidden, setHidden] = React.useState(new Set());
  const toggle = (id) => setHidden(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s; });

  if (!series.length) return null;

  // Compute per-series stats for ALL rows (so hidden rows still appear in legend)
  const allRows = series.map(s => {
    const pts = s.data.filter(d => d.xirr != null);
    if (!pts.length) return null;
    const minPt = pts.reduce((a, b) => b.xirr < a.xirr ? b : a);
    const maxPt = pts.reduce((a, b) => b.xirr > a.xirr ? b : a);
    return { id: s.id, name: s.name, min: minPt.xirr, minDate: minPt.date, max: maxPt.xirr, maxDate: maxPt.date, current: currentMap[s.id] ?? null };
  }).filter(Boolean);

  if (!allRows.length) return null;

  const allDates = series.flatMap(s => s.data.map(d => d.date)).filter(Boolean).sort();
  const rangeStart = allDates[0], rangeEnd = allDates[allDates.length - 1];

  // x-axis range: IQR fence (Q3 + 1.5×IQR) to prevent one outlier stretching the axis
  const visibleRows = allRows.filter(r => !hidden.has(r.id));
  const axisVals = visibleRows.flatMap(r => [r.min, r.max, r.current].filter(v => v != null)).sort((a, b) => a - b);
  if (!axisVals.length) return null;
  const q1 = axisVals[Math.floor(axisVals.length * 0.25)];
  const q3 = axisVals[Math.floor(axisVals.length * 0.75)];
  const iqr = Math.max(q3 - q1, 1);
  const rawMin = axisVals[0], rawMax = axisVals[axisVals.length - 1];
  const fenceMax = q3 + 1.5 * iqr;
  const xMin = rawMin - (rawMax - rawMin) * 0.04;
  const xMax = Math.min(rawMax, fenceMax) + (rawMax - rawMin) * 0.04;

  const _colorMap = colorMap || nameColors(allRows.map(r => r.name));
  const rowH = 38, padL = 132, padR = 52, barH = 8;
  const chartW = width - padL - padR;
  // bottom: 36px for ticks + 28px for caption gap
  const svgH = allRows.length * rowH + 36 + 28;

  const xOf = v => padL + ((v - xMin) / Math.max(xMax - xMin, 0.0001)) * chartW;
  const clampX = v => Math.min(Math.max(xOf(v), padL), padL + chartW);

  // x-axis ticks
  const axisRange = xMax - xMin;
  const step = axisRange <= 8 ? 2 : axisRange <= 20 ? 5 : axisRange <= 60 ? 10 : 20;
  const ticks = [];
  for (let t = Math.ceil(xMin / step) * step; t <= xMax + 0.001; t += step) ticks.push(t);
  const tickY = svgH - 36, captionY = svgH - 10;

  const _pct = (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`;

  return (
  <div>
    <svg width={width} height={svgH} style={{ display: "block", overflow: "visible" }}>
      {/* grid lines */}
      {ticks.map(t => (
        <g key={t}>
          <line x1={xOf(t)} x2={xOf(t)} y1={0} y2={tickY - 4} stroke="var(--line)" strokeWidth="1" strokeDasharray="3,3"/>
          {/* 0% label shifted right so it doesn't crowd left-side min labels */}
          <text x={t === 0 ? xOf(0) + 4 : xOf(t)} y={tickY + 10}
            textAnchor={t === 0 ? "start" : "middle"} fontSize="9" fill="var(--ink-4)">
            {t === 0 ? "0%" : _pct(t)}
          </text>
        </g>
      ))}
      {/* zero line */}
      {xMin < 0 && xMax > 0 && (
        <line x1={xOf(0)} x2={xOf(0)} y1={0} y2={tickY - 4} stroke="var(--line-2)" strokeWidth="1.5"/>
      )}
      {allRows.map((r, i) => {
        const isHidden = hidden.has(r.id);
        const cy = i * rowH + rowH / 2;
        const color = (_colorMap[r.name] || nameColor(r.name));
        const x1 = clampX(r.min);
        const rawX2 = xOf(r.max);
        const clipped = rawX2 > padL + chartW;
        const x2 = clipped ? padL + chartW : rawX2;
        const curX = r.current != null ? clampX(r.current) : null;
        const showMinLabel = (x1 - padL) > 24;
        return (
          <g key={r.id} style={{ cursor: "pointer" }} onClick={() => toggle(r.id)}>
            {/* row label — dot kept here as alignment anchor */}
            <text x={padL - 14} y={cy + 4} textAnchor="end" fontSize="10.5"
              fill={isHidden ? "var(--ink-4)" : "var(--ink-2)"}
              style={{ fontWeight: 500, textDecoration: isHidden ? "line-through" : "none" }}>
              {r.name}
            </text>
            {!isHidden && (<>
              {/* range bar */}
              <rect x={x1} y={cy - barH / 2} width={Math.max(x2 - x1, 2)} height={barH}
                rx={barH / 2} fill={color} opacity="0.22"/>
              {/* end caps — right cap omitted when clipped (arrow instead) */}
              <line x1={x1} x2={x1} y1={cy - barH/2 - 3} y2={cy + barH/2 + 3}
                stroke={color} strokeWidth="1.5" opacity="0.6"/>
              {!clipped && <line x1={x2} x2={x2} y1={cy - barH/2 - 3} y2={cy + barH/2 + 3}
                stroke={color} strokeWidth="1.5" opacity="0.6"/>}
              {/* min label — only when bar starts far enough from left edge */}
              {showMinLabel && <>
                <text x={x1 - 3} y={cy - 1} textAnchor="end" fontSize="8.5" fill={color} opacity="0.8" fontFamily="monospace">{_pct(r.min)}</text>
                <text x={x1 - 3} y={cy + 9} textAnchor="end" fontSize="7.5" fill={color} opacity="0.5" fontFamily="monospace">{_fmtMonthDate(r.minDate)}</text>
              </>}
              {/* max label + date — at clip edge if clipped, with → prefix */}
              <text x={x2 + 3} y={cy - 1} textAnchor="start" fontSize="8.5" fill={color} opacity="0.8" fontFamily="monospace">
                {clipped ? `→${_pct(r.max)}` : _pct(r.max)}
              </text>
              <text x={x2 + 3} y={cy + 9} textAnchor="start" fontSize="7.5" fill={color} opacity="0.5" fontFamily="monospace">{_fmtMonthDate(r.maxDate)}</text>
              {/* current XIRR dot */}
              {curX != null && (<>
                <circle cx={curX} cy={cy} r={5} fill={color}/>
                <text x={curX} y={cy - 8} textAnchor="middle" fontSize="8.5" fill={color} fontFamily="monospace" fontWeight="600">
                  {_pct(r.current)}
                </text>
              </>)}
            </>)}
          </g>
        );
      })}
      {/* date range caption below ticks */}
      {rangeStart && rangeEnd && (
        <text x={padL + chartW / 2} y={captionY} textAnchor="middle" fontSize="9" fill="var(--ink-4)">
          {_fmtMonthDate(rangeStart)} – {_fmtMonthDate(rangeEnd)}
        </text>
      )}
    </svg>
    {/* Legend — colored dots matching bar colors, click to hide/show */}
    <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", marginTop: 8, paddingLeft: padL }}>
      {allRows.map(r => {
        const color = (_colorMap[r.name] || nameColor(r.name));
        const isHidden = hidden.has(r.id);
        return (
          <div key={r.id}
            style={{ display: "flex", alignItems: "center", gap: 5, cursor: "pointer", opacity: isHidden ? 0.35 : 1 }}
            onClick={() => toggle(r.id)}>
            <div style={{ width: 9, height: 9, borderRadius: "50%", background: color, flexShrink: 0 }}/>
            <span style={{ fontSize: 11, color: "var(--ink-3)", textDecoration: isHidden ? "line-through" : "none" }}>{r.name}</span>
          </div>
        );
      })}
    </div>
  </div>
  );
};

Object.assign(window, { Donut, AreaChart, BarChart, TriggerTimeline, ProgressRing, StackedBar, MultiLineChart, XirrRangeChart, nameColor, nameColors });
