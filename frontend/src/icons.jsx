/* Inline SVG icons — minimal, monoline, 1.5 stroke. */

const Icon = ({ name, size = 16, className = "", style = {} }) => {
  const s = size;
  const stroke = "currentColor";
  const sw = 1.5;
  const common = { width: s, height: s, viewBox: "0 0 24 24", fill: "none", stroke, strokeWidth: sw, strokeLinecap: "round", strokeLinejoin: "round", className, style };
  switch (name) {
    case "dashboard": return (
      <svg {...common}><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg>);
    case "bell": return (
      <svg {...common}><path d="M6 8a6 6 0 1 1 12 0c0 4.5 1.5 6 1.5 6h-15s1.5-1.5 1.5-6Z"/><path d="M10.5 18a1.8 1.8 0 0 0 3 0"/></svg>);
    case "wallet": return (
      <svg {...common}><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18"/><circle cx="16.5" cy="14.5" r="1.2" fill="currentColor"/></svg>);
    case "book": return (
      <svg {...common}><path d="M5 4h11a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3Z"/><path d="M5 17a3 3 0 0 1 3-3h11"/></svg>);
    case "target": return (
      <svg {...common}><circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5" fill="currentColor"/></svg>);
    case "hourglass": return (
      <svg {...common}><path d="M6 3h12M6 21h12"/><path d="M7 3c0 5 5 5 5 9s-5 4-5 9"/><path d="M17 3c0 5-5 5-5 9s5 4 5 9"/></svg>);
    case "search": return (
      <svg {...common}><circle cx="11" cy="11" r="6.5"/><path d="m20 20-3.5-3.5"/></svg>);
    case "plus": return (
      <svg {...common}><path d="M12 5v14M5 12h14"/></svg>);
    case "check": return (
      <svg {...common}><path d="m5 12 5 5 9-11"/></svg>);
    case "x": return (
      <svg {...common}><path d="m6 6 12 12M18 6 6 18"/></svg>);
    case "trash": return (
      <svg {...common}><path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/><path d="M6 7v12a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V7"/><path d="M10 11v6M14 11v6"/></svg>);
    case "edit": return (
      <svg {...common}><path d="M4 20h4l11-11-4-4L4 16Z"/><path d="m13 6 4 4"/></svg>);
    case "play": return (
      <svg {...common}><path d="M7 5v14l12-7Z"/></svg>);
    case "pause": return (
      <svg {...common}><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>);
    case "arrow-up": return (
      <svg {...common}><path d="M12 19V5M5 12l7-7 7 7"/></svg>);
    case "arrow-down": return (
      <svg {...common}><path d="M12 5v14M5 12l7 7 7-7"/></svg>);
    case "arrow-right": return (
      <svg {...common}><path d="M5 12h14M13 5l7 7-7 7"/></svg>);
    case "arrow-left": return (
      <svg {...common}><path d="M19 12H5M11 5l-7 7 7 7"/></svg>);
    case "calendar": return (
      <svg {...common}><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/></svg>);
    case "clock": return (
      <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>);
    case "trend-up": return (
      <svg {...common}><path d="M3 17 9 11l4 4 8-8"/><path d="M14 4h7v7"/></svg>);
    case "trend-down": return (
      <svg {...common}><path d="M3 7 9 13l4-4 8 8"/><path d="M14 20h7v-7"/></svg>);
    case "settings": return (
      <svg {...common}><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.05a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.05a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z"/></svg>);
    case "mail": return (
      <svg {...common}><rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/></svg>);
    case "sun": return (
      <svg {...common}><circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4"/></svg>);
    case "moon": return (
      <svg {...common}><path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z"/></svg>);
    case "send": return (
      <svg {...common}><path d="M21 3 11 14"/><path d="M21 3 14.5 21l-3.5-7-7-3.5Z"/></svg>);
    case "import": return (
      <svg {...common}><path d="M12 3v12M7 10l5 5 5-5"/><path d="M5 21h14"/></svg>);
    case "filter": return (
      <svg {...common}><path d="M4 5h16l-6 8v6l-4-2v-4Z"/></svg>);
    case "globe": return (
      <svg {...common}><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/></svg>);
    case "menu": return (
      <svg {...common}><path d="M4 7h16M4 12h16M4 17h16"/></svg>);
    case "bolt": return (
      <svg {...common}><path d="M13 3 5 14h6l-1 7 8-11h-6Z"/></svg>);
    case "spark": return (
      <svg {...common}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8"/></svg>);
    case "chevron-right": return (
      <svg {...common}><path d="m9 6 6 6-6 6"/></svg>);
    case "chevron-down": return (
      <svg {...common}><path d="m6 9 6 6 6-6"/></svg>);
    case "circle": return (
      <svg {...common}><circle cx="12" cy="12" r="9"/></svg>);
    case "dot": return (
      <svg width={s} height={s} viewBox="0 0 24 24" className={className} style={style}><circle cx="12" cy="12" r="4" fill="currentColor"/></svg>);
    case "logo": return (
      <svg width={s} height={s} viewBox="0 0 24 24" fill="none" className={className} style={style}>
        <rect x="2" y="2" width="20" height="20" rx="5" fill="#14161B"/>
        <path d="M7 17V8h7M7 12h5" stroke="#F6F2EB" strokeWidth="2" strokeLinecap="round"/>
        <circle cx="17" cy="16" r="2" fill="#D9352B"/>
      </svg>);
    default: return null;
  }
};

window.Icon = Icon;
