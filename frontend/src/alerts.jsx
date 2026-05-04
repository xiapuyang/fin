/* Module 1 — Stock Alerts (full implementation) */

const COND_OPTIONS = [
  { value: "price_gte",  label: "价格高于 Price ≥",  symbol: "≥",  isPrice: true,  isUp: true  },
  { value: "price_lte",  label: "价格低于 Price ≤",  symbol: "≤",  isPrice: true,  isUp: false },
  { value: "change_gte", label: "涨幅超 Change ≥",   symbol: "Δ≥", isPrice: false, isUp: true  },
  { value: "change_lte", label: "跌幅超 Change ≤",   symbol: "Δ≤", isPrice: false, isUp: false },
];

const condMeta = (c) => COND_OPTIONS.find(o => o.value === c) || COND_OPTIONS[0];

const Alerts = ({ alerts, setAlerts, history, setHistory }) => {
  const [tab, setTab] = React.useState("active");
  const [category, setCategory] = React.useState(Object.keys(SYMBOLS)[0]);
  const [search, setSearch] = React.useState("");
  const [showImport, setShowImport] = React.useState(false);
  const [showEmail, setShowEmail] = React.useState(false);
  const [notifyEmail, setNotifyEmail] = React.useState("");
  const [notifyEnabled, setNotifyEnabled] = React.useState(true);

  const [liveQuotes, setLiveQuotes] = React.useState({});

  // Load alerts, history, and settings from API on mount
  React.useEffect(() => {
    fetch("/api/alerts").then(r => r.json()).then(setAlerts).catch(console.error);
    fetch("/api/history").then(r => r.json()).then(setHistory).catch(console.error);
    fetch("/api/settings").then(r => r.json()).then(s => {
      if (s.notify_email) setNotifyEmail(s.notify_email);
      setNotifyEnabled(s.notify_enabled);
    }).catch(console.error);
  }, []);

  // Fetch live quotes whenever the alert symbol set changes
  React.useEffect(() => {
    const symbols = [...new Set(alerts.map(a => a.code))];
    symbols.forEach(code => {
      fetch(`/api/quote/${code}`)
        .then(r => r.ok ? r.json() : null)
        .then(q => q && setLiveQuotes(prev => ({ ...prev, [code]: q })))
        .catch(() => {});
    });
  }, [alerts.map(a => a.code).join(",")]);

  // Form state
  const [form, setForm] = React.useState({ code: "NVDA", cond: "price_gte", threshold: "", name: "" });
  const [liveQuote, setLiveQuote] = React.useState(null);

  // Fetch live quote whenever symbol changes
  React.useEffect(() => {
    if (!form.code) return;
    setLiveQuote(null);
    fetch(`/api/quote/${form.code}`)
      .then(r => r.ok ? r.json() : null)
      .then(q => q && setLiveQuote(q))
      .catch(() => {});
  }, [form.code]);

  // Merge live quote over static symbol data for display
  const staticSym = SYMBOL_INDEX[form.code];
  const selectedSym = liveQuote
    ? { ...(staticSym || { code: form.code, name: form.code, market: "US" }),
        price: liveQuote.price, prevClose: liveQuote.prev_close, currency: liveQuote.currency }
    : staticSym;
  const cond = condMeta(form.cond);

  // computed: distance to threshold
  const numThr = parseFloat(form.threshold);
  const distance = !isNaN(numThr) && selectedSym ? (
    cond.isPrice
      ? ((numThr - selectedSym.price) / selectedSym.price * 100)
      : (numThr - ((selectedSym.price - selectedSym.prevClose) / selectedSym.prevClose * 100))
  ) : null;

  const pickSymbol = (sym) => {
    setForm(f => ({ ...f, code: sym.code, name: f.name || `${sym.name} 提醒` }));
  };

  const [formError, setFormError] = React.useState("");

  const submit = () => {
    if (!form.code || !form.threshold) return;
    const sym = SYMBOL_INDEX[form.code];
    const name = form.name || (sym ? `${sym.name} ${cond.symbol} ${form.threshold}` : `${form.code} ${cond.symbol} ${form.threshold}`);
    setFormError("");
    fetch("/api/alerts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol: form.code, name, condition: form.cond, value: parseFloat(form.threshold) }),
    }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(a => {
        setAlerts(prev => [a, ...prev]);
        setForm({ code: form.code, cond: "price_gte", threshold: "", name: "" });
      }).catch(e => setFormError(e.detail || "提交失败"));
  };

  const toggle = (id) => {
    const alert = alerts.find(a => a.id === id);
    if (!alert) return;
    fetch(`/api/alerts/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: !alert.enabled }),
    }).then(r => r.json()).then(updated => {
      setAlerts(prev => prev.map(a => a.id === id ? updated : a));
    }).catch(console.error);
  };

  const remove = (id) => {
    fetch(`/api/alerts/${id}`, { method: "DELETE" }).then(() => {
      setAlerts(prev => prev.filter(a => a.id !== id));
    }).catch(console.error);
  };

  const [editingAlert, setEditingAlert] = React.useState(null);

  const saveEdit = (id, patch, onError) => {
    fetch(`/api/alerts/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    }).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
      .then(updated => {
        setAlerts(prev => prev.map(a => a.id === id ? updated : a));
        setEditingAlert(null);
      }).catch(e => onError?.(e.detail || "保存失败"));
  };

  const reEnable = (id) => {
    fetch(`/api/alerts/${id}/reset`, { method: "POST" }).then(r => r.json()).then(updated => {
      setAlerts(prev => prev.map(a => a.id === id ? updated : a));
    }).catch(console.error);
  };

  const filtered = alerts.filter(a => {
    if (tab === "active" && !a.enabled) return false;
    if (tab === "triggered" && !a.triggered) return false;
    if (tab === "all") {}
    if (search) {
      const q = search.toLowerCase();
      return a.code.toLowerCase().includes(q) || a.name.toLowerCase().includes(q);
    }
    return true;
  });

  const counts = {
    active: alerts.filter(a => a.enabled).length,
    triggered: alerts.filter(a => a.triggered).length,
    all: alerts.length,
  };

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 01 · ALERTS"
        title="股票提醒"
        subtitle={`Stock Price Alerts · 美股 / 港股 / A 股 / 指数 · 触发后邮件通知 ${notifyEmail}`}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" icon="import" onClick={() => setShowImport(true)}>批量导入</Button>
            <Button variant="secondary" icon="mail" onClick={() => setShowEmail(true)}>
              邮件设置 <span style={{ marginLeft: 6, fontSize: 10, color: notifyEnabled ? "var(--down)" : "var(--ink-4)", fontWeight: 400 }}>· {notifyEnabled ? "ON" : "OFF"}</span>
            </Button>
          </div>
        }
      />

      {/* Stats strip */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 18 }}>
        <StatTile label="ACTIVE 监控中" value={counts.active} accent="var(--up)" hint="Cron */20 min"/>
        <StatTile label="TRIGGERED 已触发" value={counts.triggered} accent="var(--ink)" hint="本月 this month"/>
        <StatTile label="MARKETS 覆盖市场" value="3" accent="var(--info)" hint="US · HK · CN"/>
        <StatTile label="LAST CHECK 上次检查" value="2 min ago" mono={false} accent="var(--violet)" hint="next *:20"/>
      </div>

      {/* Two-column: form + symbol picker */}
      <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 14, marginBottom: 22 }}>
        {/* Symbol picker */}
        <Card padding={0}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
              <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>常用标的 Quick Pick</div>
              <Input
                value={search} onChange={() => {}}
                prefix={<Icon name="search" size={13}/>}
                placeholder="Search symbol…"
                style={{ width: 200, height: 30 }}
              />
            </div>
            <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
              {Object.keys(SYMBOLS).map(c => (
                <button key={c} onClick={() => setCategory(c)} style={{
                  padding: "5px 10px", fontSize: 11.5, fontWeight: 500,
                  background: category === c ? "var(--ink)" : "transparent",
                  color: category === c ? "#fff" : "var(--ink-3)",
                  border: "1px solid " + (category === c ? "var(--ink)" : "var(--line-2)"),
                  borderRadius: 6, cursor: "pointer",
                }}>{c}</button>
              ))}
            </div>
          </div>
          <div style={{ padding: 14, display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 260, overflowY: "auto" }} className="scroll">
            {SYMBOLS[category].map(s => (
              <SymbolChip key={s.code} sym={s} onClick={pickSymbol} selected={form.code === s.code}/>
            ))}
          </div>
        </Card>

        {/* Form */}
        <Card padding={0}>
          <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>添加提醒 New Alert</div>
            {selectedSym && (
              <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11, color: "var(--ink-4)" }}>
                <span className="pulse-dot" style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: "var(--up)" }}/>
                Live preview
              </div>
            )}
          </div>
          <div style={{ padding: 18 }}>
            {/* Selected symbol live preview */}
            {selectedSym && (
              <div style={{ background: "var(--bg-deep)", border: "1px solid var(--line)", borderRadius: 10, padding: 14, marginBottom: 14 }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                      <MarketDot market={selectedSym.market}/>
                      <span className="mono" style={{ fontWeight: 600, fontSize: 14 }}>{selectedSym.code}</span>
                      <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{selectedSym.name}</span>
                    </div>
                    <div className="mono" style={{ fontSize: 26, fontWeight: 700, marginTop: 4 }}>
                      {fmtMoney(selectedSym.price, selectedSym.currency)}
                    </div>
                    <div style={{ display: "flex", gap: 12, marginTop: 4, alignItems: "center", fontSize: 11.5 }}>
                      <ChangeNum value={(selectedSym.price - selectedSym.prevClose) / selectedSym.prevClose * 100} size="sm"/>
                      <span className="mono" style={{ color: "var(--ink-4)" }}>≈ ¥{fmtNum(toCNY(selectedSym.price, selectedSym.currency), 2)}</span>
                    </div>
                  </div>
                  <Sparkline data={selectedSym.spark} width={90} height={36} fill={true}/>
                </div>
              </div>
            )}

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 10 }}>
              <Field label="代码 Symbol">
                <Input value={form.code} onChange={v => setForm({ ...form, code: v.toUpperCase() })} prefix={<Icon name="dot" size={10} style={{ color: "var(--us)" }}/>}/>
              </Field>
              <Field label="条件 Condition">
                <Select value={form.cond} onChange={v => setForm({ ...form, cond: v })} options={COND_OPTIONS.map(o => ({ value: o.value, label: o.label }))} style={{ width: "100%" }}/>
              </Field>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1.3fr", gap: 10, marginBottom: 14 }}>
              <Field label={`阈值 Threshold ${cond.isPrice ? `(${selectedSym?.currency || "$"})` : "(%)"}`}>
                <Input
                  value={form.threshold}
                  onChange={v => setForm({ ...form, threshold: v })}
                  type="number"
                  placeholder={cond.isPrice ? selectedSym?.price.toFixed(0) : "5"}
                  suffix={cond.isPrice ? selectedSym?.currency : "%"}
                />
              </Field>
              <Field label="名称 Label (optional)">
                <Input value={form.name} onChange={v => setForm({ ...form, name: v })} placeholder="e.g. 突破新高 / 加仓信号"/>
              </Field>
            </div>

            {/* Distance hint */}
            {distance != null && (
              <div style={{
                marginBottom: 14, padding: "8px 12px", borderRadius: 8,
                background: Math.abs(distance) < 2 ? "var(--warn-soft)" : "var(--bg-deep)",
                fontSize: 12, color: "var(--ink-2)",
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <span>距离触发 {cond.isPrice ? "Distance" : "Δ"}</span>
                <span className="mono" style={{ fontWeight: 600, color: Math.abs(distance) < 2 ? "var(--warn)" : "var(--ink-2)" }}>
                  {distance > 0 ? "+" : ""}{distance.toFixed(2)}{cond.isPrice ? "%" : "pp"}
                  {Math.abs(distance) < 2 && " · 接近触发"}
                </span>
              </div>
            )}

            {formError && <div style={{ fontSize: 12, color: "var(--up)", padding: "6px 10px", background: "rgba(217,53,43,.06)", borderRadius: 6 }}>{formError}</div>}
            <Button variant="primary" icon="plus" size="lg" onClick={submit} style={{ width: "100%", justifyContent: "center" }}>
              添加提醒 Add Alert
            </Button>
          </div>
        </Card>
      </div>

      {/* Trigger timeline */}
      <Card padding={20} style={{ marginBottom: 22 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>触发历史 Trigger Timeline</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Last 14 days · {history.length} triggers</div>
          </div>
          <div style={{ display: "flex", gap: 10, fontSize: 11, color: "var(--ink-3)" }}>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, background: "var(--up)", borderRadius: 4 }}/>突破上行</span>
            <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}><span style={{ width: 8, height: 8, background: "var(--down)", borderRadius: 4 }}/>跌破下行</span>
          </div>
        </div>
        <div style={{ overflowX: "auto" }} className="scroll">
          <TriggerTimeline events={history} width={1380} height={100} days={14}/>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 12, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
          {history.slice().reverse().map((h, i) => {
            const cm = condMeta(h.cond);
            const chg = h.change_pct;
            return (
              <div key={i} style={{ display: "grid", gridTemplateColumns: "130px 90px 1fr 140px 80px", gap: 10, fontSize: 12, padding: "4px 0", alignItems: "center" }}>
                <span className="mono" style={{ color: "var(--ink-3)" }}>{h.time}</span>
                <span className="mono" style={{ fontWeight: 600 }}>{h.code}</span>
                <span style={{ color: "var(--ink-2)" }}>{h.name}</span>
                <span className="mono" style={{ color: cm.isUp ? "var(--up)" : "var(--down)", fontWeight: 600 }}>
                  {cm.symbol} {h.threshold}{!cm.isPrice ? "%" : ""} → {parseFloat(h.actual).toFixed(2)}{!cm.isPrice ? "%" : ""}
                </span>
                <span className="mono" style={{ color: chg >= 0 ? "var(--up)" : "var(--down)", fontSize: 11.5 }}>
                  {chg >= 0 ? "+" : ""}{parseFloat(chg).toFixed(2)}%
                </span>
              </div>
            );
          })}
        </div>
      </Card>

      {/* Alerts list */}
      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <Tabs
            variant="pill"
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "active",    label: "监控中 Active",    count: counts.active,    icon: "bolt" },
              { id: "triggered", label: "已触发 Triggered", count: counts.triggered, icon: "check" },
              { id: "all",       label: "全部 All",          count: counts.all },
            ]}
          />
          <Input value={search} onChange={setSearch} prefix={<Icon name="search" size={13}/>} placeholder="搜索代码或名称…" style={{ width: 240, height: 30 }}/>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "32px 1fr 110px 130px 100px 90px 80px 60px", gap: 12, padding: "10px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
          <span></span>
          <span>NAME · CODE</span>
          <span>CONDITION</span>
          <span style={{ textAlign: "right" }}>NOW</span>
          <span style={{ textAlign: "right" }}>THRESHOLD</span>
          <span style={{ textAlign: "right" }}>DISTANCE</span>
          <span style={{ textAlign: "center" }}>STATUS</span>
          <span style={{ textAlign: "right" }}></span>
        </div>

        {filtered.length === 0 && <Empty icon="bell" title="No alerts yet" hint="Pick a symbol above and add your first alert."/>}

        {filtered.map((a, idx) => (
          <AlertRow key={a.id} a={a} onToggle={toggle} onRemove={remove} onReEnable={reEnable} onEdit={setEditingAlert} last={idx === filtered.length - 1} liveQuotes={liveQuotes}/>
        ))}
      </Card>

      {editingAlert && (
        <EditAlertModal
          alert={editingAlert}
          onClose={() => setEditingAlert(null)}
          onSave={saveEdit}
        />
      )}

      {/* Import modal */}
      <Modal open={showImport} onClose={() => setShowImport(false)} title="批量导入提醒 Bulk Import" width={600}>
        <div style={{ padding: 20 }}>
          <div style={{ fontSize: 13, color: "var(--ink-3)", marginBottom: 12 }}>
            一行一条，格式：<span className="mono" style={{ background: "var(--bg-deep)", padding: "1px 5px", borderRadius: 3 }}>CODE COND THRESHOLD [NAME]</span>
          </div>
          <textarea defaultValue={`NVDA price_gte 150 突破新高
QQQ price_lte 490 加仓信号
0700.HK price_lte 380 腾讯加仓
^VIX price_gte 25 恐慌
600519.SS change_lte -3 茅台异动`}
            style={{
              width: "100%", height: 180, padding: 12, fontFamily: "IBM Plex Mono, monospace",
              fontSize: 12, border: "1px solid var(--line-2)", borderRadius: 8, resize: "vertical",
              background: "var(--paper-2)", color: "var(--ink)",
            }} className="scroll"
          />
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14 }}>
            <Button variant="secondary" onClick={() => setShowImport(false)}>取消</Button>
            <Button variant="primary" icon="check" onClick={() => setShowImport(false)}>导入 5 条</Button>
          </div>
        </div>
      </Modal>

      {/* Email settings modal */}
      <EmailSettingsModal
        open={showEmail} onClose={() => setShowEmail(false)}
        email={notifyEmail} setEmail={setNotifyEmail}
        enabled={notifyEnabled} setEnabled={setNotifyEnabled}
      />
    </div>
  );
};

const EmailSettingsModal = ({ open, onClose, email, setEmail, enabled, setEnabled }) => {
  const [draft, setDraft] = React.useState(email);
  React.useEffect(() => { setDraft(email); }, [email]);

  const save = () => {
    const trimmed = draft.trim();
    if (!/.+@.+\..+/.test(trimmed)) return;
    fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ notify_email: trimmed, notify_enabled: enabled }),
    }).then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(s => {
        setEmail(s.notify_email || "");
        setEnabled(!!s.notify_enabled);
        onClose();
      }).catch(console.error);
  };

  return (
    <Modal open={open} onClose={onClose} title="邮件通知 Email Notifications" width={400}>
      <div style={{ padding: "18px 20px 20px", display: "flex", flexDirection: "column", gap: 16 }}>
        <Field label="通知邮箱 Email">
          <Input
            value={draft}
            onChange={setDraft}
            prefix={<Icon name="mail" size={13}/>}
            placeholder="your@email.com"
          />
        </Field>

        <div style={{
          display: "flex", justifyContent: "space-between", alignItems: "center",
          padding: "12px 14px", background: "var(--bg-deep)", borderRadius: 8,
          border: "1px solid var(--line)",
        }}>
          <div>
            <div style={{ fontSize: 13, fontWeight: 500 }}>触发提醒通知</div>
            <div style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 2 }}>提醒触发时发送邮件</div>
          </div>
          <Toggle value={enabled} onChange={() => setEnabled(!enabled)} />
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 2 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" icon="check" onClick={save}>保存</Button>
        </div>
      </div>
    </Modal>
  );
};

const Field = ({ label, children }) => (
  <div>
    <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", marginBottom: 4 }}>{label}</div>
    {children}
  </div>
);

const StatTile = ({ label, value, hint, accent }) => (
  <Card padding={16}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div>
        <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".12em" }}>{label}</div>
        <div className="mono" style={{ fontSize: 24, fontWeight: 700, marginTop: 6 }}>{value}</div>
        {hint && <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>{hint}</div>}
      </div>
      <span style={{ width: 4, height: 28, borderRadius: 2, background: accent }}/>
    </div>
  </Card>
);

const AlertRow = ({ a, onToggle, onRemove, onReEnable, onEdit, last, liveQuotes }) => {
  const staticSym = SYMBOL_INDEX[a.code];
  const q = liveQuotes && liveQuotes[a.code];
  const sym = q
    ? { ...(staticSym || { code: a.code, name: a.code, market: "US" }),
        price: q.price, prevClose: q.prev_close, currency: q.currency }
    : staticSym;
  const cm = condMeta(a.cond);
  const isPriceCond = cm.isPrice;
  const ch = sym ? (sym.price - sym.prevClose) / sym.prevClose * 100 : 0;
  const distance = sym
    ? (isPriceCond ? ((a.threshold - sym.price) / sym.price * 100) : (a.threshold - ch))
    : null;
  const close = distance != null && Math.abs(distance) < 2;

  return (
    <div style={{
      display: "grid", gridTemplateColumns: "32px 1fr 110px 130px 100px 90px 80px 60px",
      gap: 12, padding: "12px 18px", alignItems: "center",
      borderBottom: last ? "none" : "1px solid var(--line)",
      background: a.triggered ? "rgba(217, 53, 43, .03)" : "transparent",
    }}>
      <Toggle value={a.enabled} onChange={() => onToggle(a.id)} size="sm"/>
      <div>
        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--ink)" }}>{a.name}</div>
        <div style={{ fontSize: 11.5, color: "var(--ink-4)", display: "flex", alignItems: "center", gap: 6, marginTop: 1 }}>
          <MarketDot market={sym?.market} size={6}/>
          <span className="mono">{a.code}</span>
          {sym && <span>· {sym.name}</span>}
          <span>· created {a.created}</span>
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
        <Badge tone={cm.isUp ? "up" : "down"} size="sm">
          {cm.symbol} {cm.isPrice ? "" : "% "}
        </Badge>
      </div>
      <div className="mono" style={{ textAlign: "right", fontSize: 13 }}>
        {sym ? (isPriceCond ? fmtMoney(sym.price, sym.currency, 2) : fmtPct(ch, 2)) : "—"}
      </div>
      <div className="mono" style={{ textAlign: "right", fontSize: 13, fontWeight: 600 }}>
        {isPriceCond ? fmtMoney(a.threshold, sym?.currency, 2) : fmtPct(a.threshold, 2)}
      </div>
      <div className="mono" style={{ textAlign: "right", fontSize: 12, color: close ? "var(--warn)" : "var(--ink-3)", fontWeight: close ? 600 : 500 }}>
        {distance != null ? `${distance > 0 ? "+" : ""}${distance.toFixed(1)}${isPriceCond ? "%" : "pp"}` : "—"}
      </div>
      <div style={{ textAlign: "center" }}>
        {a.triggered
          ? <Badge tone="up" solid size="sm">已触发</Badge>
          : a.enabled
            ? <Badge tone="down" size="sm">监控中</Badge>
            : <Badge tone="neutral" size="sm">已禁用</Badge>}
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 4 }}>
        {a.triggered && <button onClick={() => onReEnable(a.id)} title="重新启用" style={iconBtn}><Icon name="play" size={13}/></button>}
        <button onClick={() => onEdit(a)} title="编辑" style={iconBtn}><Icon name="edit" size={13}/></button>
        <button onClick={() => onRemove(a.id)} title="删除" style={iconBtn}><Icon name="trash" size={13}/></button>
      </div>
    </div>
  );
};

const iconBtn = {
  width: 24, height: 24, padding: 0, display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "transparent", border: "1px solid transparent", borderRadius: 5,
  color: "var(--ink-3)", cursor: "pointer",
};

const EditAlertModal = ({ alert, onClose, onSave }) => {
  const [name, setName] = React.useState(alert.name);
  const [cond, setCond] = React.useState(alert.cond);
  const [threshold, setThreshold] = React.useState(String(alert.threshold));
  const [error, setError] = React.useState("");

  const condMeta_ = condMeta(cond);
  const sym = SYMBOL_INDEX[alert.code];

  const submit = () => {
    const patch = {};
    if (name !== alert.name) patch.name = name;
    if (cond !== alert.cond) patch.condition = cond;
    const numThr = parseFloat(threshold);
    if (!isNaN(numThr) && numThr !== alert.threshold) patch.value = numThr;
    if (Object.keys(patch).length === 0) { onClose(); return; }
    setError("");
    onSave(alert.id, patch, setError);
  };

  return (
    <Modal open={true} onClose={onClose} title={`编辑提醒 · ${alert.code}`} width={480}>
      <div style={{ padding: "18px 20px 20px", display: "flex", flexDirection: "column", gap: 14 }}>
        <div style={{ display: "flex", gap: 8, padding: "10px 12px", background: "var(--bg-deep)", borderRadius: 8, fontSize: 12, color: "var(--ink-3)", alignItems: "center" }}>
          <MarketDot market={sym?.market} size={7}/>
          <span className="mono" style={{ fontWeight: 600, color: "var(--ink)" }}>{alert.code}</span>
          {sym && <span>{sym.name}</span>}
          <span style={{ marginLeft: "auto", color: "var(--ink-4)" }}>created {alert.created}</span>
        </div>

        <Field label="名称 Label">
          <Input value={name} onChange={setName} placeholder="提醒名称"/>
        </Field>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10 }}>
          <Field label="条件 Condition">
            <Select value={cond} onChange={setCond} options={COND_OPTIONS.map(o => ({ value: o.value, label: o.label }))} style={{ width: "100%" }}/>
          </Field>
          <Field label={`阈值 Threshold ${condMeta_.isPrice ? `(${sym?.currency || "$"})` : "(%)"}`}>
            <Input value={threshold} onChange={setThreshold} type="number" suffix={condMeta_.isPrice ? (sym?.currency || "$") : "%"}/>
          </Field>
        </div>

        {error && <div style={{ fontSize: 12, color: "var(--up)", padding: "6px 10px", background: "rgba(217,53,43,.06)", borderRadius: 6 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, paddingTop: 4 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" icon="check" onClick={submit}>保存</Button>
        </div>
      </div>
    </Modal>
  );
};

window.Alerts = Alerts;
