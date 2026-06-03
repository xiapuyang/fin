/* Main app — sidebar nav + module router */

const NAV = [
  { id: "dashboard", icon: "dashboard", tag: null },
  { id: "alerts",    icon: "bell",      tag: "01" },
  { id: "holdings",  icon: "wallet",    tag: "02" },
  { id: "ledger",    icon: "book",      tag: "03" },
  { id: "balance",   icon: "target",    tag: "04" },
  { id: "fire",      icon: "spark",     tag: "05" },
];

const useLang = () => {
  const [ready, setReady] = React.useState(I18N.isReady());
  React.useEffect(() => { I18N.onReady(() => setReady(true)); }, []);
  return ready;
};

const AppInner = () => {
  const [route, setRoute] = React.useState("dashboard");
  const [alertsCategory, setAlertsCategory] = React.useState(null);
  const [alerts, setAlerts] = React.useState([]);
  const [history, setHistory] = React.useState([]);
  const [fxRates, setFxRates] = React.useState({ USD: 7.24, HKD: 0.93, CNY: 1, CAD: 5.3 });
  const [currency, setCurrency] = React.useState("CNY");
  const [settings, setSettings] = React.useState({ timezone: "", display_name: "" });
  const [enabledMarkets, setEnabledMarkets] = React.useState(["us"]);
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
      if (Array.isArray(s.enabled_markets) && s.enabled_markets.length > 0) setEnabledMarkets(s.enabled_markets);
      // Only adopt backend language when user has no explicit localStorage preference
      if (s.language && s.language !== I18N.getLang() && !localStorage.getItem("fin_lang")) I18N.setLang(s.language);
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
        <TopBar route={route} fxRates={fxRates} currency={currency} market={market} enabledMarkets={enabledMarkets} displayName={settings.display_name || ""} onCurrencyChange={c => {
          setCurrency(c);
          fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ currency: c }) }).catch(() => {});
        }} onOpenSettings={() => setShowSettings(true)} onTogglePrivacy={next => {
          setPrivacyMasked(next);
          fetch("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ privacy_mask: next }) }).catch(() => {});
        }}/>
        <div data-screen-label={route}>
          {Page}
        </div>
      </main>
      {showSettings && (
        <AppSettingsModal
          settings={{ ...settings, enabled_markets: enabledMarkets }}
          onClose={() => setShowSettings(false)}
          onSaved={s => { setSettings(prev => ({ ...prev, ...s })); if (Array.isArray(s.enabled_markets)) setEnabledMarkets(s.enabled_markets); }}
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
            <span style={{ flex: 1 }}>{I18N.t(`nav.${n.id}`)}</span>
            {n.tag && <span className="mono" style={{ fontSize: 9.5, color: active ? "rgba(255,255,255,.5)" : "var(--ink-5)", letterSpacing: ".05em" }}>{n.tag}</span>}
          </button>
        );
      })}
    </nav>
  </aside>
);

// Market key (lowercase) → { currency, fxKey } mapping
const MARKET_META = {
  us: { currency: "USD", fxKey: "USD" },
  hk: { currency: "HKD", fxKey: "HKD" },
  cn: { currency: "CNY", fxKey: null },
  ca: { currency: "CAD", fxKey: "CAD" },
};

const TopBar = ({ route, fxRates = {}, currency = "CNY", market = {}, enabledMarkets = ["us"], displayName = "", onCurrencyChange, onOpenSettings, onTogglePrivacy }) => {
  const cur = NAV.find(n => n.id === route);
  const masked = usePrivacyMasked();

  // Filter market dots to only enabled markets
  const visibleMarket = Object.fromEntries(
    Object.entries(market).filter(([k]) => enabledMarkets.includes(k.toLowerCase()))
  );

  // Build FX string from enabled markets that have a fxKey
  const fxParts = enabledMarkets
    .filter(m => MARKET_META[m]?.fxKey)
    .map(m => { const key = MARKET_META[m].fxKey; return `${key} ¥${(fxRates[key] ?? 0).toFixed(2)}`; });

  // Currency buttons: CNY always + currencies for enabled non-CN markets
  const visibleCurrencies = ["CNY", ...enabledMarkets
    .filter(m => m !== "cn" && MARKET_META[m])
    .map(m => MARKET_META[m].currency)
  ];
  return (
    <div style={{
      height: 52, padding: "0 32px", display: "flex", alignItems: "center", justifyContent: "space-between",
      borderBottom: "1px solid var(--line)", background: "rgba(255,255,255,0.6)", backdropFilter: "blur(8px)",
      position: "sticky", top: 0, zIndex: 30,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 12, color: "var(--ink-3)" }}>
        <span>fin</span><Icon name="chevron-right" size={12}/><span style={{ color: "var(--ink)", fontWeight: 500 }}>{I18N.t(`nav.${route}`)}</span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {/* Market status dots — filtered to enabled markets */}
        {Object.keys(visibleMarket).length > 0 && (
          <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
            {Object.entries(visibleMarket).map(([k, v]) => (
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
        {fxParts.length > 0 && <><span style={{ width: 1, height: 16, background: "var(--line-2)" }}/><span className="mono" style={{ fontSize: 11, color: "var(--ink-4)" }}>{fxParts.join(" · ")}</span></>}
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <div style={{ display: "flex", gap: 2 }}>
          {visibleCurrencies.map(c => (
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
        <select
          value={I18N.getLang()}
          onChange={e => I18N.setLang(e.target.value)}
          style={{
            fontSize: 11, fontWeight: 700, color: "var(--ink)",
            background: "var(--paper-2)", border: "1.5px solid var(--line)",
            borderRadius: 6, padding: "3px 8px", cursor: "pointer",
            outline: "none", letterSpacing: ".02em",
          }}
        >
          <option value="en">English</option>
          <option value="zh">中文</option>
        </select>
        <span style={{ width: 1, height: 16, background: "var(--line-2)" }}/>
        <Button
          variant={masked ? "secondary" : "ghost"}
          size="sm"
          icon={masked ? "eye-off" : "eye"}
          onClick={() => onTogglePrivacy(!masked)}
          title={masked ? I18N.t("app.privacy.show") : I18N.t("app.privacy.hide")}
        />
        <Button variant="ghost" size="sm" icon="settings" onClick={onOpenSettings}/>
        {(() => {
          const ch = displayName ? displayName.trim()[0] : "?";
          const isCJK = ch.codePointAt(0) >= 0x4E00;
          return <div style={{ width: 28, height: 28, borderRadius: 14, background: "linear-gradient(135deg, #14161B, #5C6270)", color: "#fff", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: isCJK ? 13 : 11, fontWeight: 600 }}>{isCJK ? ch : ch.toUpperCase()}</div>;
        })()}
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
  { value: "Asia/Shanghai",      get label() { return I18N.t("app.tz.Asia/Shanghai"); } },
  { value: "Asia/Hong_Kong",     get label() { return I18N.t("app.tz.Asia/Hong_Kong"); } },
  { value: "Asia/Tokyo",         get label() { return I18N.t("app.tz.Asia/Tokyo"); } },
];

const AppSettingsModal = ({ settings, onClose, onSaved }) => {
  const [displayName, setDisplayName] = React.useState(settings.display_name || "");
  const [tz, setTz]              = React.useState(settings.timezone   || Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
  const [birthDate, setBirthDate] = React.useState(settings.birth_date || "");
  const [notifyEmail, setNotifyEmail] = React.useState(settings.notify_email || "");
  const [notifyEnabled, setNotifyEnabled] = React.useState(settings.notify_enabled !== false);
  const [enabledMarkets, setEnabledMarkets] = React.useState(settings.enabled_markets || ["us"]);
  const [saving, setSaving]       = React.useState(false);
  const [emailError, setEmailError] = React.useState("");
  const [apiKeyInput, setApiKeyInput] = React.useState("");
  const [apiKeySet, setApiKeySet]     = React.useState(false);
  const [apiKeyHint, setApiKeyHint]   = React.useState("");
  const [apiInbox, setApiInbox]       = React.useState("");
  const [origApiInbox, setOrigApiInbox] = React.useState("");
  const [apiKeySaved, setApiKeySaved] = React.useState(false);
  const [showKey, setShowKey]         = React.useState(false);

  React.useEffect(() => {
    fetch("/api/settings/credentials")
      .then(r => r.ok ? r.json() : null)
      .then(d => {
        if (d) {
          setApiKeySet(!!d.agentmail_api_key_set);
          setApiKeyHint(d.agentmail_api_key_hint || "");
          setApiInbox(d.agentmail_inbox || "");
          setOrigApiInbox(d.agentmail_inbox || "");
        }
      })
      .catch(() => {});
  }, []);

  const save = async () => {
    const trimmed = notifyEmail.trim();
    if (trimmed && !/.+@.+\..+/.test(trimmed)) {
      setEmailError(I18N.t("app.settings.emailError"));
      return;
    }
    setEmailError("");
    setSaving(true);
    try {
      const credPayload = {};
      const newKey = apiKeyInput.trim();
      if (newKey) credPayload.agentmail_api_key = newKey;
      if (apiInbox !== origApiInbox) credPayload.agentmail_inbox = apiInbox;
      if (Object.keys(credPayload).length > 0) {
        const kr = await fetch("/api/settings/credentials", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(credPayload),
        });
        if (kr.ok) {
          if (newKey) {
            setApiKeySet(true);
            setApiKeyHint(newKey.length >= 8 ? newKey.slice(-4) : "");
            setApiKeyInput("");
          }
          setOrigApiInbox(apiInbox);
          setApiKeySaved(true);
        }
      }
      const payload = { display_name: displayName.trim(), timezone: tz, birth_date: birthDate, notify_email: trimmed, notify_enabled: notifyEnabled, enabled_markets: enabledMarkets };
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (res.ok) { onSaved(payload); if (!apiKeySaved) onClose(); else onClose(); }
    } finally { setSaving(false); }
  };

  return (
    <Modal open={true} onClose={onClose} title={I18N.t("app.settings.title")} width={420}>
      <div style={{ padding: "18px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>{I18N.t("app.settings.markets")}</div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {Object.entries(MARKET_META).map(([key, meta]) => {
              const checked = enabledMarkets.includes(key);
              return (
                <label key={key} style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 13, cursor: "pointer", padding: "5px 10px", borderRadius: 6, border: `1px solid ${checked ? "var(--ink-3)" : "var(--line)"}`, background: checked ? "var(--bg-deep)" : "transparent", userSelect: "none" }}>
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={e => setEnabledMarkets(prev => e.target.checked ? [...prev, key] : prev.filter(x => x !== key))}
                    style={{ accentColor: "var(--ink)", cursor: "pointer" }}
                  />
                  <span style={{ fontWeight: 600 }}>{key.toUpperCase()}</span>
                  <span style={{ color: "var(--ink-4)", fontSize: 11 }}>{meta.currency}</span>
                </label>
              );
            })}
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.markets.hint")}</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>{I18N.t("app.settings.timezone")}</div>
          <Select value={tz} onChange={setTz} options={TIMEZONE_OPTIONS} style={{ width: "100%" }}/>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.timezone.hint")}</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>{I18N.t("app.settings.displayName")}</div>
          <Input
            value={displayName}
            onChange={setDisplayName}
            placeholder={I18N.t("app.settings.displayName.ph")}
            autoComplete="off"
          />
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.displayName.hint")}</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>{I18N.t("app.settings.birthDate")}</div>
          <DateInput value={birthDate} onChange={v => setBirthDate(v)} style={{ width: "100%" }}/>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.birthDate.hint")}</div>
        </div>
        <div>
          <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 6 }}>{I18N.t("app.settings.email")}</div>
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
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>{I18N.t("app.settings.notify")}</div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>{I18N.t("app.settings.notify.hint")}</div>
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
                  value={apiKeyInput}
                  onChange={e => setApiKeyInput(e.target.value)}
                  placeholder={apiKeySet
                    ? (apiKeyHint
                        ? I18N.tf("app.settings.apiKey.savedHint", { hint: apiKeyHint })
                        : I18N.t("app.settings.apiKey.saved"))
                    : I18N.t("app.settings.apiKey.placeholder")}
                  autoComplete="new-password"
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
                autoComplete="off"
                style={{
                  width: "100%", padding: "6px 10px", fontSize: 13, borderRadius: 7,
                  border: "1px solid var(--line-2)", background: "var(--paper)", color: "var(--ink)",
                  boxSizing: "border-box",
                }}
              />
            </div>
          </div>
          <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.email.hint")}</div>
          {apiKeySaved && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 4 }}>{I18N.t("app.settings.saved")}</div>}
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={save} disabled={saving}>{saving ? I18N.t("base.btn.saving") : I18N.t("base.btn.save")}</Button>
        </div>
      </div>
    </Modal>
  );
};

const App = () => {
  const i18nReady = useLang();
  if (!i18nReady) return null;
  return <AppInner />;
};

ReactDOM.createRoot(document.getElementById("root")).render(<App/>);
