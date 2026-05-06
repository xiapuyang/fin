/* Dashboard — overview of all 5 modules + market summary */

const STATE_LABEL = {
  REGULAR: "盘中 Open",
  PRE:     "盘前 Pre",
  POST:    "盘后 After",
  CLOSED:  "休市 Closed",
};

const MARKET_HOURS = (now = new Date()) => {
  const day = now.getUTCDay();
  const t = now.getUTCHours() * 60 + now.getUTCMinutes();
  const inRange = (lo, hi) => t >= lo && t < hi;
  const weekday = day >= 1 && day <= 5;

  // US: NYSE/NASDAQ (EDT = UTC-4)
  // PRE  04:00-09:30 EDT = 08:00-13:30 UTC
  // REG  09:30-16:00 EDT = 13:30-20:00 UTC
  // POST 16:00-20:00 EDT = 20:00-00:00 UTC
  const usState = !weekday ? "CLOSED"
    : inRange(13 * 60 + 30, 20 * 60) ? "REGULAR"
    : inRange(20 * 60, 24 * 60)       ? "POST"
    : inRange(8 * 60, 13 * 60 + 30)  ? "PRE"
    : "CLOSED";

  // HK: HKEX Mon-Fri 09:30-12:00 and 13:00-16:00 HKT = 01:30-04:00 and 05:00-08:00 UTC
  const hkState = weekday && (inRange(1 * 60 + 30, 4 * 60) || inRange(5 * 60, 8 * 60)) ? "REGULAR" : "CLOSED";

  // CN: SSE/SZSE Mon-Fri 09:30-11:30 and 13:00-15:00 CST = 01:30-03:30 and 05:00-07:00 UTC
  const cnState = weekday && (inRange(1 * 60 + 30, 3 * 60 + 30) || inRange(5 * 60, 7 * 60)) ? "REGULAR" : "CLOSED";

  const mk = (state) => ({ state, label: STATE_LABEL[state] });
  return { US: mk(usState), HK: mk(hkState), CN: mk(cnState) };
};

const Dashboard = ({ onNavigate, alerts, history, timezone = "America/Toronto" }) => {
  const [now, setNow] = React.useState(new Date());
  const [serverStates, setServerStates] = React.useState({});

  React.useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 60 * 1000);
    return () => clearInterval(t);
  }, []);

  // Fetch authoritative market states from check_market_state.py output.
  // Falls back to time-based calculation if the file is missing or stale (>5min).
  React.useEffect(() => {
    const ctrl = new AbortController();
    const fetch_ = () =>
      fetch("/api/market-states", { signal: ctrl.signal })
        .then(r => r.ok ? r.json() : null)
        .then(d => d && setServerStates(d))
        .catch(() => {});
    fetch_();
    const t = setInterval(fetch_, 60 * 1000);
    return () => { clearInterval(t); ctrl.abort(); };
  }, []);

  const timeBased = MARKET_HOURS(now);
  const serverFresh = serverStates.updated_at &&
    (Date.now() - new Date(serverStates.updated_at).getTime()) < 5 * 60 * 1000;
  const market = Object.fromEntries(
    Object.entries(timeBased).map(([k, v]) => {
      const state = serverFresh ? (serverStates[k] || v.state) : v.state;
      return [k, { state, label: STATE_LABEL[state] || v.label }];
    })
  );

  const all = Object.values(SYMBOLS).flat();

  const [watchlist, setWatchlist] = React.useState([]);
  const [watchQuotes, setWatchQuotes] = React.useState({});
  const [alertQuotes, setAlertQuotes] = React.useState({});

  React.useEffect(() => {
    fetch("/api/watchlist").then(r => r.json()).then(setWatchlist).catch(console.error);
  }, []);

  // Batch-fetch prices for watchlist + enabled alerts in one request
  React.useEffect(() => {
    const ctrl = new AbortController();
    const watchSyms = watchlist.map(w => w.symbol);
    const alertSyms = alerts.filter(a => a.enabled).map(a => a.code);
    const all = [...new Set([...watchSyms, ...alertSyms])];
    if (!all.length) return () => ctrl.abort();
    fetch(`/api/prices?symbols=${all.map(encodeURIComponent).join(",")}`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setWatchQuotes(prev => {
          const next = { ...prev };
          watchSyms.forEach(s => { if (data[s]) next[s] = data[s]; });
          return next;
        });
        setAlertQuotes(prev => {
          const next = { ...prev };
          alertSyms.forEach(s => { if (data[s]) next[s] = data[s]; });
          return next;
        });
      })
      .catch(() => {});
    return () => ctrl.abort();
  }, [watchlist.map(w => w.symbol).join(","), alerts.filter(a => a.enabled).map(a => a.code).join(",")]);

  const watch = watchlist.map(w => {
    const q = watchQuotes[w.symbol];
    const base = SYMBOL_INDEX[w.symbol] || { code: w.symbol, name: w.name || w.symbol, market: w.market || "US", currency: w.currency || "USD" };
    return q ? { ...base, price: q.price, prevClose: q.prev_close } : base;
  }).filter(s => s.price != null);

  const activeAlerts = alerts.filter(a => a.enabled).length;
  const triggered = alerts.filter(a => a.triggered).length;

  // Allocation (canonical net worth source — declared first so dashboard numbers reconcile)
  const allocation = [
    { label: "美股科技", value: 1340000, color: "#1F4FE0" },
    { label: "美股 ETF", value: 280000, color: "#5C8AE6" },
    { label: "港股", value: 220000, color: "#B8447B" },
    { label: "A 股", value: 95000, color: "#C8460F" },
    { label: "黄金", value: 78000, color: "#C8821F" },
    { label: "现金", value: 250000, color: "#5C6270" },
  ];

  const netWorth = allocation.reduce((s, a) => s + a.value, 0); // ¥2.263M
  const pnlPct = 24.3; // mock — coherent with display

  const modules = [
    { id: "alerts",   icon: "bell",      kicker: "MODULE 01", title: "提醒",     en: "Alerts",       color: "var(--up)",     stat: `${activeAlerts} active · ${triggered} triggered`, blurb: "盘中价格 & 涨跌触发邮件" },
    { id: "holdings", icon: "wallet",    kicker: "MODULE 02", title: "投资组合", en: "Portfolio",     color: "var(--info)",   stat: `Portfolio · ${fmtPct(pnlPct,1)}`, blurb: "成本 & 盈亏 & 年化 IRR" },
    { id: "ledger",   icon: "book",      kicker: "MODULE 03", title: "记账",     en: "Ledger",       color: "var(--violet)", stat: `${LEDGER.length} entries this week`, blurb: "支出收入 & 月度报表" },
    { id: "balance",  icon: "target",    kicker: "MODULE 04", title: "资产负债",  en: "Balance Sheet",color: "var(--warn)",   stat: `${BS_ITEMS.length} items · ${BS_SNAPSHOTS.length} 快照`, blurb: "净资产 & 历史快照" },
    { id: "fire",     icon: "spark",     kicker: "MODULE 05", title: "退休计划",  en: "FIRE",         color: "var(--down)",   stat: "11.2y to 财务自由", blurb: "FIRE 数字 & 复利推演 & 里程碑" },
  ];

  // Net worth history (mock series, ends at canonical netWorth)
  const netWorthSeries = [
    { label: "Jun", value: 1820000 }, { label: "Jul", value: 1864000 },
    { label: "Aug", value: 1942000 }, { label: "Sep", value: 1981000 },
    { label: "Oct", value: 2014000 }, { label: "Nov", value: 2102000 },
    { label: "Dec", value: 2154000 }, { label: "Jan", value: 2178000 },
    { label: "Feb", value: 2201000 }, { label: "Mar", value: 2218000 },
    { label: "Apr", value: 2231000 }, { label: "May", value: netWorth },
  ];
  const prevMonth = 2231000;
  const momPct = (netWorth - prevMonth) / prevMonth * 100;

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      {/* Welcome */}
      <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", marginBottom: 22, gap: 24 }}>
        <div>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".18em", textTransform: "uppercase", color: "var(--ink-4)" }}>{(() => {
            const tzDate = new Date(now.toLocaleString("en-US", { timeZone: timezone }));
            const y = tzDate.getFullYear();
            const start = new Date(y, 0, 1);
            const week = Math.ceil(((tzDate - start) / 86400000 + start.getDay() + 1) / 7);
            const months = ["JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"];
            return `${y} · WEEK ${String(week).padStart(2,"0")} · ${months[tzDate.getMonth()]} ${String(tzDate.getDate()).padStart(2,"0")}`;
          })()}</div>
          <h1 className="serif-cn" style={{ fontSize: 36, fontWeight: 700, margin: "6px 0 4px", letterSpacing: ".01em" }}>下午好，sharp</h1>
          <div style={{ fontSize: 14, color: "var(--ink-3)" }}>Net worth tracking toward FIRE · 11.2y to 财务自由</div>
        </div>
        <div style={{ display: "flex", gap: 14, alignItems: "center" }}>
          {Object.entries(market).map(([k, v]) => (
            <div key={k} style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 2 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <MarketDot market={k} size={6}/>
                <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-3)", letterSpacing: ".05em" }}>
                  {{ US: "US", HK: "HK", CN: "CN" }[k]}
                </span>
                <span className={"pulse-dot"} style={{
                  display: "inline-block", width: 6, height: 6, borderRadius: 3,
                  background: v.state === "REGULAR" ? "var(--up)"
                    : (v.state === "PRE" || v.state === "POST") ? "var(--warn)"
                    : "var(--ink-5)",
                }}/>
              </div>
              <div style={{ fontSize: 10.5, color: "var(--ink-4)" }}>{v.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Top stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
            <div>
              <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>NET WORTH · 净资产</div>
              <div className="mono" style={{ fontSize: 36, fontWeight: 700, marginTop: 6, letterSpacing: "-.01em" }}>
                ¥{(netWorth / 1000000).toFixed(2)}<span style={{ fontSize: 18, color: "var(--ink-3)", fontWeight: 500 }}>M</span>
              </div>
              <div style={{ display: "flex", gap: 12, marginTop: 4, alignItems: "center" }}>
                <ChangeNum value={momPct} format="pct" size="sm"/>
                <span style={{ fontSize: 12, color: "var(--ink-4)" }}>since last month</span>
              </div>
            </div>
            <Sparkline data={netWorthSeries.map(d => d.value)} width={120} height={40} color="var(--up)" fill={true}/>
          </div>
          <div style={{ marginTop: 16, paddingTop: 16, borderTop: "1px dashed var(--line)" }}>
            <AreaChart data={netWorthSeries} width={420} height={120} color="var(--ink)" fillOpacity={.06} yLabels={3}/>
          </div>
        </Card>

        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>ALLOCATION · 仓位</div>
          <div style={{ display: "flex", alignItems: "center", gap: 14, marginTop: 8 }}>
            <Donut
              data={allocation} size={140} thickness={20}
              centerValue={`${(allocation.reduce((s, d) => s + d.value, 0) / 1000000).toFixed(2)}M`}
              centerSub="¥ CNY"
            />
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 11.5, flex: 1 }}>
              {allocation.map(a => {
                const pct = a.value / allocation.reduce((s, d) => s + d.value, 0) * 100;
                return (
                  <div key={a.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: a.color, flexShrink: 0 }}/>
                    <span style={{ flex: 1, color: "var(--ink-2)" }}>{a.label}</span>
                    <span className="mono" style={{ color: "var(--ink-3)", fontWeight: 500 }}>{pct.toFixed(0)}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        </Card>

        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>FIRE TARGET · 财务自由</div>
          <div style={{ display: "flex", gap: 16, alignItems: "center", marginTop: 12 }}>
            <ProgressRing value={netWorth / 6000000} size={88} thickness={9} color="var(--down)"/>
            <div>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>{((netWorth / 6000000) * 100).toFixed(1)}<span style={{ fontSize: 14, color: "var(--ink-3)" }}>%</span></div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>of ¥6M target</div>
            </div>
          </div>
          <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px dashed var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>Years to go</div>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700 }}>11.2<span style={{ fontSize: 14, color: "var(--ink-3)" }}>y</span></div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>Required CAGR</div>
              <div className="mono" style={{ fontSize: 22, fontWeight: 700, color: "var(--up)" }}>10.4<span style={{ fontSize: 14 }}>%</span></div>
            </div>
          </div>
        </Card>
      </div>

      {/* Modules grid */}
      <SectionHeader kicker="MODULES" title="模块导航" subtitle="Local-first · zero cloud · five focused modules"/>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 12, marginBottom: 32 }}>
        {modules.map(m => (
          <ModuleCard key={m.id} mod={m} onClick={() => onNavigate(m.id)}/>
        ))}
      </div>

      {/* Bottom — watchlist + alerts overview */}
      <div style={{ display: "grid", gridTemplateColumns: "1.6fr 1fr", gap: 14 }}>
        <Card padding={0}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>关注列表 Watchlist</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{watchlist.length} 支 · 自选标的</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrow-right" onClick={() => onNavigate({ route: "alerts", category: WATCHLIST_TAB })}>Manage</Button>
          </div>
          <div>
            {watch.length === 0 && (
              <Empty icon="bell" title="自选为空" hint="在提醒页搜索标的并添加到自选"/>
            )}
            {watch.map((s, i) => {
              const ch = (s.price - s.prevClose) / s.prevClose * 100;
              return (
                <div key={s.code} style={{
                  padding: "12px 20px", display: "grid", gridTemplateColumns: "auto 1fr 90px 120px 80px", gap: 16, alignItems: "center",
                  borderBottom: i < watch.length - 1 ? "1px solid var(--line)" : "none",
                }}>
                  <MarketDot market={s.market}/>
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mono" style={{ fontWeight: 600, fontSize: 13 }}>{s.code}</span>
                      <span style={{ fontSize: 12, color: "var(--ink-3)" }}>{s.name}</span>
                    </div>
                  </div>
                  <Sparkline data={s.spark} width={90} height={26} fill={true}/>
                  <div className="mono" style={{ textAlign: "right", fontSize: 14, fontWeight: 600 }}>
                    {fmtMoney(s.price, s.currency, 2)}
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <ChangeNum value={ch} size="sm"/>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card padding={0}>
          <div style={{ padding: "16px 20px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>提醒概览 Alerts</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>{activeAlerts} active · {triggered} fired this month</div>
            </div>
            <Button size="sm" variant="ghost" iconRight="arrow-right" onClick={() => onNavigate("alerts")}>查看全部</Button>
          </div>
          <div style={{ padding: "10px 14px" }}>
            {alerts.filter(a => a.enabled).slice(0, 10).map(a => {
              const q = alertQuotes[a.code];
              const isPriceCond = a.cond.startsWith("price");
              const ch = q ? (q.price - q.prev_close) / q.prev_close * 100 : null;
              const distance = q
                ? (isPriceCond
                    ? (a.threshold - q.price) / q.price * 100
                    : a.threshold - ch)
                : null;
              const condLabel = { price_gte: "≥", price_lte: "≤", change_gte: "Δ≥", change_lte: "Δ≤" }[a.cond];
              return (
                <div key={a.id} style={{ padding: "8px 6px", display: "flex", alignItems: "center", gap: 10, borderRadius: 6 }}>
                  <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: 3, background: "var(--up)", flexShrink: 0 }}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 500, color: "var(--ink-2)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{a.name}</div>
                    <div style={{ fontSize: 11, color: "var(--ink-4)", display: "flex", alignItems: "center", gap: 6 }}>
                      <span className="mono">{a.code}</span>
                      <span>·</span>
                      <span className="mono">{condLabel} {a.threshold}{isPriceCond ? "" : "%"}</span>
                    </div>
                  </div>
                  <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                    {distance != null && isFinite(distance)
                      ? `${Math.abs(distance).toFixed(1)}${isPriceCond ? "%" : "pp"} away`
                      : "—"}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
};

const ModuleCard = ({ mod, onClick }) => {
  const [hov, setHov] = React.useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHov(true)} onMouseLeave={() => setHov(false)}
      style={{
        background: "var(--paper)", border: "1px solid var(--line)",
        borderRadius: "var(--radius-lg)", padding: 18, cursor: "pointer",
        transition: "transform .15s, box-shadow .2s, border-color .15s",
        boxShadow: hov ? "var(--shadow-md)" : "var(--shadow-sm)",
        transform: hov ? "translateY(-2px)" : "none",
        borderColor: hov ? "var(--line-strong)" : "var(--line)",
        position: "relative", overflow: "hidden",
      }}>
      <div style={{
        position: "absolute", top: 0, left: 0, width: 3, height: "100%", background: mod.color,
      }}/>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span style={{
          width: 32, height: 32, borderRadius: 8, background: "var(--bg-deep)",
          display: "inline-flex", alignItems: "center", justifyContent: "center", color: mod.color,
        }}><Icon name={mod.icon} size={17}/></span>
        <Icon name="arrow-right" size={14} style={{ color: hov ? "var(--ink)" : "var(--ink-5)", transition: "color .15s, transform .15s", transform: hov ? "translateX(2px)" : "none" }}/>
      </div>
      <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: ".15em", color: "var(--ink-4)", marginTop: 14 }}>{mod.kicker}</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 8, marginTop: 4 }}>
        <span className="serif-cn" style={{ fontSize: 22, fontWeight: 700 }}>{mod.title}</span>
        <span style={{ fontSize: 12, color: "var(--ink-4)", fontWeight: 500 }}>{mod.en}</span>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 6, lineHeight: 1.45 }}>{mod.blurb}</div>
      <div className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 12, paddingTop: 10, borderTop: "1px dashed var(--line)" }}>{mod.stat}</div>
    </div>
  );
};

window.Dashboard = Dashboard;
