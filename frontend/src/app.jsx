/* Main app — sidebar nav + module router */

const NAV = [
  { id: "dashboard", icon: "dashboard", label: "Dashboard",  cn: "总览"    },
  { id: "alerts",    icon: "bell",      label: "Alerts",     cn: "提醒",       tag: "01" },
  { id: "holdings",  icon: "wallet",    label: "Portfolio",  cn: "投资组合",    tag: "02" },
  { id: "ledger",    icon: "book",      label: "Ledger",     cn: "收入支出",    tag: "03" },
  { id: "balance",   icon: "target",    label: "Balance",    cn: "资产负债",    tag: "04" },
  { id: "fire",      icon: "spark",     label: "FIRE",       cn: "退休计划",    tag: "05" },
];

const App = () => {
  const [route, setRoute] = React.useState("dashboard");
  const [alertsCategory, setAlertsCategory] = React.useState(null);
  const [alerts, setAlerts] = React.useState([]);
  const [history, setHistory] = React.useState([]);
  const [fxRates, setFxRates] = React.useState({ USD: 7.24, HKD: 0.93, CNY: 1, CAD: 5.3 });
  const [currency, setCurrency] = React.useState("CNY");
  const [settings, setSettings] = React.useState({ timezone: "", display_name: "" });
  const [showSettings, setShowSettings] = React.useState(false);
  const [marketNow, setMarketNow] = React.useState(new Date());
  const [serverMarket, setServerMarket] = React.useState({});

  React.useEffect(() => {
    fetch("/api/alerts").then(r => r.json()).then(setAlerts).catch(() => {});
    fetch("/api/history").then(r => r.json()).then(setHistory).catch(() => {});
    fetch("/api/settings").then(r => r.json()).then(s => {
      setSettings(prev => ({ ...prev, ...s }));
      if (s.currency && CURRENCIES.includes(s.currency)) setCurrency(s.currency);
      if (typeof s.privacy_mask === "boolean") setPrivacyMasked(s.privacy_mask);
    }).catch(() => {});
    fetch("/api/symbols").then(r => r.json()).then(data => {
      Object.assign(SYMBOLS, data);
      _rebuildSymbolIndex();
    }).catch(() => {});
  }, []);

  // Fetch FX rates on load and every 5 minutes; also update global FX object
  React.useEffect(() => {
    const refresh = () =>
      fetch("/api/fx").then(r => r.json()).then(rates => {
        setFxRates(rates);
        Object.assign(FX, rates);
      }).catch(() => {});
    refresh();
    const t = setInterval(refresh, 5 * 60 * 1000);
    return () => clearInterval(t);
  }, []);

  // Market state — drives TopBar indicator dots, refreshed every minute
  React.useEffect(() => {
    const t = setInterval(() => setMarketNow(new Date()), 60 * 1000);
    return () => clearInterval(t);
  }, []);
  React.useEffect(() => {
    const ctrl = new AbortController();
    const poll = () => fetch("/api/market-states", { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : null).then(d => d && setServerMarket(d)).catch(() => {});
    poll();
    const t = setInterval(poll, 60 * 1000);
    return () => { clearInterval(t); ctrl.abort(); };
  }, []);
  const _timeBased = MARKET_HOURS(marketNow);
  const _serverFresh = serverMarket.updated_at &&
    (Date.now() - new Date(serverMarket.updated_at).getTime()) < 5 * 60 * 1000;
  const market = Object.fromEntries(
    Object.entries(_timeBased).map(([k, v]) => {
      const state = _serverFresh ? (serverMarket[k] || v.state) : v.state;
      return [k, { state, label: STATE_LABEL[state] || v.label }];
    })
  );

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
    dashboard: <Dashboard onNavigate={navigate} alerts={alerts} history={history} timezone={settings.timezone} currency={currency} displayName={settings.display_name || ""}/>,
    alerts:    <Alerts alerts={alerts} setAlerts={setAlerts} history={history} setHistory={setHistory} initialCategory={alertsCategory}/>,
    holdings:  <Holdings currency={currency} birthDate={settings.birth_date || ""}/>,
    ledger:    <Ledger fxRates={fxRates} currency={currency}/>,
    balance:   <BalanceSheet currency={currency}/>,
    fire:      <Fire currency={currency} birthDate={settings.birth_date || ""}/>,
  }[route];

  return (
    <div style={{ display: "flex", minHeight: "100vh" }}>
      <Sidebar route={route} setRoute={navigate}/>
      <main style={{ flex: 1, minWidth: 0, background: "var(--bg)" }} className="scroll">
        <TopBar route={route} fxRates={fxRates} currency={currency} market={market} onCurrencyChange={c => {
          setCurrency(c);
          fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ currency: c }) }).catch(() => {});
        }} onOpenSettings={() => setShowSettings(true)} onTogglePrivacy={next => {
          setPrivacyMasked(next);
          fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ privacy_mask: next }) }).catch(() => {});
        }}/>
        <div data-screen-label={`${NAV.find(n=>n.id===route)?.cn||""} ${route}`}>
          {Page}
        </div>
      </main>
      {showSettings && (
        <AppSettingsModal
          settings={settings}
          onClose={() => setShowSettings(false)}
          onSaved={s => setSettings(prev => ({ ...prev, ...s }))}
        />
      )}
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
  </aside>
);

const TopBar = ({ route, fxRates = {}, currency = "CNY", market = {}, onCurrencyChange, onOpenSettings, onTogglePrivacy }) => {
  const cur = NAV.find(n => n.id === route);
  const usd = fxRates.USD ?? 7.24;
  const hkd = fxRates.HKD ?? 0.93;
  const cad = fxRates.CAD ?? 5.3;
  const masked = usePrivacyMasked();
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
        {/* Market status dots */}
        {Object.keys(market).length > 0 && (
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            {Object.entries(market).map(([k, v]) => (
              <div key={k} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 3 }}>
                  <span style={{
                    width: 6, height: 6, borderRadius: "50%", flexShrink: 0,
                    background: v.state === "REGULAR" ? "var(--up)"
                      : (v.state === "PRE" || v.state === "POST") ? "var(--warn)"
                      : "var(--ink-5)",
                  }}/>
                  <span style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-3)", letterSpacing: ".03em" }}>{k}</span>
                </div>
                <span style={{ fontSize: 9, color: "var(--ink-4)", letterSpacing: ".02em" }}>{v.label.split(" ")[0]}</span>
              </div>
            ))}
          </div>
        )}
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>USD ¥{usd.toFixed(2)} · HKD ¥{hkd.toFixed(2)} · CAD ¥{cad.toFixed(2)}</span>
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <div style={{ display: "flex", gap: 2 }}>
          {CURRENCIES.map(c => (
            <button key={c} onClick={() => onCurrencyChange(c)} style={{
              fontSize: 10, fontWeight: 600, padding: "2px 7px", borderRadius: 4, lineHeight: 1.6,
              border: `1px solid ${currency === c ? "var(--ink)" : "var(--line)"}`,
              background: currency === c ? "var(--ink)" : "transparent",
              color: currency === c ? "var(--paper)" : "var(--ink-4)",
              cursor: "pointer",
            }}>{c}</button>
          ))}
        </div>
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <Button
          variant={masked ? "secondary" : "ghost"}
          size="sm"
          icon={masked ? "eye-off" : "eye"}
          onClick={() => onTogglePrivacy(!masked)}
          title={masked ? "显示金额 Show amounts" : "隐藏金额 Hide amounts (demo mode)"}
        />
        <Button variant="ghost" size="sm" icon="settings" onClick={onOpenSettings}/>
        <div style={{ width: 28, height: 28, borderRadius: 14, background: "linear-gradient(135deg, #14161B, #5C6270)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: 600 }}>S</div>
      </div>
    </div>
  );
};

const TIMEZONE_OPTIONS = [
  { value: "UTC",                label: "UTC" },
  { value: "America/New_York",   label: "New York (ET)" },
  { value: "America/Toronto",    label: "Toronto (ET)" },
  { value: "America/Vancouver",  label: "Vancouver (PT)" },
  { value: "America/Los_Angeles",label: "Los Angeles (PT)" },
  { value: "Europe/London",      label: "London (GMT/BST)" },
  { value: "Asia/Shanghai",      label: "上海 / 北京 (CST)" },
  { value: "Asia/Hong_Kong",     label: "香港 (HKT)" },
  { value: "Asia/Tokyo",         label: "東京 (JST)" },
];

const AppSettingsModal = ({ settings, onClose, onSaved }) => {
  const [displayName, setDisplayName] = React.useState(settings.display_name || "");
  const [tz, setTz]              = React.useState(settings.timezone   || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [birthDate, setBirthDate] = React.useState(settings.birth_date || "");
  const [notifyEmail, setNotifyEmail] = React.useState(settings.notify_email || "");
  const [notifyEnabled, setNotifyEnabled] = React.useState(settings.notify_enabled !== false);
  const [saving, setSaving]       = React.useState(false);
  const [emailError, setEmailError] = React.useState("");
  const [apiKey, setApiKey]         = React.useState("");
  const [apiInbox, setApiInbox]     = React.useState("");
  const [origApiKey, setOrigApiKey] = React.useState("");
  const [origApiInbox, setOrigApiInbox] = React.useState("");
  const [apiKeySaved, setApiKeySaved] = React.useState(false);
  const [showKey, setShowKey]       = React.useState(false);

  React.useEffect(() => {
    fetch("/api/settings/credentials")
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setApiKey(d.agentmail_api_key || "");
          setApiInbox(d.agentmail_inbox || "");
          setOrigApiKey(d.agentmail_api_key || "");
          setOrigApiInbox(d.agentmail_inbox || "");
        }
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    const trimmed = notifyEmail.trim();
    if (trimmed && !/.+@.+\..+/.test(trimmed)) {
      setEmailError("请输入有效邮箱");
      return;
    }
    setEmailError("");
    setSaving(true);
    try {
      const credPayload = {};
      if (apiKey !== origApiKey) credPayload.agentmail_api_key = apiKey;
      if (apiInbox !== origApiInbox) credPayload.agentmail_inbox = apiInbox;
      if (Object.keys(credPayload).length > 0) {
        const kr = await fetch("/api/settings/credentials", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(credPayload),
        });
        if (kr.ok) { setOrigApiKey(apiKey); setOrigApiInbox(apiInbox); setApiKeySaved(true); }
      }
      const payload = { display_name: displayName.trim(), timezone: tz, birth_date: birthDate, notify_email: trimmed, notify_enabled: notifyEnabled };
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) { onSaved(payload); if (!apiKeySaved) onClose(); else onClose(); }
    } finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title="应用设置 App Settings" width={420}>
      <div style={{ padding: "18px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>时区 Timezone</div>
          <Select value={tz} onChange={setTz} options={TIMEZONE_OPTIONS} style={{ width: "100%" }}/>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>影响日期显示和时间相关计算</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>显示名 Display Name</div>
          <Input
            value={displayName}
            onChange={setDisplayName}
            placeholder="例如 Alice — 留空显示通用问候语"
          />
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>用于首页问候语「下午好，xxx」</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>出生日期 Birth Date</div>
          <input
            type="date"
            value={birthDate}
            onChange={e => setBirthDate(e.target.value)}
            style={{
              width: "100%", padding: "6px 10px", fontSize: 13, borderRadius: 7,
              border: "1px solid var(--line-2)", background: "var(--paper)", color: "var(--ink)",
              boxSizing: "border-box",
            }}
          />
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>用于 FIRE 退休计划自动计算当前年龄</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>通知邮箱 Notification Email</div>
          <Input
            value={notifyEmail}
            onChange={v => { setNotifyEmail(v); if (emailError) setEmailError(""); }}
            prefix={<Icon name="mail" size={13}/>}
            placeholder="your@email.com"
          />
          {emailError && <div style={{ fontSize: 11, color: "var(--down-ink)", marginTop: 4 }}>{emailError}</div>}
          <div style={{
            display: "flex", justifyContent: "space-between", alignItems: "center",
            marginTop: 10, padding: "10px 12px", background: "var(--bg-deep)", borderRadius: 8,
            border: "1px solid var(--line)",
          }}>
            <div>
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>触发提醒通知</div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>提醒触发时发送邮件</div>
            </div>
            <Toggle value={notifyEnabled} onChange={() => setNotifyEnabled(!notifyEnabled)} />
          </div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>AgentMail</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 3 }}>API Key</div>
              <div style={{ position: "relative" }}>
                <input
                  type={showKey ? "text" : "password"}
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  style={{
                    width: "100%", padding: "6px 34px 6px 10px", fontSize: 13, borderRadius: 7,
                    border: "1px solid var(--line-2)", background: "var(--paper)", color: "var(--ink)",
                    boxSizing: "border-box",
                  }}
                />
                <button
                  type="button"
                  onClick={() => setShowKey(v => !v)}
                  style={{
                    position: "absolute", right: 8, top: "50%", transform: "translateY(-50%)",
                    background: "none", border: "none", cursor: "pointer", padding: 2,
                    color: "var(--ink-4)", display: "flex", alignItems: "center",
                  }}
                >
                  <Icon name={showKey ? "eye-off" : "eye"} size={14}/>
                </button>
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginBottom: 3 }}>Inbox ID</div>
              <input
                type="text"
                value={apiInbox}
                onChange={e => setApiInbox(e.target.value)}
                style={{
                  width: "100%", padding: "6px 10px", fontSize: 13, borderRadius: 7,
                  border: "1px solid var(--line-2)", background: "var(--paper)", color: "var(--ink)",
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>用于价格提醒邮件通知。两项均需设置，留空保持不变。</div>
          {apiKeySaved && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>已保存，重启生效 · Restart required</div>}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={save} disabled={saving}>{saving ? "保存中…" : "保存"}</Button>
        </div>
      </div>
    </Modal>
  );
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
