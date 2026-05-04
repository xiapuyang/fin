/* Main app — sidebar nav + module router */

const NAV = [
  { id: "dashboard", icon: "dashboard", label: "Dashboard",  cn: "总览"    },
  { id: "alerts",    icon: "bell",      label: "Alerts",     cn: "提醒",       tag: "01" },
  { id: "holdings",  icon: "wallet",    label: "Portfolio",  cn: "投资组合",    tag: "02" },
  { id: "ledger",    icon: "book",      label: "Ledger",     cn: "记账",       tag: "03" },
  { id: "balance",   icon: "target",    label: "Balance",    cn: "资产负债",    tag: "04" },
  { id: "fire",      icon: "spark",     label: "FIRE",       cn: "退休计划",    tag: "05" },
];

const App = () => {
  const [route, setRoute] = React.useState("dashboard");
  const [alertsCategory, setAlertsCategory] = React.useState(null);
  const [alerts, setAlerts] = React.useState([]);
  const [history, setHistory] = React.useState([]);

  const navigate = (target) => {
    if (typeof target === "object") {
      setRoute(target.route);
      setAlertsCategory(target.category || null);
    } else {
      setRoute(target);
      setAlertsCategory(null);
    }
  };

  const Page = {
    dashboard: <Dashboard onNavigate={navigate} alerts={alerts} history={history}/>,
    alerts:    <Alerts alerts={alerts} setAlerts={setAlerts} history={history} setHistory={setHistory} initialCategory={alertsCategory}/>,
    holdings:  <Holdings/>,
    ledger:    <Ledger/>,
    balance:   <BalanceSheet/>,
    fire:      <Fire/>,
  }[route];

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar route={route} setRoute={navigate}/>
      <main style={{ flex: 1, minWidth: 0, background: "var(--bg)" }} className="scroll">
        <TopBar route={route}/>
        <div data-screen-label={`${NAV.find(n=>n.id===route)?.cn||""} ${route}`}>
          {Page}
        </div>
      </main>
    </div>
  );
};

const Sidebar = ({ route, setRoute }) => (
  <aside style={{
    width: 220, flexShrink: 0, background: "var(--paper-2)",
    borderRight: "1px solid var(--line)", padding: "20px 14px",
    display: "flex", flexDirection: "column", position: "sticky", top: 0, height: "100vh",
  }}>
    <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "0 6px 18px" }}>
      <Icon name="logo" size={28}/>
      <div>
        <div className="serif-cn" style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}>fin</div>
        <div style={{ fontSize: 10, color: "var(--ink-4)", letterSpacing: ".1em", marginTop: 2 }}>FINANCIAL INTELLIGENCE</div>
      </div>
    </div>

    <div style={{ fontSize: 10, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".15em", padding: "8px 8px 6px" }}>NAVIGATION</div>
    <nav style={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {NAV.map(n => {
        const active = n.id === route;
        return (
          <button key={n.id} onClick={() => setRoute(n.id)} style={{
            display: "flex", alignItems: "center", gap: 10,
            padding: "8px 10px", border: "none", borderRadius: 7,
            background: active ? "var(--ink)" : "transparent",
            color: active ? "#fff" : "var(--ink-2)",
            fontSize: 13, fontWeight: 500, cursor: "pointer", textAlign: "left",
            transition: "background .12s",
          }}
          onMouseEnter={e => !active && (e.currentTarget.style.background = "var(--bg-deep)")}
          onMouseLeave={e => !active && (e.currentTarget.style.background = "transparent")}
          >
            <Icon name={n.icon} size={16}/>
            <span style={{ flex: 1 }}>{n.cn} <span style={{ fontSize: 11, color: active ? "rgba(255,255,255,.55)" : "var(--ink-4)", fontWeight: 400 }}>{n.label}</span></span>
            {n.tag && <span className="mono" style={{ fontSize: 9.5, color: active ? "rgba(255,255,255,.5)" : "var(--ink-5)", letterSpacing: ".05em" }}>{n.tag}</span>}
          </button>
        );
      })}
    </nav>

    <div style={{ marginTop: "auto", borderTop: "1px dashed var(--line)", paddingTop: 14 }}>
      <div style={{ background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 10, padding: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 6 }}>
          <Icon name="clock" size={12} style={{ color: "var(--ink-3)" }}/>
          <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-3)", letterSpacing: ".1em" }}>CRON STATUS</span>
        </div>
        <div style={{ fontSize: 11, color: "var(--ink-3)", marginBottom: 4 }}>US <span className="mono">*/20 9-16 * * 1-5</span></div>
        <div style={{ fontSize: 11, color: "var(--ink-3)" }}>Asia <span className="mono">*/20 21-23 * * 0-4</span></div>
        <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 8, fontSize: 10.5, color: "var(--down)" }}>
          <span className="pulse-dot" style={{ width: 6, height: 6, borderRadius: 3, background: "var(--up)" }}/>
          <span>Next run in 18m</span>
        </div>
      </div>
      <div style={{ fontSize: 10, color: "var(--ink-4)", marginTop: 12, padding: "0 4px", lineHeight: 1.5 }}>
        ~/.openclaw/cron/fin/<br/>
        local-first · zero cloud
      </div>
    </div>
  </aside>
);

const TopBar = ({ route }) => {
  const cur = NAV.find(n => n.id === route);
  return (
    <div style={{
      height: 52, padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between",
      borderBottom: "1px solid var(--line)", background: "rgba(255,255,255,0.6)", backdropFilter: "blur(8px)",
      position: "sticky", top: 0, zIndex: 30,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--ink-3)" }}>
        <span>fin</span><Icon name="chevron-right" size={12}/><span style={{ color: "var(--ink)", fontWeight: 500 }}>{cur?.cn} {cur?.label}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>USD ¥7.24 · HKD ¥0.93</span>
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <Button variant="ghost" size="sm" icon="search">Search…</Button>
        <Button variant="ghost" size="sm" icon="settings"/>
        <div style={{ width: 28, height: 28, borderRadius: 14, background: "linear-gradient(135deg, #14161B, #5C6270)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600 }}>S</div>
      </div>
    </div>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
