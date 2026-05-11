/* Atomic UI components — buttons, chips, badges, tabs, market dot, etc. */

const fmtNum = (n, dp = 2) => {
  if (n == null || isNaN(n)) return "—";
  return n.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: dp });
};
const fmtMoney = (n, ccy = "USD", dp = 2) => {
  const sym = { USD: "$", HKD: "HK$", CNY: "¥", CAD: "CA$" }[ccy] || "";
  if (n == null || isNaN(n)) return "—";
  const abs = Math.abs(n);
  return (n < 0 ? "−" : "") + sym + abs.toLocaleString("en-US", { minimumFractionDigits: dp, maximumFractionDigits: dp });
};
const fmtPct = (n, dp = 2) => {
  if (n == null || isNaN(n)) return "—";
  return (n > 0 ? "+" : "") + n.toFixed(dp) + "%";
};
const toCNY = (amount, ccy) => amount * (FX[ccy] || 1);

// === Market dot ============================================================
const MarketDot = ({ market, size = 8 }) => {
  const c = { US: "var(--us)", HK: "var(--hk)", CN: "var(--cn)", CA: "#C8531C" }[market] || "#999";
  return <span style={{ display: "inline-block", width: size, height: size, borderRadius: "50%", background: c, flexShrink: 0 }} />;
};

const MarketLabel = ({ market }) => {
  const t = { US: "美股 US", HK: "港股 HK", CN: "A股 CN", CA: "加股 CA" }[market] || market;
  return <span style={{ display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11, color: "var(--ink-3)", fontWeight: 500 }}><MarketDot market={market} /> {t}</span>;
};

// === Badge =================================================================
const Badge = ({ children, tone = "neutral", solid = false, size = "md" }) => {
  const tones = {
    neutral: { bg: "#EFEAE0", fg: "#2C3038", solid: { bg: "#2C3038", fg: "#fff" } },
    up:      { bg: "var(--up-soft)", fg: "var(--up-ink)", solid: { bg: "var(--up)", fg: "#fff" } },
    down:    { bg: "var(--down-soft)", fg: "var(--down-ink)", solid: { bg: "var(--down)", fg: "#fff" } },
    info:    { bg: "var(--info-soft)", fg: "#1438A8", solid: { bg: "var(--info)", fg: "#fff" } },
    warn:    { bg: "var(--warn-soft)", fg: "#7A4D0E", solid: { bg: "var(--warn)", fg: "#fff" } },
    violet:  { bg: "var(--violet-soft)", fg: "#3F2D80", solid: { bg: "var(--violet)", fg: "#fff" } },
  };
  const t = tones[tone] || tones.neutral;
  const s = solid ? t.solid : t;
  const pad = size === "sm" ? "1px 7px" : "3px 9px";
  const fs = size === "sm" ? 10.5 : 11.5;
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 4,
      padding: pad, fontSize: fs, fontWeight: 600, letterSpacing: ".01em",
      background: s.bg, color: s.fg, borderRadius: 999, lineHeight: 1.4, whiteSpace: "nowrap",
    }}>{children}</span>
  );
};

// === Button ================================================================
const Button = ({ children, variant = "ghost", size = "md", icon, iconRight, disabled, onClick, style = {}, type, title }) => {
  const sizes = {
    sm: { pad: "5px 10px", fs: 12, h: 26 },
    md: { pad: "7px 13px", fs: 13, h: 32 },
    lg: { pad: "10px 16px", fs: 14, h: 38 },
  };
  const sz = sizes[size];
  const variants = {
    primary: { bg: "var(--ink)", fg: "#fff", border: "1px solid var(--ink)", hover: { background: "#000" } },
    secondary: { bg: "var(--paper)", fg: "var(--ink)", border: "1px solid var(--line-2)", hover: { background: "var(--bg-deep)" } },
    ghost: { bg: "transparent", fg: "var(--ink-2)", border: "1px solid transparent", hover: { background: "var(--bg-deep)" } },
    danger: { bg: "var(--paper)", fg: "var(--up-ink)", border: "1px solid var(--up-soft)", hover: { background: "var(--up-soft)" } },
    accent: { bg: "var(--up)", fg: "#fff", border: "1px solid var(--up)", hover: { background: "#B82A21" } },
  };
  const v = variants[variant];
  const [hov, setHov] = React.useState(false);
  return (
    <button
      type={type || "button"} onClick={onClick} disabled={disabled} title={title}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        display: "inline-flex", alignItems: "center", gap: 6,
        padding: sz.pad, height: sz.h, fontSize: sz.fs, fontWeight: 500,
        background: v.bg, color: v.fg, border: v.border, borderRadius: 8,
        cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.5 : 1,
        transition: "background .15s, transform .05s",
        ...(hov && !disabled ? v.hover : {}),
        ...style,
      }}
    >
      {icon && <Icon name={icon} size={sz.fs + 2} />}
      {children}
      {iconRight && <Icon name={iconRight} size={sz.fs + 2} />}
    </button>
  );
};

// === Card ==================================================================
const Card = ({ children, style = {}, padding = 18, hover = false, onClick, title }) => {
  const [hov, setHov] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => hover && setHov(true)} onMouseLeave={() => hover && setHov(false)}
      title={title}
      style={{
        background: "var(--paper)", borderRadius: "var(--radius-lg)",
        border: "1px solid var(--line)",
        boxShadow: hov ? "var(--shadow-lg)" : "var(--shadow-sm)",
        padding, transition: "box-shadow .2s, transform .15s",
        cursor: onClick ? "pointer" : "default",
        transform: hov && hover ? "translateY(-2px)" : "none",
        ...style,
      }}>
      {children}
    </div>
  );
};

// === SectionHeader ==========================================================
const SectionHeader = ({ kicker, title, subtitle, right, level = 1 }) => (
  <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 14, gap: 16 }}>
    <div>
      {kicker && <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{kicker}</div>}
      <h2 className="serif-cn" style={{
        margin: kicker ? "4px 0 0" : 0,
        fontSize: level === 1 ? 28 : 20, fontWeight: 700, color: "var(--ink)",
        letterSpacing: ".02em",
      }}>{title}</h2>
      {subtitle && <div style={{ fontSize: 13, color: "var(--ink-3)", marginTop: 4 }}>{subtitle}</div>}
    </div>
    {right && <div>{right}</div>}
  </div>
);

// === Tabs ==================================================================
const Tabs = ({ tabs, value, onChange, variant = "underline" }) => {
  if (variant === "pill") {
    return (
      <div style={{ display: "inline-flex", padding: 3, background: "var(--bg-deep)", borderRadius: 8, gap: 2 }}>
        {tabs.map(t => {
          const active = t.id === value;
          return (
            <button key={t.id} onClick={() => onChange(t.id)} style={{
              padding: "5px 12px", fontSize: 12.5, fontWeight: 500,
              background: active ? "var(--paper)" : "transparent",
              color: active ? "var(--ink)" : "var(--ink-3)",
              border: "none", borderRadius: 6,
              boxShadow: active ? "var(--shadow-sm)" : "none",
              cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 5,
            }}>
              {t.icon && <Icon name={t.icon} size={13} />}
              {t.label}
              {t.count != null && <span style={{ fontSize: 11, color: "var(--ink-4)", fontWeight: 500 }}>{t.count}</span>}
            </button>
          );
        })}
      </div>
    );
  }
  return (
    <div style={{ display: "flex", gap: 18, borderBottom: "1px solid var(--line)" }}>
      {tabs.map(t => {
        const active = t.id === value;
        return (
          <button key={t.id} onClick={() => onChange(t.id)} style={{
            padding: "10px 0", fontSize: 13.5, fontWeight: 500,
            color: active ? "var(--ink)" : "var(--ink-3)",
            background: "transparent", border: "none",
            borderBottom: active ? "2px solid var(--ink)" : "2px solid transparent",
            marginBottom: -1, cursor: "pointer",
          }}>{t.label}{t.count != null && <span style={{ marginLeft: 6, fontSize: 11, color: "var(--ink-4)" }}>{t.count}</span>}</button>
        );
      })}
    </div>
  );
};

// === Field / Input =========================================================
const Input = ({ value, onChange, placeholder, prefix, suffix, type = "text", inputMode, style = {}, ...rest }) => {
  return (
    <div style={{
      display: "flex", alignItems: "center",
      background: "var(--paper)", border: "1px solid var(--line-2)",
      borderRadius: 8, padding: "0 10px", height: 34, gap: 6,
      ...style,
    }}>
      {prefix && <span style={{ color: "var(--ink-4)", fontSize: 12, display: "inline-flex", alignItems: "center", gap: 4 }}>{prefix}</span>}
      <input
        {...rest}
        type={type} inputMode={inputMode} value={value ?? ""} placeholder={placeholder}
        onChange={e => onChange?.(e.target.value)}
        style={{ flex: 1, border: "none", background: "transparent", height: "100%", fontSize: 13, color: "var(--ink)" }}
      />
      {suffix && <span style={{ color: "var(--ink-4)", fontSize: 12 }}>{suffix}</span>}
    </div>
  );
};

const Select = ({ value, onChange, options, style = {} }) => {
  return (
    <div style={{
      display: "inline-flex", alignItems: "center",
      background: "var(--paper)", border: "1px solid var(--line-2)",
      borderRadius: 8, height: 34, padding: "0 8px 0 12px", gap: 4, position: "relative",
      ...style,
    }}>
      <select value={value} onChange={e => onChange(e.target.value)} style={{
        appearance: "none", border: "none", background: "transparent", paddingRight: 18,
        fontSize: 13, color: "var(--ink)", height: "100%", cursor: "pointer",
      }}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      <Icon name="chevron-down" size={14} style={{ color: "var(--ink-4)", position: "absolute", right: 8, pointerEvents: "none" }}/>
    </div>
  );
};

// === Toggle ================================================================
const Toggle = ({ value, onChange, size = "md" }) => {
  const w = size === "sm" ? 28 : 34;
  const h = size === "sm" ? 16 : 20;
  const knob = h - 4;
  return (
    <button onClick={() => onChange(!value)} style={{
      width: w, height: h, padding: 0, borderRadius: h, border: "none",
      background: value ? "var(--ink)" : "var(--line-strong)",
      position: "relative", cursor: "pointer", transition: "background .15s",
    }}>
      <span style={{
        position: "absolute", top: 2, left: value ? w - knob - 2 : 2,
        width: knob, height: knob, borderRadius: "50%",
        background: "#fff", transition: "left .15s",
        boxShadow: "0 1px 3px rgba(0,0,0,.2)",
      }} />
    </button>
  );
};

// === Symbol chip ===========================================================
const SymbolChip = ({ sym, onClick, selected, showName = true, dense = false }) => {
  const hasPrice = sym.price != null && sym.prevClose != null && sym.prevClose !== 0;
  const ch = hasPrice ? ((sym.price - sym.prevClose) / sym.prevClose) * 100 : null;
  return (
    <button onClick={() => onClick?.(sym)} style={{
      display: "inline-flex", alignItems: "center", gap: 8,
      padding: dense ? "5px 9px" : "7px 11px",
      background: selected ? "var(--ink)" : "var(--paper)",
      color: selected ? "#fff" : "var(--ink)",
      border: "1px solid " + (selected ? "var(--ink)" : "var(--line-2)"),
      borderRadius: 8, cursor: "pointer", textAlign: "left",
      transition: "background .12s, border-color .12s",
    }}>
      <MarketDot market={sym.market} />
      <span className="mono" style={{ fontWeight: 600, fontSize: 12, letterSpacing: ".02em" }}>{sym.code}</span>
      {showName && <span style={{ fontSize: 11.5, color: selected ? "rgba(255,255,255,.7)" : "var(--ink-3)" }}>{sym.name}</span>}
      <span className="mono" style={{ fontSize: 11, color: ch != null ? (ch >= 0 ? "var(--up)" : "var(--down)") : "var(--ink-4)", fontWeight: 600, marginLeft: 2 }}>
        {ch != null ? fmtPct(ch, 2) : "—"}
      </span>
    </button>
  );
};

// === Sparkline ============================================================
const Sparkline = ({ data, width = 80, height = 24, color, fill = false }) => {
  if (!data || !data.length) return null;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const points = data.map((v, i) => [i * step, height - ((v - min) / range) * (height - 2) - 1]);
  const d = "M" + points.map(p => p.map(v => v.toFixed(1)).join(",")).join(" L ");
  const isUp = data[data.length - 1] >= data[0];
  const c = color || (isUp ? "var(--up)" : "var(--down)");
  const fillD = fill ? d + ` L ${width.toFixed(1)},${height} L 0,${height} Z` : null;
  return (
    <svg width={width} height={height} className="spark" style={{ display: "block" }}>
      {fill && <path d={fillD} fill={c} fillOpacity=".1" stroke="none"/>}
      <path d={d} stroke={c} />
    </svg>
  );
};

// === ChangeNum ============================================================
const ChangeNum = ({ value, format = "pct", dp = 2, size = "md" }) => {
  if (value == null || isNaN(value)) return <span className="mono" style={{ color: "var(--ink-4)" }}>—</span>;
  const isUp = value >= 0;
  const fs = { sm: 12, md: 13, lg: 16 }[size];
  const txt = format === "pct" ? fmtPct(value, dp) : fmtNum(value, dp);
  return (
    <span className="mono" style={{
      color: isUp ? "var(--up)" : "var(--down)", fontWeight: 600, fontSize: fs, fontVariantNumeric: "tabular-nums",
    }}>{txt}</span>
  );
};

// === Empty ================================================================
const Empty = ({ icon = "circle", title, hint }) => (
  <div style={{ padding: 32, textAlign: "center", color: "var(--ink-4)" }}>
    <Icon name={icon} size={28} style={{ color: "var(--ink-5)" }}/>
    <div style={{ fontSize: 14, fontWeight: 600, color: "var(--ink-2)", marginTop: 10 }}>{title}</div>
    {hint && <div style={{ fontSize: 12.5, marginTop: 4 }}>{hint}</div>}
  </div>
);

// === Modal ================================================================
const Modal = ({ open, onClose, children, width = 520, title }) => {
  if (!open) return null;
  const downOnBackdrop = React.useRef(false);
  return (
    <div
      onMouseDown={e => { downOnBackdrop.current = e.target === e.currentTarget; }}
      onMouseUp={e => { if (downOnBackdrop.current && e.target === e.currentTarget) onClose(); }}
      style={{
      position: "fixed", inset: 0, background: "rgba(20,22,27,.45)",
      display: "flex", alignItems: "center", justifyContent: "center", zIndex: 60,
      animation: "fadeIn .15s ease",
    }}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--paper)", borderRadius: 14, width, maxWidth: "94vw",
        maxHeight: "90vh", overflow: "hidden", boxShadow: "var(--shadow-lg)",
        display: "flex", flexDirection: "column",
      }}>
        {title && (
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div style={{ fontSize: 15, fontWeight: 600 }}>{title}</div>
            <button onClick={onClose} style={{ background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-3)" }}><Icon name="x" size={18} /></button>
          </div>
        )}
        <div className="scroll" style={{ overflowY: "auto", flex: 1 }}>{children}</div>
      </div>
    </div>
  );
};

Object.assign(window, {
  fmtNum, fmtMoney, fmtPct, toCNY,
  MarketDot, MarketLabel, Badge, Button, Card, SectionHeader, Tabs,
  Input, Select, Toggle, SymbolChip, Sparkline, ChangeNum, Empty, Modal,
});
