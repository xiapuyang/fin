/* Module 04 — Balance Sheet
   API-wired: snapshots, items, accounts all loaded from backend.
   FX conversion uses global FX object + currency prop from TopBar.
*/

const BALANCE_CATEGORIES = ["现金","存款","理财","投资","期权","固定资产","房产","社保","外债","信用卡","贷款","其他贷款"];

const BALANCE_CAT_COLORS = {
  "现金":     "#1F8A4C",
  "存款":     "#0E7A5A",
  "理财":     "#2D9E6E",
  "投资":     "#1F4FE0",
  "期权":     "#7A1F4F",
  "固定资产": "#6B4FB8",
  "房产":     "#4B3580",
  "社保":     "#B8447B",
  "外债":     "#C8821F",
  "信用卡":   "#C03A3A",
  "贷款":     "#9A4D2E",
  "其他贷款": "#B85C2E",
};

// Convert item.amount (in item.currency) → display currency
const toDisplay = (amount, ccy, displayCcy) =>
  amount * (FX[ccy] || 1) / (FX[displayCcy] || 1);

const symFor = (ccy) => CURRENCY_SYMBOL[ccy] || "¥";
const fmtDisplay = (amount, ccy, displayCcy, dp = 0) => {
  const v = toDisplay(amount, ccy, displayCcy);
  return symFor(displayCcy) + fmtNum(v, dp);
};

// ── Main component ────────────────────────────────────────────────────────────

const BalanceSheet = ({ currency = "CNY" }) => {
  const [snapshots, setSnapshots] = React.useState([]);
  const [items, setItems]         = React.useState([]);
  const [allItems, setAllItems]   = React.useState([]);
  const [accounts, setAccounts]   = React.useState([]);
  const [loading, setLoading]     = React.useState(true);
  const [snapId, setSnapId]       = React.useState(null);
  const [sideFilter, setSideFilter] = React.useState("all");
  const [accountFilter, setAccountFilter] = React.useState(null);

  const [showSnapMenu, setShowSnapMenu]       = React.useState(false);
  const [editItem, setEditItem]               = React.useState(null);
  const [copyItem, setCopyItem]               = React.useState(null);
  const [historyItem, setHistoryItem]         = React.useState(null);
  const [showCopySnap, setShowCopySnap]       = React.useState(false);
  const [showEditSnap, setShowEditSnap]       = React.useState(false);
  const [showInjectHoldings, setShowInjectHoldings] = React.useState(false);
  const [showManageAccounts, setShowManageAccounts] = React.useState(false);
  const [deleteTarget, setDeleteTarget]       = React.useState(null);

  // ── Data loading ───────────────────────────────────────────────────────────

  const loadAll = React.useCallback(async () => {
    setLoading(true);
    try {
      const [snaps, ai, accts] = await Promise.all([
        apiGetBalanceSnapshots(),
        apiGetAllBalanceItems(),
        apiGetBalanceAccounts(),
      ]);
      setSnapshots(snaps);
      setAllItems(ai);
      setAccounts(accts);
      if (snaps.length > 0) {
        const last = snaps[snaps.length - 1];
        setSnapId(prev => prev || last.id);
      }
    } finally {
      setLoading(false);
    }
  }, []);

  const loadItems = React.useCallback(async (sid) => {
    if (!sid) return;
    const its = await apiGetBalanceItems(sid);
    setItems(its);
  }, []);

  React.useEffect(() => { loadAll(); }, [loadAll]);
  React.useEffect(() => { loadItems(snapId); }, [snapId, loadItems]);

  // ── Derived ────────────────────────────────────────────────────────────────

  const snap     = snapshots.find(s => s.id === snapId) || null;
  const isLatest = snap && snapshots.length > 0 && snap.id === snapshots[snapshots.length - 1].id;

  const toCNY = (it) => it.amount * (FX[it.currency] || 1);
  const totalAssets      = items.filter(i => i.side === "asset")    .reduce((s, i) => s + toCNY(i), 0);
  const totalLiabilities = items.filter(i => i.side === "liability").reduce((s, i) => s + toCNY(i), 0);
  const netWorth = totalAssets - totalLiabilities;

  const liquidAssets = items.filter(i => i.side === "asset" && ["现金","理财","投资"].includes(i.category))
    .reduce((s, i) => s + toCNY(i), 0);

  // Net worth series across all snapshots
  const snapSeries = snapshots.map(s => {
    const its = allItems.filter(i => i.snapshot_id === s.id);
    const a = its.filter(i => i.side === "asset")    .reduce((sum, i) => sum + toCNY(i), 0);
    const l = its.filter(i => i.side === "liability").reduce((sum, i) => sum + toCNY(i), 0);
    return { id: s.id, date: s.snapshot_date, label: s.label, net: a - l, assets: a, liabilities: l };
  });

  const snapIdx = snapSeries.findIndex(s => s.id === snapId);
  const prevSnap = snapIdx > 0 ? snapSeries[snapIdx - 1] : null;
  const delta    = prevSnap ? netWorth - prevSnap.net : 0;
  const deltaPct = prevSnap && prevSnap.net ? (delta / prevSnap.net) * 100 : 0;

  const aggCat = (side) => {
    const cats = {};
    items.filter(i => i.side === side).forEach(i => {
      if (!cats[i.category]) cats[i.category] = 0;
      cats[i.category] += toCNY(i);
    });
    return BALANCE_CATEGORIES
      .map(c => ({ label: c, value: cats[c] || 0, color: BALANCE_CAT_COLORS[c] }))
      .filter(c => c.value > 0);
  };
  const assetCats  = aggCat("asset").map(c => ({ ...c, label: I18N.tCat(c.label) }));
  const liabCats   = aggCat("liability").map(c => ({ ...c, label: I18N.tCat(c.label) }));
  const assetItems = items.filter(i => i.side === "asset");
  const liabItems  = items.filter(i => i.side === "liability");

  const sideFiltered = sideFilter === "all" ? items : items.filter(i => i.side === sideFilter);
  const filtered = accountFilter ? sideFiltered.filter(i => i.account_name === accountFilter) : sideFiltered;
  const sortedFiltered = [...filtered].sort((a, b) => toCNY(b) - toCNY(a));
  const accountNames = [...new Set(items.map(i => i.account_name).filter(Boolean))].sort();

  // ── Actions ────────────────────────────────────────────────────────────────

  const handleDeleteItem = async (id) => {
    await apiDeleteBalanceItem(id);
    setDeleteTarget(null);
    await loadItems(snapId);
    const ai = await apiGetAllBalanceItems();
    setAllItems(ai);
  };

  const handleDeleteSnapshot = async (id) => {
    await apiDeleteBalanceSnapshot(id);
    setDeleteTarget(null);
    const snaps = await apiGetBalanceSnapshots();
    setSnapshots(snaps);
    const ai = await apiGetAllBalanceItems();
    setAllItems(ai);
    if (snaps.length > 0) {
      const newId = snaps[snaps.length - 1].id;
      setSnapId(newId);
    } else {
      setSnapId(null);
      setItems([]);
    }
  };

  const handleItemSaved = async () => {
    setEditItem(null);
    await loadItems(snapId);
    const ai = await apiGetAllBalanceItems();
    setAllItems(ai);
    const snaps = await apiGetBalanceSnapshots(); // refresh item_count
    setSnapshots(snaps);
  };

  const handleSnapUpdated = async () => {
    setShowEditSnap(false);
    const snaps = await apiGetBalanceSnapshots();
    setSnapshots(snaps);
  };

  const handleSnapCreated = async (newId) => {
    setShowCopySnap(false);
    const snaps = await apiGetBalanceSnapshots();
    setSnapshots(snaps);
    const ai = await apiGetAllBalanceItems();
    setAllItems(ai);
    setSnapId(newId);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) return (
    <div style={{ padding: "80px 32px", textAlign: "center", color: "var(--ink-4)" }}>
      <div style={{ fontSize: 14 }}>{I18N.t("base.empty.loading")}</div>
    </div>
  );

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 04 · BALANCE SHEET"
        title={I18N.t("balance.title")}
        subtitle={I18N.t("balance.subtitle")}
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" icon="settings" onClick={() => setShowManageAccounts(true)}>{I18N.t("balance.btn.accounts")}</Button>
            {snap && <Button variant="secondary" icon="copy" onClick={() => setShowCopySnap(true)}>{I18N.t("balance.btn.copySnap")}</Button>}
            <Button variant="primary" icon="plus" onClick={() => setEditItem({})}>{I18N.t("balance.btn.addItem")}</Button>
          </div>
        }
      />

      {/* Snapshot selector bar */}
      <SnapBar
        snapshots={snapshots}
        snapId={snapId}
        setSnapId={(id) => { setSnapId(id); setShowSnapMenu(false); }}
        snap={snap}
        isLatest={isLatest}
        showSnapMenu={showSnapMenu}
        setShowSnapMenu={setShowSnapMenu}
        snapSeries={snapSeries}
        onInjectHoldings={() => setShowInjectHoldings(true)}
        onEditSnap={() => setShowEditSnap(true)}
        onDeleteSnap={(id) => setDeleteTarget({ type: "snapshot", id })}
      />

      {/* Summary tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{I18N.t("balance.stat.netWorth")}</div>
          <div className="mono" style={{ fontSize: 38, fontWeight: 700, marginTop: 6 }}>
            <Private>{symFor(currency)}{fmtNum(toDisplay(netWorth, "CNY", currency), 0)}</Private>
          </div>
          {prevSnap && (
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4, display: "flex", alignItems: "center", gap: 8 }}>
              <ChangeNum value={deltaPct} size="sm"/>
              <span>vs {prevSnap.date}</span>
            </div>
          )}
          <div style={{ marginTop: 14, paddingTop: 12, borderTop: "1px dashed var(--line)" }}>
            {snapSeries.length > 1 && <NetWorthTrend series={snapSeries} highlightId={snapId}/>}
          </div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{I18N.t("balance.stat.assets")}</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--down)" }}>
            <Private>+{symFor(currency)}{fmtNum(toDisplay(totalAssets, "CNY", currency), 0)}</Private>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{assetItems.length} {I18N.t("balance.stat.items")} · {assetCats.length} {I18N.t("balance.stat.types")}</div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{I18N.t("balance.stat.liabilities")}</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--up)" }}>
            <Private>−{symFor(currency)}{fmtNum(toDisplay(totalLiabilities, "CNY", currency), 0)}</Private>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
            {items.filter(i=>i.side==="liability").length} {I18N.t("balance.stat.items")} · {I18N.t("balance.stat.liabRate")} {totalAssets ? (totalLiabilities/totalAssets*100).toFixed(0) : 0}%
          </div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>{I18N.t("balance.stat.liquidity")}</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6 }}>
            <Private>{symFor(currency)}{fmtNum(toDisplay(liquidAssets, "CNY", currency), 0)}</Private>
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
            {I18N.tf("balance.stat.liquid.detail", { pct: totalAssets ? (liquidAssets/totalAssets*100).toFixed(0) : 0 })}
          </div>
        </Card>
      </div>

      {/* Category breakdowns */}
      {(assetCats.length > 0 || liabCats.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 18 }}>
          <CatBreakdownCard title={I18N.t("balance.catBreakdown.assets")} cats={assetCats} total={totalAssets} currency={currency}/>
          <CatBreakdownCard title={I18N.t("balance.catBreakdown.liab")} cats={liabCats} total={totalLiabilities} currency={currency}/>
        </div>
      )}

      {/* Account breakdowns */}
      {(assetItems.length > 0 || liabItems.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 18 }}>
          <AccountBreakdownCard title={I18N.t("balance.acctBreakdown.assets")} items={assetItems} total={totalAssets} currency={currency}/>
          <AccountBreakdownCard title={I18N.t("balance.acctBreakdown.liab")} items={liabItems} total={totalLiabilities} currency={currency}/>
        </div>
      )}

      {/* Detail table */}
      <Card padding={0} style={{ marginBottom: 18 }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 10 }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>{I18N.t("balance.items.title")}</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>{I18N.t("balance.items.hint")}</div>
          </div>
          <Tabs variant="pill" value={sideFilter} onChange={v => { setSideFilter(v); setAccountFilter(null); }} tabs={[
            { id: "all",       label: `${I18N.t("balance.items.tab.all")} ${items.length}` },
            { id: "asset",     label: `${I18N.t("balance.items.tab.asset")} ${items.filter(i=>i.side==="asset").length}` },
            { id: "liability", label: `${I18N.t("balance.items.tab.liability")} ${items.filter(i=>i.side==="liability").length}` },
          ]}/>
        </div>
        {accountNames.length > 0 && (
          <div style={{ padding: "8px 18px", borderBottom: "1px solid var(--line)", display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
            <button onClick={() => setAccountFilter(null)} style={{
              padding: "3px 10px", borderRadius: 20, border: "1px solid " + (!accountFilter ? "var(--ink)" : "var(--line)"),
              background: !accountFilter ? "var(--ink)" : "transparent",
              color: !accountFilter ? "var(--paper)" : "var(--ink-3)",
              fontSize: 11.5, fontWeight: 600, cursor: "pointer",
            }}>{I18N.t("balance.items.tab.all")}</button>
            {accountNames.map(name => {
              const color = entityColor(name);
              const active = accountFilter === name;
              return (
                <button key={name} onClick={() => setAccountFilter(active ? null : name)} style={{
                  padding: "3px 10px", borderRadius: 20,
                  border: "1px solid " + (active ? color : color + "55"),
                  background: active ? color : color + "18",
                  color: active ? "#fff" : color,
                  fontSize: 11.5, fontWeight: 600, cursor: "pointer",
                }}>{name}</button>
              );
            })}
          </div>
        )}
        {sortedFiltered.length === 0 ? (
          <div style={{ padding: "40px 18px", textAlign: "center", color: "var(--ink-4)", fontSize: 13 }}>
            {I18N.t("balance.items.empty")} <button style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink)", textDecoration: "underline", fontSize: 13 }} onClick={() => setEditItem({})}>{I18N.t("balance.items.empty.link")}</button>
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1.6fr 100px 80px 130px 130px 1fr 72px", gap: 10, padding: "9px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
              <span>{I18N.t("balance.col.name")}</span><span>{I18N.t("balance.col.category")}</span><span>{I18N.t("balance.col.side")}</span>
              <span style={{ textAlign: "right" }}>{I18N.t("balance.col.amount")}</span>
              <span style={{ textAlign: "right" }}>≈ {currency}</span>
              <span>{I18N.t("balance.col.note")}</span>
              <span></span>
            </div>
            {sortedFiltered.map((it, i, arr) => (
              <ItemRow
                key={it.id}
                item={it}
                currency={currency}
                last={i === arr.length - 1}
                onClick={() => setHistoryItem(it)}
                onEdit={(e) => { e.stopPropagation(); setEditItem(it); }}
                onDelete={(e) => { e.stopPropagation(); setDeleteTarget({ type: "item", id: it.id }); }}
                onCopy={(e) => { e.stopPropagation(); setCopyItem(it); }}
              />
            ))}
          </>
        )}
      </Card>

      {/* Modals */}
      {editItem !== null && (
        <ItemModal
          item={editItem}
          snapId={snapId}
          accounts={accounts}
          onClose={() => setEditItem(null)}
          onDone={handleItemSaved}
        />
      )}
      {historyItem && (
        <HistoryModal
          item={historyItem}
          allItems={allItems}
          snapshots={snapshots}
          currency={currency}
          onClose={() => setHistoryItem(null)}
        />
      )}
      {showInjectHoldings && snap && (
        <InjectHoldingsModal
          snapId={snapId}
          currentItems={items}
          onClose={() => setShowInjectHoldings(false)}
          onDone={async () => { setShowInjectHoldings(false); await loadItems(snapId); const ai = await apiGetAllBalanceItems(); setAllItems(ai); }}
        />
      )}
      {copyItem && (
        <CopyItemModal
          item={copyItem}
          snapshots={snapshots}
          accounts={accounts}
          onClose={() => setCopyItem(null)}
          onDone={() => { setCopyItem(null); loadItems(snapId); loadAll(); }}
        />
      )}
      {showCopySnap && snap && (
        <CopySnapModal snap={snap} onClose={() => setShowCopySnap(false)} onDone={handleSnapCreated}/>
      )}
      {showEditSnap && snap && (
        <EditSnapModal snap={snap} onClose={() => setShowEditSnap(false)} onDone={handleSnapUpdated}/>
      )}
      {showManageAccounts && (
        <BalanceAccountManagerModal
          accounts={accounts}
          onClose={() => setShowManageAccounts(false)}
          onDone={async (updated) => { setAccounts(updated); if (updated.length < accounts.length) loadItems(snapId); }}
        />
      )}
      {deleteTarget && (
        <ConfirmDeleteModal
          message={deleteTarget.type === "snapshot"
            ? I18N.t("balance.items.deleteSnap")
            : I18N.t("balance.items.deleteItem")}
          onClose={() => setDeleteTarget(null)}
          onConfirm={() =>
            deleteTarget.type === "snapshot"
              ? handleDeleteSnapshot(deleteTarget.id)
              : handleDeleteItem(deleteTarget.id)
          }
        />
      )}
    </div>
  );
};

// ── Snapshot selector bar ─────────────────────────────────────────────────────

const SnapBar = ({ snapshots, snapId, setSnapId, snap, isLatest, showSnapMenu, setShowSnapMenu, snapSeries, onInjectHoldings, onEditSnap, onDeleteSnap }) => {
  const menuRef = React.useRef(null);
  React.useEffect(() => {
    if (!showSnapMenu) return;
    const handler = (e) => { if (!menuRef.current?.contains(e.target)) setShowSnapMenu(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [showSnapMenu]);

  return (
  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, gap: 16, padding: "10px 14px", background: isLatest ? "var(--paper)" : "var(--warn-soft)", border: "1px solid " + (isLatest ? "var(--line)" : "var(--warn)"), borderRadius: 12 }}>
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <Icon name={isLatest ? "clock" : "archive"} size={16} style={{ color: isLatest ? "var(--ink-3)" : "#7A4D0E" }}/>
      {snap ? (
        <div>
          <div style={{ fontSize: 12, fontWeight: 600, color: isLatest ? "var(--ink-3)" : "#7A4D0E", letterSpacing: ".05em", textTransform: "uppercase" }}>
            {isLatest ? I18N.t("balance.snap.latest") : I18N.t("balance.snap.historical")}
          </div>
          <div style={{ fontSize: 13.5, marginTop: 2 }}>
            <span className="mono" style={{ fontWeight: 600 }}>{snap.snapshot_date}</span>
            <span style={{ margin: "0 8px", color: "var(--ink-4)" }}>·</span>
            <span>{snap.label}</span>
            {snap.note && <span style={{ marginLeft: 8, color: "var(--ink-3)", fontSize: 12 }}>— {snap.note}</span>}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>{I18N.t("balance.snap.empty")}</div>
      )}
    </div>
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      {snap && <Button variant="secondary" icon="wallet" onClick={onInjectHoldings}>{I18N.t("balance.snap.injectHoldings")}</Button>}
      {snap && <Button variant="ghost" icon="edit" onClick={onEditSnap} title={I18N.t("balance.snap.edit")}/>}
      {snap && <Button variant="ghost" icon="trash" onClick={() => onDeleteSnap(snapId)} title={I18N.t("balance.snap.delete")}/>}
      <div ref={menuRef} style={{ position: "relative" }}>
        <Button variant="secondary" iconRight="chevron-down" onClick={() => setShowSnapMenu(v => !v)}>
          {I18N.t("balance.snap.switch")} · {snapshots.length} {I18N.t("balance.snap.versions")}
        </Button>
        {showSnapMenu && (
          <div style={{ position: "absolute", top: "calc(100% + 6px)", right: 0, background: "var(--paper)", border: "1px solid var(--line)", borderRadius: 10, boxShadow: "var(--shadow-lg)", padding: 6, width: 360, zIndex: 50 }}>
            {[...snapshots].reverse().map(s => {
              const sel = s.id === snapId;
              const ss = snapSeries.find(x => x.id === s.id);
              return (
                <button key={s.id} onClick={() => setSnapId(s.id)} style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 12px", width: "100%", background: sel ? "var(--bg-deep)" : "transparent", border: "none", borderRadius: 8, cursor: "pointer", textAlign: "left" }}>
                  <span style={{ width: 6, height: 6, borderRadius: 3, background: sel ? "var(--ink)" : "var(--line-strong)", flexShrink: 0 }}/>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, display: "flex", gap: 6, alignItems: "center" }}>
                      <span className="mono" style={{ color: "var(--ink-3)", fontSize: 11.5, fontWeight: 500 }}>{s.snapshot_date}</span>
                      <span>{s.label}</span>
                      {sel && <Badge tone="info" size="sm">{I18N.t("balance.snap.current")}</Badge>}
                    </div>
                    <div className="mono" style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 2 }}>
                      {ss ? `net ¥${((ss.net)/1000000).toFixed(2)}M · ` : ""}{s.item_count} items
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  </div>
  );
};

// ── Category breakdown card ───────────────────────────────────────────────────

const CatBreakdownCard = ({ title, cats, total, currency }) => (
  <Card padding={20}>
    <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700, marginBottom: 12 }}>{title}</div>
    <div style={{ display: "flex", height: 8, borderRadius: 4, overflow: "hidden", marginBottom: 12, background: "var(--bg-deep)" }}>
      {cats.map(c => <div key={c.label} style={{ flex: c.value, background: c.color }} title={`${c.label} ¥${fmtNum(c.value,0)}`}/>)}
    </div>
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
      {cats.map(c => {
        const pct = total ? (c.value / total) * 100 : 0;
        return (
          <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 0" }}>
            <span style={{ width: 8, height: 8, borderRadius: 2, background: c.color, flexShrink: 0 }}/>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 12.5, fontWeight: 500 }}>{c.label}</div>
              <div className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                <Private>{symFor(currency)}{fmtNum(toDisplay(c.value,"CNY",currency),0)}</Private> · {pct.toFixed(0)}%
              </div>
            </div>
          </div>
        );
      })}
    </div>
  </Card>
);

// Deterministic palette: djb2-style hash(name) → fixed color slot.
// Same name always lands on the same color; no config to maintain.
const PALETTE = [
  "#1F8A4C", "#1F4FE0", "#C03A3A", "#C8821F", "#7A1F4F",
  "#2D9E6E", "#6B4FB8", "#B8447B", "#9A4D2E", "#4B3580",
  "#2196A6", "#C8A000", "#5A7A2E", "#3F4FA0", "#A03A8F", "#5577AA",
];
const entityColor = (name) => {
  let h = 0;
  const s = name || "";
  for (let i = 0; i < s.length; i++) h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  return PALETTE[(h >>> 0) % PALETTE.length];
};

// Blend hex towards white by t ∈ [0,1]
const blendWhite = (hex, t) => {
  const r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
  const m = c => Math.round(c + (255 - c) * t).toString(16).padStart(2,"0");
  return `#${m(r)}${m(g)}${m(b)}`;
};

const DonutChart = ({ segments, size = 52 }) => {
  const total = segments.reduce((s, g) => s + g.value, 0);
  if (!total) return (
    <svg width={size} height={size}>
      <circle cx={size/2} cy={size/2} r={size/2 - 2} fill="var(--bg-deep)"/>
    </svg>
  );
  const R = size / 2 - 1.5, r = R * 0.46, cx = size / 2, cy = size / 2;
  const nonZero = segments.filter(s => s.value > 0);
  if (nonZero.length === 1) return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      <circle cx={cx} cy={cy} r={R} fill={nonZero[0].color}/>
      <circle cx={cx} cy={cy} r={r} fill="var(--paper)"/>
    </svg>
  );
  let a = -Math.PI / 2;
  const arcs = segments.map(seg => {
    const sweep = (seg.value / total) * 2 * Math.PI;
    if (sweep < 0.002) { a += sweep; return null; }
    const a0 = a, a1 = a + sweep;
    a = a1;
    const large = sweep > Math.PI ? 1 : 0;
    const p = (ang, rad) => `${(cx + rad * Math.cos(ang)).toFixed(2)},${(cy + rad * Math.sin(ang)).toFixed(2)}`;
    return { color: seg.color, d: `M${p(a0,R)} A${R},${R} 0 ${large},1 ${p(a1,R)} L${p(a1,r)} A${r},${r} 0 ${large},0 ${p(a0,r)} Z` };
  }).filter(Boolean);
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {arcs.map((arc, i) => <path key={i} d={arc.d} fill={arc.color} stroke="var(--paper)" strokeWidth="1.5"/>)}
    </svg>
  );
};

const AccountBreakdownCard = ({ title, items, total, currency }) => {
  if (!items.length) return null;
  const cnyOf = i => i.amount * (FX[i.currency] || 1);

  const acctMap = {};
  items.forEach(i => {
    const acct = i.account_name || I18N.t("balance.acct.other");
    if (!acctMap[acct]) acctMap[acct] = { total: 0, subs: {} };
    const v = cnyOf(i);
    acctMap[acct].total += v;
    const sub = i.sub_account_name || null;
    if (sub) acctMap[acct].subs[sub] = (acctMap[acct].subs[sub] || 0) + v;
  });

  const rows = Object.entries(acctMap)
    .map(([name, data]) => {
      const color = entityColor(name);
      const subEntries = Object.entries(data.subs).sort((a, b) => b[1] - a[1]);
      const subColors = subEntries.map((_, i) =>
        blendWhite(color, subEntries.length > 1 ? i * 0.45 / (subEntries.length - 1) : 0)
      );
      return { name, total: data.total, color, subEntries, subColors };
    })
    .sort((a, b) => b.total - a.total);

  const [selectedName, setSelectedName] = React.useState(rows[0]?.name || "");
  React.useEffect(() => {
    if (rows.length && !rows.find(r => r.name === selectedName)) {
      setSelectedName(rows[0].name);
    }
  }, [rows]);
  const selected = rows.find(r => r.name === selectedName) || rows[0];
  const topSegments = rows.map(r => ({ value: r.total, color: r.color }));
  const subSegments = selected?.subEntries.map(([, v], i) => ({ value: v, color: selected.subColors[i] })) || [];

  return (
    <Card padding={20}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
        <div className="serif-cn" style={{ fontSize: 16, fontWeight: 700 }}>{title}</div>
        <Select
          value={selectedName}
          onChange={setSelectedName}
          options={rows.filter(r => r.total > 0).map(r => ({ value: r.name, label: r.name }))}
          style={{ width: 140 }}
        />
      </div>

      {/* Overview donut + account legend */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start", marginBottom: selected?.subEntries.length > 0 ? 14 : 0 }}>
        <DonutChart segments={topSegments} size={80}/>
        <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, paddingTop: 2 }}>
          {rows.filter(r => r.total > 0).map(r => {
            const pct = total ? (r.total / total) * 100 : 0;
            const isSel = r.name === selectedName;
            return (
              <div key={r.name} onClick={() => setSelectedName(r.name)}
                style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer", padding: "2px 4px", borderRadius: 5, background: isSel ? "var(--bg-deep)" : "transparent" }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: r.color, flexShrink: 0 }}/>
                <span style={{ fontSize: 12, fontWeight: isSel ? 700 : 500, flex: 1 }}>{r.name}</span>
                <span className="mono" style={{ fontSize: 11, color: "var(--ink-3)" }}>
                  <Private>{symFor(currency)}{fmtNum(toDisplay(r.total,"CNY",currency),0)}</Private>
                </span>
                <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)", width: 26, textAlign: "right" }}>
                  {pct.toFixed(0)}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Selected account sub breakdown */}
      {selected?.subEntries.length > 0 && (
        <>
          <div style={{ height: 1, background: "var(--line)", marginBottom: 12 }}/>
          <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
            <DonutChart segments={subSegments} size={64}/>
            <div style={{ flex: 1, display: "flex", flexDirection: "column", gap: 4, paddingTop: 1 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: selected.color, marginBottom: 4 }}>{selected.name}</div>
              {selected.subEntries.map(([subName, subAmt], i) => {
                const subPct = selected.total ? (subAmt / selected.total) * 100 : 0;
                return (
                  <div key={subName} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span style={{ width: 7, height: 7, borderRadius: 2, background: selected.subColors[i], flexShrink: 0 }}/>
                    <span style={{ fontSize: 11.5, color: "var(--ink-2)", flex: 1 }}>{subName}</span>
                    <span className="mono" style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                      <Private>{symFor(currency)}{fmtNum(toDisplay(subAmt,"CNY",currency),0)}</Private>
                    </span>
                    <span className="mono" style={{ fontSize: 10.5, color: "var(--ink-4)", width: 28, textAlign: "right" }}>
                      {subPct.toFixed(0)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        </>
      )}
    </Card>
  );
};

// ── Item row ──────────────────────────────────────────────────────────────────

const ItemRow = ({ item: it, currency, last, onClick, onEdit, onDelete, onCopy }) => {
  const dispAmt = toDisplay(it.amount, it.currency, currency);
  const cnyAmt  = toDisplay(it.amount, it.currency, "CNY");
  const iconBtn = (onClick, name) => (
    <button onClick={onClick} style={{ width: 22, height: 22, background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Icon name={name} size={12}/>
    </button>
  );
  return (
    <div onClick={onClick} style={{ display: "grid", gridTemplateColumns: "1.6fr 100px 80px 130px 130px 1fr 72px", gap: 10, padding: "11px 18px", alignItems: "center", borderBottom: last ? "none" : "1px solid var(--line)", fontSize: 12.5, cursor: "pointer" }}
      onMouseEnter={e => e.currentTarget.style.background = "var(--bg-deep)"}
      onMouseLeave={e => e.currentTarget.style.background = ""}
    >
      <div>
        <div style={{ fontWeight: 600 }}>{it.name}</div>
        {(it.account_name || it.sub_account_name) && (
          <div style={{ fontSize: 10.5, color: "var(--ink-4)", marginTop: 1 }}>
            {[it.account_name, it.sub_account_name].filter(Boolean).join(" · ")}
          </div>
        )}
      </div>
      <span>
        <span style={{ display: "inline-flex", alignItems: "center", padding: "2px 7px", background: (BALANCE_CAT_COLORS[it.category] || "#888") + "20", color: BALANCE_CAT_COLORS[it.category] || "#888", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
          {I18N.tCat(it.category)}
        </span>
      </span>
      <span><Badge tone={it.side === "asset" ? "down" : "up"} size="sm">{it.side === "asset" ? I18N.t("balance.badge.asset") : I18N.t("balance.badge.liability")}</Badge></span>
      <span className="mono" style={{ textAlign: "right", fontWeight: 600 }}>
        <Private>{fmtMoney(it.amount, it.currency, 2)}</Private>
      </span>
      <span className="mono" style={{ textAlign: "right", color: currency === "CNY" ? "var(--ink-3)" : "var(--ink)" }}>
        {currency !== it.currency ? <Private>{symFor(currency)}{fmtNum(dispAmt, 0)}</Private> : <span style={{ color: "var(--ink-4)" }}>—</span>}
      </span>
      <span style={{ color: "var(--ink-3)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.note || "—"}</span>
      <div style={{ display: "flex", gap: 2 }} onClick={e => e.stopPropagation()}>
        {iconBtn(onCopy, "copy")}
        {iconBtn(onEdit, "edit")}
        {iconBtn(onDelete, "trash")}
      </div>
    </div>
  );
};

// ── Net worth trend ───────────────────────────────────────────────────────────

const NetWorthTrend = ({ series, highlightId }) => {
  usePrivacyMasked(); // re-render so chart labels refresh on toggle
  const W = 380, padX = 12, padTop = 20, padBottom = 18, chartH = 70;
  const H = padTop + chartH + padBottom;
  const nets = series.map(s => s.net);
  const maxV = Math.max(...nets, 0);
  const minV = Math.min(...nets, 0);
  const range = maxV - minV || 1;
  const n = series.length;
  const x = (i) => padX + (n > 1 ? (i / (n - 1)) : 0.5) * (W - padX * 2);
  const y = (v) => padTop + (1 - (v - minV) / range) * chartH;
  const netPath = "M " + series.map((s, i) => `${x(i).toFixed(1)},${y(s.net).toFixed(1)}`).join(" L ");
  const fill = netPath + ` L ${x(n-1).toFixed(1)},${y(0).toFixed(1)} L ${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const hi = series.findIndex(s => s.id === highlightId);
  const fmtVal = (v) => {
    if (PRIVACY.masked) return "•••";
    const abs = Math.abs(v);
    if (abs >= 1e6) return (v / 1e6).toFixed(2) + "M";
    if (abs >= 1e3) return (v / 1e3).toFixed(0) + "K";
    return v.toFixed(0);
  };
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 4 }}>{I18N.t("balance.history.title")} · {I18N.tf("balance.history.count", { n })}</div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
        {minV < 0 && <line x1={padX} x2={W-padX} y1={y(0)} y2={y(0)} stroke="var(--line-2)" strokeDasharray="2 3"/>}
        <path d={fill} fill="var(--ink)" fillOpacity=".06"/>
        <path d={netPath} stroke="var(--ink)" strokeWidth="1.8" fill="none"/>
        {series.map((s, i) => {
          const cx = x(i), cy = y(s.net);
          const isHi = i === hi;
          const anchor = i === 0 ? "start" : i === n - 1 ? "end" : "middle";
          return (
            <g key={s.id}>
              <circle cx={cx} cy={cy} r={isHi ? 4 : 2.5}
                fill={isHi ? "var(--up)" : "var(--ink)"} stroke="#fff" strokeWidth="1"/>
              <text x={cx} y={cy - 6} textAnchor={anchor} fontSize="9" fontFamily="monospace"
                fill={isHi ? "var(--up)" : "var(--ink-3)"} fontWeight={isHi ? "700" : "400"}>
                ¥{fmtVal(s.net)}
              </text>
              <text x={cx} y={H - 2} textAnchor={anchor} fontSize="9" fontFamily="monospace"
                fill="var(--ink-4)">
                {s.date}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
};

// ── History modal ─────────────────────────────────────────────────────────────

const HistoryModal = ({ item, allItems, snapshots, currency, onClose }) => {
  const history = allItems
    .filter(i => {
      if (i.side !== item.side) return false;
      // prefer account_id match; fall back to name match when account_id is unset
      if (item.account_id) {
        return i.account_id === item.account_id &&
               i.sub_account_id === item.sub_account_id &&
               i.category === item.category &&
               i.name === item.name;
      }
      return i.name === item.name;
    })
    .map(i => ({ ...i, snap: snapshots.find(s => s.id === i.snapshot_id) }))
    .filter(i => i.snap)
    .sort((a, b) => a.snap.snapshot_date.localeCompare(b.snap.snapshot_date));

  return (
    <Modal open title={`${I18N.t("balance.history.title")} · ${item.name}`} onClose={onClose} width={580}>
      <div style={{ padding: "16px 20px 20px" }}>
      <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 12 }}>
        {item.side === "asset" ? I18N.t("balance.badge.asset") : I18N.t("balance.badge.liability")} · {I18N.tCat(item.category)}
      </div>
      {history.length === 0 ? (
        <div style={{ color: "var(--ink-4)", fontSize: 13 }}>{I18N.t("balance.history.onlyThis")}</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".08em" }}>
              <th style={{ textAlign: "left", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>{I18N.t("balance.history.snapDate")}</th>
              <th style={{ textAlign: "left", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>{I18N.t("balance.history.snapLabel")}</th>
              <th style={{ textAlign: "right", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>{I18N.t("balance.history.amount")}</th>
              <th style={{ textAlign: "right", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>≈ {currency}</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h, i) => (
              <tr key={h.id} style={{ background: h.snapshot_id === item.snapshot_id ? "var(--bg-deep)" : "" }}>
                <td style={{ padding: "8px 0", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  <span className="mono">{h.snap.snapshot_date}</span>
                  {h.snapshot_id === item.snapshot_id && <Badge tone="info" size="sm" style={{ marginLeft: 8 }}>{I18N.t("balance.history.current")}</Badge>}
                </td>
                <td style={{ padding: "8px 8px", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>{h.snap.label}</td>
                <td className="mono" style={{ textAlign: "right", padding: "8px 0", fontWeight: 600, borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  <Private>{fmtMoney(h.amount, h.currency, 0)}</Private>
                </td>
                <td className="mono" style={{ textAlign: "right", padding: "8px 0", color: "var(--ink-3)", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  <Private>{symFor(currency)}{fmtNum(toDisplay(h.amount, h.currency, currency), 0)}</Private>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      </div>
    </Modal>
  );
};

// ── Shared form helpers ───────────────────────────────────────────────────────

const BalField = ({ label, children, span2 = false }) => (
  <div style={{ gridColumn: span2 ? "1/-1" : undefined }}>
    <div style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ink-3)", marginBottom: 5 }}>{label}</div>
    {children}
  </div>
);

const BalSelect = ({ value, onChange, options, disabled = false }) => (
  <Select
    value={value}
    onChange={onChange}
    options={options}
    style={{ width: "100%", opacity: disabled ? 0.5 : 1, pointerEvents: disabled ? "none" : "auto" }}
  />
);

// ── Item modal (create / edit) ────────────────────────────────────────────────

const LOAN_CATS = ["贷款", "其他贷款"];
const OPTION_CATS = ["期权"];

const ItemModal = ({ item, snapId, accounts, onClose, onDone }) => {
  const isEdit = !!item.id;
  const [form, setForm] = React.useState({
    snapshot_id: item.snapshot_id || snapId,
    name: item.name || "",
    category: item.category || "现金",
    side: item.side || "asset",
    amount: item.amount != null ? String(item.amount) : "",
    currency: item.currency || "CNY",
    account_id: item.account_id ? String(item.account_id) : "",
    sub_account_id: item.sub_account_id ? String(item.sub_account_id) : "",
    note: item.note || "",
    interest_rate: item.interest_rate != null ? String(item.interest_rate) : "",
    monthly_payment: item.monthly_payment != null ? String(item.monthly_payment) : "",
    start_date: item.start_date || "",
    end_date: item.end_date || "",
    price: item.price != null ? String(item.price) : "",
    quantity: item.quantity != null ? String(item.quantity) : "",
  });
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState(null);

  const set = (k, v) => setForm(f => {
    const next = { ...f, [k]: v };
    if ((k === "price" || k === "quantity") && OPTION_CATS.includes(next.category)) {
      const p = parseFloat(next.price), q = parseFloat(next.quantity);
      if (!isNaN(p) && !isNaN(q)) next.amount = String(p * q);
    }
    return next;
  });

  const parentAccounts = accounts.filter(a => !a.parent_id);
  const subAccounts    = form.account_id
    ? accounts.filter(a => a.parent_id === Number(form.account_id))
    : [];

  const isLoan   = LOAN_CATS.includes(form.category);
  const isOption = OPTION_CATS.includes(form.category);

  const buildPayload = () => {
    const p = {
      snapshot_id: form.snapshot_id,
      name: form.name.trim(),
      category: form.category,
      side: form.side,
      amount: parseFloat(form.amount) || 0,
      currency: form.currency,
      account_id: form.account_id ? Number(form.account_id) : null,
      sub_account_id: form.sub_account_id ? Number(form.sub_account_id) : null,
      note: form.note.trim() || null,
    };
    if (isLoan) {
      p.interest_rate    = form.interest_rate    ? parseFloat(form.interest_rate)    : null;
      p.monthly_payment  = form.monthly_payment  ? parseFloat(form.monthly_payment)  : null;
      p.start_date       = form.start_date       || null;
      p.end_date         = form.end_date         || null;
    }
    if (isOption) {
      p.price    = form.price    ? parseFloat(form.price)    : null;
      p.quantity = form.quantity ? parseFloat(form.quantity) : null;
    }
    return p;
  };

  const handleSave = async () => {
    if (!form.name.trim()) { setError(I18N.t("balance.item.nameEmpty")); return; }
    if (!form.amount || isNaN(parseFloat(form.amount))) { setError(I18N.t("balance.item.amountInvalid")); return; }
    setLoading(true); setError(null);
    try {
      if (isEdit) await apiUpdateBalanceItem(item.id, buildPayload());
      else        await apiCreateBalanceItem(buildPayload());
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title={isEdit ? I18N.t("balance.item.edit.title") : I18N.t("balance.item.new.title")} onClose={onClose} width={480}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label={I18N.t("balance.item.side")} span2>
            <div style={{ display: "flex", gap: 8 }}>
              {[{ value: "asset", label: I18N.t("balance.badge.asset") }, { value: "liability", label: I18N.t("balance.badge.liability") }].map(opt => (
                <button key={opt.value} onClick={() => set("side", opt.value)} style={{
                  flex: 1, padding: "7px 0", border: "1px solid " + (form.side === opt.value ? "var(--ink)" : "var(--line)"),
                  borderRadius: 7, background: form.side === opt.value ? "var(--ink)" : "transparent",
                  color: form.side === opt.value ? "var(--paper)" : "var(--ink-2)",
                  fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}>{opt.label}</button>
              ))}
            </div>
          </BalField>
          <BalField label={I18N.t("balance.item.name")} span2>
            <Input value={form.name} onChange={v => set("name", v)} placeholder={I18N.t("balance.item.name.ph")} style={{ width: "100%" }}/>
          </BalField>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <BalField label={I18N.t("balance.item.category")} span2>
              <BalSelect value={form.category} onChange={v => set("category", v)}
                options={BALANCE_CATEGORIES.map(c => ({ value: c, label: I18N.tCat(c) }))}/>
            </BalField>
            {parentAccounts.length > 0 && (
              <>
                <BalField label={I18N.t("balance.item.account")}>
                  <BalSelect value={form.account_id} onChange={v => { set("account_id", v); set("sub_account_id", ""); }}
                    options={[{ value: "", label: I18N.t("balance.item.noSelect") }, ...parentAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
                <BalField label={I18N.t("balance.item.subAccount")}>
                  <BalSelect value={form.sub_account_id} onChange={v => set("sub_account_id", v)}
                    disabled={!form.account_id || subAccounts.length === 0}
                    options={[{ value: "", label: I18N.t("balance.item.noSelect") }, ...subAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
              </>
            )}
            <BalField label={I18N.t("balance.item.amount")} span2>
              <div style={{ display: "flex", gap: 0 }}>
                <Input type="number" value={form.amount} onChange={v => set("amount", v)} placeholder="0"
                  style={{ flex: 1, borderRadius: "7px 0 0 7px", borderRight: "none" }}/>
                <Select value={form.currency} onChange={v => set("currency", v)}
                  options={CURRENCIES.map(c => ({ value: c, label: c }))}
                  style={{ width: 90, borderRadius: "0 7px 7px 0" }}/>
              </div>
            </BalField>
            <BalField label={I18N.t("balance.item.note")} span2>
              <Input value={form.note} onChange={v => set("note", v)} placeholder={I18N.t("balance.item.note.ph")} style={{ width: "100%" }}/>
            </BalField>
            {isLoan && (
              <>
                <BalField label={I18N.t("balance.item.rate")}>
                  <Input type="number" value={form.interest_rate} onChange={v => set("interest_rate", v)} placeholder="0.0365" style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.payment")}>
                  <Input type="number" value={form.monthly_payment} onChange={v => set("monthly_payment", v)} placeholder="10400" style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.startDate")}>
                  <Input type="date" value={form.start_date} onChange={v => set("start_date", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.endDate")}>
                  <Input type="date" value={form.end_date} onChange={v => set("end_date", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
            {isOption && (
              <>
                <BalField label={I18N.t("balance.item.unitPrice")}>
                  <Input type="number" value={form.price} onChange={v => set("price", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.quantity")}>
                  <Input type="number" value={form.quantity} onChange={v => set("quantity", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
          </div>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? I18N.t("balance.item.saving") : I18N.t("base.btn.save")}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── New snapshot modal ────────────────────────────────────────────────────────

// ── Inject holdings modal ─────────────────────────────────────────────────────

const InjectHoldingsModal = ({ snapId, currentItems, onClose, onDone }) => {
  const [holdAccounts, setHoldAccounts] = React.useState([]);
  const [totals, setTotals]             = React.useState({});
  const [checked, setChecked]           = React.useState({});
  const [loading, setLoading]           = React.useState(true);
  const [saving, setSaving]             = React.useState(false);
  const [error, setError]               = React.useState(null);

  const existingKeys = new Set(
    currentItems.map(i => `${i.snapshot_id}|asset|${i.account_id ?? -1}|${i.sub_account_id ?? -1}|投资`)
  );

  const isDupe = (acct) => {
    if (!acct.balance_account_id) return false;
    const key = `${snapId}|asset|${acct.balance_account_id}|${acct.balance_sub_account_id ?? -1}|投资`;
    return existingKeys.has(key);
  };

  React.useEffect(() => {
    const load = async () => {
      try {
        const [hlds, accts] = await Promise.all([apiGetHoldings(), apiGetAccounts()]);
        const codes = [...new Set(hlds.map(h => h.code).filter(c => c && c !== "CASH"))];
        const prices = codes.length > 0 ? await apiGetPrices(codes) : {};
        const result = {};
        accts.forEach(acct => {
          const acctFx = FX[acct.currency] || 1;
          let total = 0;
          hlds.filter(h => h.account === acct.name).forEach(h => {
            const price = h.code === "CASH" ? (h.avg_cost || 1) : (prices[h.code]?.price || 0);
            total += (h.shares || 0) * price * (FX[h.currency] || 1) / acctFx;
          });
          result[acct.name] = { amount: total, currency: acct.currency };
        });
        setHoldAccounts(accts);
        setTotals(result);
        const initChecked = {};
        accts.forEach(a => {
          initChecked[a.name] = !!a.balance_account_id && !isDupe(a);
        });
        setChecked(initChecked);
      } catch (e) {
        setError(e.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleSave = async () => {
    setSaving(true); setError(null);
    try {
      const payloads = holdAccounts
        .filter(acct => checked[acct.name] && acct.balance_account_id && !isDupe(acct))
        .map(acct => {
          const { amount, currency } = totals[acct.name] || { amount: 0, currency: acct.currency };
          return {
            snapshot_id: snapId,
            name: acct.name,
            category: "投资",
            side: "asset",
            amount: Math.round(amount),
            currency,
            account_id: acct.balance_account_id,
            sub_account_id: acct.balance_sub_account_id || null,
          };
        });
      if (payloads.length > 0) {
        const result = await apiCreateBalanceItemsBulk(payloads);
        if (result.errors && result.errors.length > 0) throw new Error(result.errors[0].reason);
      }
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setSaving(false); }
  };

  return (
    <Modal open title={I18N.t("balance.inject.title")} onClose={onClose} width={480}>
      <div style={{ display: "flex", flexDirection: "column", maxHeight: "65vh" }}>
        <div style={{ padding: "10px 20px 8px", flexShrink: 0, fontSize: 12, color: "var(--ink-3)" }}>
          {I18N.t("balance.inject.hint")}
        </div>
        {loading ? (
          <div style={{ padding: "20px", textAlign: "center", color: "var(--ink-3)" }}>{I18N.t("balance.inject.loading")}</div>
        ) : (
          <>
            <div style={{ overflowY: "auto", flex: 1, padding: "4px 20px 8px", display: "flex", flexDirection: "column", gap: 6 }}>
              {holdAccounts.map(acct => {
                const { amount, currency } = totals[acct.name] || {};
                const sym = CURRENCY_SYMBOL[currency] || "";
                const dupe = isDupe(acct);
                const noMap = !acct.balance_account_id;
                const isChecked = !!checked[acct.name];
                return (
                  <label key={acct.name} style={{
                    display: "flex", alignItems: "center", gap: 10, padding: "10px 12px",
                    border: "1px solid " + (isChecked ? "var(--line-strong)" : "var(--line)"),
                    borderRadius: 9,
                    background: (dupe || noMap) ? "var(--bg-deep)" : "var(--paper)",
                    cursor: (dupe || noMap) ? "default" : "pointer",
                    opacity: noMap ? 0.5 : 1,
                  }}>
                    <input type="checkbox" checked={isChecked && !dupe} disabled={dupe || noMap}
                      onChange={e => setChecked(s => ({ ...s, [acct.name]: e.target.checked }))}/>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{acct.name}</div>
                      <div style={{ fontSize: 11, color: "var(--ink-4)", marginTop: 1 }}>
                        {dupe ? I18N.t("balance.inject.exists") : noMap ? I18N.t("balance.inject.noMap") : I18N.t("balance.inject.investing")}
                      </div>
                    </div>
                    <div className="mono" style={{ fontSize: 13, fontWeight: 600, opacity: dupe ? 0.5 : 1 }}>
                      {amount != null ? `${sym}${fmtNum(amount, 0)}` : "—"}
                      <span style={{ fontSize: 10, color: "var(--ink-4)", marginLeft: 4 }}>{currency}</span>
                    </div>
                  </label>
                );
              })}
            </div>
            <div style={{ padding: "10px 20px 20px", flexShrink: 0, borderTop: "1px solid var(--line)" }}>
              {error && <div style={{ color: "var(--up)", fontSize: 12, marginBottom: 10 }}>{error}</div>}
              <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
                <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
                <Button variant="primary" onClick={handleSave} disabled={saving}>{saving ? I18N.t("balance.inject.inserting") : I18N.t("balance.inject.insert")}</Button>
              </div>
            </div>
          </>
        )}
      </div>
    </Modal>
  );
};

// ── Copy item modal ───────────────────────────────────────────────────────────

const CopyItemModal = ({ item, snapshots, accounts, onClose, onDone }) => {
  const [form, setForm] = React.useState({
    snapshot_id: String(snapshots[snapshots.length - 1]?.id || item.snapshot_id),
    name:           item.name || "",
    category:       item.category || "现金",
    side:           item.side || "asset",
    amount:         item.amount != null ? String(item.amount) : "",
    currency:       item.currency || "CNY",
    account_id:     item.account_id ? String(item.account_id) : "",
    sub_account_id: item.sub_account_id ? String(item.sub_account_id) : "",
    note:           item.note || "",
    interest_rate:    item.interest_rate  != null ? String(item.interest_rate)  : "",
    monthly_payment:  item.monthly_payment != null ? String(item.monthly_payment) : "",
    start_date:     item.start_date || "",
    end_date:       item.end_date || "",
    price:          item.price    != null ? String(item.price)    : "",
    quantity:       item.quantity != null ? String(item.quantity) : "",
  });
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState(null);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const parentAccounts = accounts.filter(a => !a.parent_id);
  const subAccounts    = form.account_id
    ? accounts.filter(a => a.parent_id === Number(form.account_id))
    : [];
  const isLoan   = LOAN_CATS.includes(form.category);
  const isOption = OPTION_CATS.includes(form.category);

  const handleSave = async () => {
    if (!form.name.trim()) { setError(I18N.t("balance.item.nameEmpty")); return; }
    if (!form.amount || isNaN(parseFloat(form.amount))) { setError(I18N.t("balance.item.amountInvalid")); return; }
    setLoading(true); setError(null);
    try {
      const p = {
        snapshot_id:    Number(form.snapshot_id),
        name:           form.name.trim(),
        category:       form.category,
        side:           form.side,
        amount:         parseFloat(form.amount) || 0,
        currency:       form.currency,
        account_id:     form.account_id ? Number(form.account_id) : null,
        sub_account_id: form.sub_account_id ? Number(form.sub_account_id) : null,
        note:           form.note.trim() || null,
      };
      if (isLoan) {
        p.interest_rate   = form.interest_rate   ? parseFloat(form.interest_rate)   : null;
        p.monthly_payment = form.monthly_payment ? parseFloat(form.monthly_payment) : null;
        p.start_date      = form.start_date  || null;
        p.end_date        = form.end_date    || null;
      }
      if (isOption) {
        p.price    = form.price    ? parseFloat(form.price)    : null;
        p.quantity = form.quantity ? parseFloat(form.quantity) : null;
      }
      await apiCreateBalanceItem(p);
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title={I18N.t("balance.item.copy.title")} onClose={onClose} width={480}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label={I18N.t("balance.item.copy.targetSnap")} span2>
            <BalSelect value={form.snapshot_id} onChange={v => set("snapshot_id", v)}
              options={snapshots.map(s => ({ value: String(s.id), label: `${s.snapshot_date}  ${s.label}` }))}/>
          </BalField>
          <BalField label={I18N.t("balance.item.side")} span2>
            <div style={{ display: "flex", gap: 8 }}>
              {[{ value: "asset", label: I18N.t("balance.badge.asset") }, { value: "liability", label: I18N.t("balance.badge.liability") }].map(opt => (
                <button key={opt.value} onClick={() => set("side", opt.value)} style={{
                  flex: 1, padding: "7px 0", border: "1px solid " + (form.side === opt.value ? "var(--ink)" : "var(--line)"),
                  borderRadius: 7, background: form.side === opt.value ? "var(--ink)" : "transparent",
                  color: form.side === opt.value ? "var(--paper)" : "var(--ink-2)",
                  fontSize: 13, fontWeight: 600, cursor: "pointer",
                }}>{opt.label}</button>
              ))}
            </div>
          </BalField>
          <BalField label={I18N.t("balance.item.name")} span2>
            <Input value={form.name} onChange={v => set("name", v)} placeholder={I18N.t("balance.item.name.ph")} style={{ width: "100%" }}/>
          </BalField>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <BalField label={I18N.t("balance.item.category")} span2>
              <BalSelect value={form.category} onChange={v => set("category", v)}
                options={BALANCE_CATEGORIES.map(c => ({ value: c, label: I18N.tCat(c) }))}/>
            </BalField>
            {parentAccounts.length > 0 && (
              <>
                <BalField label={I18N.t("balance.item.account")}>
                  <BalSelect value={form.account_id} onChange={v => { set("account_id", v); set("sub_account_id", ""); }}
                    options={[{ value: "", label: I18N.t("balance.item.noSelect") }, ...parentAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
                <BalField label={I18N.t("balance.item.subAccount")}>
                  <BalSelect value={form.sub_account_id} onChange={v => set("sub_account_id", v)}
                    disabled={!form.account_id || subAccounts.length === 0}
                    options={[{ value: "", label: I18N.t("balance.item.noSelect") }, ...subAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
              </>
            )}
            <BalField label={I18N.t("balance.item.amount")} span2>
              <div style={{ display: "flex", gap: 0 }}>
                <Input type="number" value={form.amount} onChange={v => set("amount", v)} placeholder="0"
                  style={{ flex: 1, borderRadius: "7px 0 0 7px", borderRight: "none" }}/>
                <Select value={form.currency} onChange={v => set("currency", v)}
                  options={CURRENCIES.map(c => ({ value: c, label: c }))}
                  style={{ width: 90, borderRadius: "0 7px 7px 0" }}/>
              </div>
            </BalField>
            <BalField label={I18N.t("balance.item.note")} span2>
              <Input value={form.note} onChange={v => set("note", v)} placeholder={I18N.t("balance.item.note.ph")} style={{ width: "100%" }}/>
            </BalField>
            {isLoan && (
              <>
                <BalField label={I18N.t("balance.item.rate")}>
                  <Input type="number" value={form.interest_rate} onChange={v => set("interest_rate", v)} placeholder="0.0365" style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.payment")}>
                  <Input type="number" value={form.monthly_payment} onChange={v => set("monthly_payment", v)} placeholder="10400" style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.startDate")}>
                  <Input type="date" value={form.start_date} onChange={v => set("start_date", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.endDate")}>
                  <Input type="date" value={form.end_date} onChange={v => set("end_date", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
            {isOption && (
              <>
                <BalField label={I18N.t("balance.item.unitPrice")}>
                  <Input type="number" value={form.price} onChange={v => set("price", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label={I18N.t("balance.item.quantity")}>
                  <Input type="number" value={form.quantity} onChange={v => set("quantity", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
          </div>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? I18N.t("balance.item.copying") : I18N.t("base.btn.copy")}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Copy snapshot modal ───────────────────────────────────────────────────────

const CopySnapModal = ({ snap, onClose, onDone }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate]   = React.useState(today);
  const [label, setLabel] = React.useState(snap.label + I18N.t("balance.copySnap.labelDefault"));
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState(null);

  const handleSave = async () => {
    setLoading(true); setError(null);
    try {
      const newSnap = await apiCopyBalanceSnapshot(snap.id, { new_label: label.trim(), new_date: date });
      onDone(newSnap.id, { fromCopy: true });
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title={`${I18N.t("balance.copySnap.title")} · ${snap.label}`} onClose={onClose} width={400}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 14 }}>
          {I18N.tf("balance.copySnap.itemCount", { n: snap.item_count })}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label={I18N.t("balance.copySnap.date")}><Input type="date" value={date} onChange={setDate} style={{ width: "100%" }}/></BalField>
          <BalField label={I18N.t("balance.copySnap.label")}><Input value={label} onChange={setLabel} style={{ width: "100%" }}/></BalField>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? I18N.t("balance.copySnap.copying") : I18N.t("balance.copySnap.copy")}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Edit snapshot modal ───────────────────────────────────────────────────────

const EditSnapModal = ({ snap, onClose, onDone }) => {
  const [date, setDate]   = React.useState(snap.snapshot_date);
  const [label, setLabel] = React.useState(snap.label);
  const [note, setNote]   = React.useState(snap.note || "");
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState(null);

  const handleSave = async () => {
    if (!label.trim()) { setError(I18N.t("balance.item.nameEmpty")); return; }
    setLoading(true); setError(null);
    try {
      await apiUpdateBalanceSnapshot(snap.id, {
        snapshot_date: date,
        label: label.trim(),
        note: note.trim() || null,
      });
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title={I18N.t("balance.snap.edit")} onClose={onClose} width={400}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label={I18N.t("balance.copySnap.date")}><Input type="date" value={date} onChange={setDate} style={{ width: "100%" }}/></BalField>
          <BalField label={I18N.t("balance.copySnap.label")}><Input value={label} onChange={setLabel} style={{ width: "100%" }}/></BalField>
          <BalField label={`${I18N.t("balance.item.note")} (${I18N.t("base.label.optional")})`}><Input value={note} onChange={setNote} placeholder={I18N.t("balance.item.note.ph")} style={{ width: "100%" }}/></BalField>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? I18N.t("balance.item.saving") : I18N.t("base.btn.save")}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Import modal ──────────────────────────────────────────────────────────────

// ── Confirm delete modal ──────────────────────────────────────────────────────

const ConfirmDeleteModal = ({ message, onClose, onConfirm }) => (
  <Modal open title={I18N.t("ledger.confirm.delete")} onClose={onClose} width={380}>
    <div style={{ padding: "16px 20px 20px" }}>
      <div style={{ fontSize: 13.5, color: "var(--ink)", marginBottom: 20 }}>{message}</div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button variant="secondary" onClick={onClose}>{I18N.t("base.btn.cancel")}</Button>
        <Button variant="danger" onClick={onConfirm}>{I18N.t("base.btn.delete")}</Button>
      </div>
    </div>
  </Modal>
);

// ── Balance account manager modal ────────────────────────────────────────────

const NameForm = ({ label, value, onChange, onConfirm, onCancel, saving }) => (
  <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "8px 0 10px" }}>
    <div style={{ fontSize: 11, color: "var(--ink-4)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em" }}>{label}</div>
    <div style={{ display: "flex", gap: 6 }}>
      <Input value={value} onChange={onChange} style={{ flex: 1 }} />
      <Button variant="primary" icon="check" onClick={onConfirm} disabled={saving} />
      <Button variant="secondary" icon="x" onClick={onCancel} />
    </div>
  </div>
);

const BalanceAccountManagerModal = ({ accounts: initialAccounts, onClose, onDone }) => {
  const [accts, setAccts] = React.useState(initialAccounts);
  const [selectedParentId, setSelectedParentId] = React.useState(
    () => initialAccounts.find(a => !a.parent_id)?.id ?? null
  );
  const [form, setForm] = React.useState(null); // { mode, id?, parentId?, value }
  const [confirmDelete, setConfirmDelete] = React.useState(null);
  const [err, setErr] = React.useState(null);
  const [saving, setSaving] = React.useState(false);

  const parents = accts.filter(a => !a.parent_id);
  const selectedParent = parents.find(p => p.id === selectedParentId) || null;
  const children = accts.filter(a => a.parent_id === selectedParentId);

  const reload = async (keepParent) => {
    const updated = await apiGetBalanceAccounts();
    setAccts(updated);
    onDone(updated);
    setSelectedParentId(keepParent);
  };

  const submitForm = async () => {
    const name = (form.value || "").trim();
    if (!name) { setErr(I18N.t("balance.item.nameEmpty")); return; }
    setSaving(true); setErr(null);
    try {
      if (form.mode === "add_parent") {
        const created = await apiCreateBalanceAccount({ name });
        setForm(null);
        await reload(created.id);
      } else if (form.mode === "add_child") {
        await apiCreateBalanceAccount({ name, parent_id: form.parentId });
        setForm(null);
        await reload(form.parentId);
      } else {
        const parentToKeep = selectedParentId;
        await apiUpdateBalanceAccount(form.id, { name });
        setForm(null);
        await reload(parentToKeep);
      }
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  const doDelete = async () => {
    if (!confirmDelete || saving) return;
    // Capture stale-closure values synchronously before any await
    const targetId = confirmDelete.id;
    const targetIsParent = !accts.find(a => a.id === targetId)?.parent_id;
    const nextParent = targetIsParent
      ? accts.filter(a => !a.parent_id && a.id !== targetId)[0]?.id ?? null
      : selectedParentId;
    setSaving(true); setErr(null);
    try {
      await apiDeleteBalanceAccount(targetId);
      await reload(nextParent);
      setConfirmDelete(null);
    } catch (ex) { setErr(ex.message); }
    finally { setSaving(false); }
  };

  const cancelForm = () => { setForm(null); setErr(null); };

  const nameFormProps = form ? {
    value: form.value,
    onChange: v => setForm(f => ({ ...f, value: v })),
    onConfirm: submitForm,
    onCancel: cancelForm,
    saving,
  } : null;

  const iBtn = { background: "none", border: "none", cursor: "pointer", color: "var(--ink-4)", padding: "3px 5px", borderRadius: 4, lineHeight: 1 };

  return (
    <Modal open title={I18N.t("balance.btn.accounts")} onClose={onClose} width={460}>
      <div style={{ padding: "16px 20px 20px" }}>
        {err && <div style={{ color: "var(--up)", fontSize: 12, marginBottom: 10 }}>{err}</div>}

        {/* Parent selector row */}
        <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 18 }}>
          <Select
            value={selectedParentId ? String(selectedParentId) : ""}
            onChange={v => { setSelectedParentId(v ? Number(v) : null); setForm(null); setErr(null); }}
            options={parents.map(p => ({ value: String(p.id), label: p.name }))}
            style={{ flex: 1 }}
          />
          {form?.mode === "add_parent" ? null : (
            <Button variant="secondary" icon="plus" onClick={() => setForm({ mode: "add_parent", value: "" })}>
              {I18N.t("base.btn.add")}
            </Button>
          )}
        </div>

        {/* Add parent form */}
        {form?.mode === "add_parent" && <NameForm label={I18N.t("balance.btn.accounts")} {...nameFormProps} />}

        {selectedParent && form?.mode !== "add_parent" && (
          <>
            {/* Parent name row */}
            <div style={{ fontSize: 10.5, color: "var(--ink-4)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6 }}>{I18N.t("balance.item.account")}</div>
            <div style={{ display: "flex", alignItems: "center", padding: "8px 12px", background: "var(--surface)", borderRadius: 8, marginBottom: 14, border: "1px solid var(--line)" }}>
              {form?.mode === "edit" && form.id === selectedParent.id ? (
                <NameForm label={I18N.t("balance.item.name")} {...nameFormProps} />
              ) : (
                <>
                  <span style={{ fontWeight: 600, fontSize: 14, flex: 1 }}>{selectedParent.name}</span>
                  {!form && <>
                    <button style={iBtn} title={I18N.t("base.btn.edit")} onClick={() => setForm({ mode: "edit", id: selectedParent.id, value: selectedParent.name })}>
                      <Icon name="edit" size={14} />
                    </button>
                    {children.length === 0
                      ? <button style={{ ...iBtn, color: "var(--up)" }} title={I18N.t("base.btn.delete")} onClick={() => setConfirmDelete({ id: selectedParent.id, name: selectedParent.name })}>
                          <Icon name="trash" size={14} />
                        </button>
                      : <span style={{ fontSize: 11, color: "var(--ink-4)", paddingLeft: 6 }}>{I18N.t("balance.item.subAccount")} first</span>
                    }
                  </>}
                </>
              )}
            </div>

            {/* Children */}
            <div style={{ fontSize: 10.5, color: "var(--ink-4)", fontWeight: 600, textTransform: "uppercase", letterSpacing: ".08em", marginBottom: 6 }}>{I18N.t("balance.item.subAccount")}</div>
            <div style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden", marginBottom: 10 }}>
              {children.map((child, i) => {
                const isEditingChild = form?.mode === "edit" && form.id === child.id;
                return (
                  <div key={child.id} style={{ padding: "8px 12px", borderBottom: i < children.length - 1 ? "1px solid var(--line)" : "none" }}>
                    {isEditingChild ? <NameForm label={I18N.t("balance.item.name")} {...nameFormProps} /> : (
                      <div style={{ display: "flex", alignItems: "center" }}>
                        <span style={{ fontSize: 13, flex: 1 }}>{child.name}</span>
                        {!form && <>
                          <button style={iBtn} title={I18N.t("base.btn.edit")} onClick={() => setForm({ mode: "edit", id: child.id, value: child.name })}>
                            <Icon name="edit" size={13} />
                          </button>
                          <button style={{ ...iBtn, color: "var(--up)" }} title={I18N.t("base.btn.delete")} onClick={() => setConfirmDelete({ id: child.id, name: child.name })}>
                            <Icon name="trash" size={13} />
                          </button>
                        </>}
                      </div>
                    )}
                  </div>
                );
              })}
              {/* Add child row */}
              {form?.mode === "add_child" && form.parentId === selectedParentId ? (
                <div style={{ padding: "8px 12px", borderTop: children.length ? "1px solid var(--line)" : "none" }}>
                  <NameForm label={I18N.t("balance.item.subAccount")} {...nameFormProps} />
                </div>
              ) : !form && (
                <div style={{ padding: "8px 12px", borderTop: children.length ? "1px solid var(--line)" : "none" }}>
                  <button style={{ ...iBtn, color: "var(--ink-3)", fontSize: 12, display: "flex", alignItems: "center", gap: 4 }}
                    onClick={() => setForm({ mode: "add_child", parentId: selectedParentId, value: "" })}>
                    <Icon name="plus" size={12} /> {I18N.t("balance.item.subAccount")}
                  </button>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {confirmDelete && (
        <ConfirmDeleteModal
          message={I18N.t("base.confirm.delete")}
          onClose={() => setConfirmDelete(null)}
          onConfirm={doDelete}
        />
      )}
    </Modal>
  );
};

window.BalanceSheet = BalanceSheet;
