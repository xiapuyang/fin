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

const _LINE_COLORS = ["#e5484d", "#3b82f6", "#f59e0b", "#8b5cf6", "#06b6d4", "#10b981", "#f43f5e"];

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
  const padT = 14, padR = 16, padB = 30, padL = 44;
  const w = width - padL - padR;
  const h = height - padT - padB;

  const allDates = [...new Set(series.flatMap(s => s.data.map(d => d.date)))].sort();
  if (allDates.length === 0) return <svg width={width} height={height}/>;

  const allValues = series.flatMap(s => s.data.map(d => d.xirr).filter(v => v != null));
  if (allValues.length === 0) return <svg width={width} height={height}/>;

  const minV = Math.min(...allValues);
  const maxV = Math.max(...allValues);
  const vPad = (maxV - minV) * 0.12 || 2;
  const yMin = minV - vPad, yMax = maxV + vPad;

  // When there is only one date, center the single point horizontally
  const xOf = (date) => allDates.length === 1
    ? padL + w / 2
    : padL + (allDates.indexOf(date) / (allDates.length - 1)) * w;
  const yOf = (v) => padT + h - ((v - yMin) / Math.max(yMax - yMin, 0.0001)) * h;

  // y-axis ticks
  const yRange = yMax - yMin;
  const yStep = yRange <= 8 ? 2 : yRange <= 20 ? 5 : yRange <= 60 ? 10 : 20;
  const yTicks = [];
  for (let y = Math.ceil(yMin / yStep) * yStep; y <= yMax + 0.001; y += yStep) yTicks.push(y);

  // x-axis ticks: ~5 evenly spaced; always include all dates when few
  const xStep = Math.max(1, Math.floor(allDates.length / 5));
  const xTicks = allDates.filter((_, i) => i % xStep === 0 || i === allDates.length - 1);

  const _months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  const fmtX = (d) => {
    const parts = d.split("-");
    // Single-point: show exact date; handle both YYYY-MM-DD and YYYY-MM formats
    if (allDates.length === 1) {
      const mo = _months[+parts[1] - 1];
      return parts[2] ? `${mo} ${+parts[2]}, ${parts[0]}` : `${mo} ${parts[0]}`;
    }
    if (granularity === "month") return `${_months[+parts[1]-1]} '${parts[0].slice(2)}`;
    return d.slice(5);
  };

  // Dedup-aware colors so no two series share a color within this chart
  const _colorMap = colorMap || nameColors(series.map(s => s.name));
  const seriesColor = (name) => _colorMap[name] || nameColor(name);

  return (
    <div>
      <svg width={width} height={height} style={{ display: "block", overflow: "visible" }}>
        {/* y-axis grid + labels */}
        {yTicks.map(y => (
          <g key={y}>
            <line x1={padL} x2={padL + w} y1={yOf(y)} y2={yOf(y)} stroke="var(--line)" strokeWidth="1" strokeDasharray="3,3"/>
            <text x={padL - 4} y={yOf(y) + 4} textAnchor="end" fontSize="9.5" fill="var(--ink-4)">
              {y > 0 ? `+${y}%` : `${y}%`}
            </text>
          </g>
        ))}
        {/* zero line (bold) */}
        {yMin < 0 && yMax > 0 && (
          <line x1={padL} x2={padL + w} y1={yOf(0)} y2={yOf(0)} stroke="var(--line-2)" strokeWidth="1.5"/>
        )}
        {/* x-axis labels */}
        {xTicks.map(d => (
          <text key={d} x={xOf(d)} y={padT + h + 16} textAnchor="middle" fontSize="9.5" fill="var(--ink-4)">{fmtX(d)}</text>
        ))}
        {/* series lines */}
        {series.map((s) => {
          const color = seriesColor(s.name);
          const pts = s.data.filter(d => d.xirr != null).map(d => `${xOf(d.date)},${yOf(d.xirr)}`).join(" ");
          return pts ? <polyline key={s.id} points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round"/> : null;
        })}
        {/* terminal dots */}
        {series.map((s) => {
          const color = seriesColor(s.name);
          const last = s.data.filter(d => d.xirr != null).at(-1);
          return last ? <circle key={s.id} cx={xOf(last.date)} cy={yOf(last.xirr)} r={3} fill={color}/> : null;
        })}
        {/* value labels next to terminal dots */}
        {series.map((s) => {
          const color = seriesColor(s.name);
          const last = s.data.filter(d => d.xirr != null).at(-1);
          if (!last) return null;
          const x = xOf(last.date);
          const y = yOf(last.xirr);
          const label = `${last.xirr >= 0 ? "+" : ""}${last.xirr.toFixed(1)}%`;
          return <text key={`lbl-${s.id}`} x={x + 6} y={y + 4} fontSize="9" fill={color} fontFamily="monospace">{label}</text>;
        })}
      </svg>
      {/* legend row — names only; values shown on dots */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 16px", marginTop: 6, paddingLeft: padL }}>
        {series.map((s) => {
          const color = seriesColor(s.name);
          return (
            <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-3)" }}>
              <div style={{ width: 8, height: 8, borderRadius: 2, background: color, flexShrink: 0 }}/>
              <span>{s.name}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

Object.assign(window, { Donut, AreaChart, BarChart, TriggerTimeline, ProgressRing, StackedBar, MultiLineChart, nameColor, nameColors });
