/* Module 04 — Balance Sheet
   API-wired: snapshots, items, accounts all loaded from backend.
   FX conversion uses global FX object + currency prop from TopBar.
*/

const BALANCE_CATEGORIES = ["现金","理财","投资","期权","固定资产","房产","社保","外债","信用卡","贷款","其他贷款"];
const BALANCE_CAT_COLORS = {
  "现金":     "#1F8A4C",
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

  const [showSnapMenu, setShowSnapMenu]     = React.useState(false);
  const [editItem, setEditItem]             = React.useState(null);    // null = closed, {} = new, {id,...} = edit
  const [historyItem, setHistoryItem]       = React.useState(null);    // item for cross-snapshot history
  const [showNewSnap, setShowNewSnap]       = React.useState(false);
  const [showCopySnap, setShowCopySnap]     = React.useState(false);
  const [showEditSnap, setShowEditSnap]     = React.useState(false);
  const [showImport, setShowImport]         = React.useState(false);
  const [deleteTarget, setDeleteTarget]     = React.useState(null);    // {type:"item"|"snapshot", id}

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
  const assetCats = aggCat("asset");
  const liabCats  = aggCat("liability");

  const filtered = sideFilter === "all" ? items : items.filter(i => i.side === sideFilter);
  const sortedFiltered = [...filtered].sort((a, b) => toCNY(b) - toCNY(a));

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

  const doInvestmentAutofill = async (newSnapId) => {
    try {
      const [hlds, txns] = await Promise.all([apiGetHoldings(), apiGetTransactions()]);
      if (!hlds || hlds.length === 0) return;
      const codes = [...new Set(hlds.map(h => h.code).filter(c => c && c !== "CASH"))];
      const prices = codes.length > 0 ? await apiGetPrices(codes) : {};
      const positions = computePositions(hlds, txns, prices);
      const byAccount = {};
      positions.forEach(p => {
        if (!byAccount[p.account]) byAccount[p.account] = 0;
        byAccount[p.account] += p.value; // value is already in CNY
      });
      const snapItems = await apiGetBalanceItems(newSnapId);
      const targets = snapItems.filter(i => i.category === "投资" && i.account_name && byAccount[i.account_name] != null);
      await Promise.all(targets.map(i =>
        apiUpdateBalanceItem(i.id, { amount: byAccount[i.account_name], currency: "CNY" })
      ));
    } catch (e) {
      console.warn("Investment auto-fill skipped:", e.message);
    }
  };

  const handleSnapUpdated = async () => {
    setShowEditSnap(false);
    const snaps = await apiGetBalanceSnapshots();
    setSnapshots(snaps);
  };

  const handleSnapCreated = async (newId, opts = {}) => {
    setShowNewSnap(false);
    setShowCopySnap(false);
    if (opts.fromCopy) await doInvestmentAutofill(newId);
    const snaps = await apiGetBalanceSnapshots();
    setSnapshots(snaps);
    const ai = await apiGetAllBalanceItems();
    setAllItems(ai);
    setSnapId(newId);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  if (loading) return (
    <div style={{ padding: "80px 32px", textAlign: "center", color: "var(--ink-4)" }}>
      <div style={{ fontSize: 14 }}>加载中…</div>
    </div>
  );

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 04 · BALANCE SHEET"
        title="资产负债"
        subtitle="Net Worth Tracker · 快照管理 · FX 换算"
        right={
          <div style={{ display: "flex", gap: 8 }}>
            <Button variant="secondary" icon="upload" onClick={() => setShowImport(true)}>导入</Button>
            {snap && <Button variant="secondary" icon="copy" onClick={() => setShowCopySnap(true)}>复制快照</Button>}
            <Button variant="primary" icon="plus" onClick={() => setEditItem({})}>新增条目</Button>
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
        onNewSnap={() => setShowNewSnap(true)}
        onEditSnap={() => setShowEditSnap(true)}
        onDeleteSnap={(id) => setDeleteTarget({ type: "snapshot", id })}
      />

      {/* Summary tiles */}
      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr 1fr 1fr", gap: 14, marginBottom: 18 }}>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>NET WORTH · 净资产</div>
          <div className="mono" style={{ fontSize: 38, fontWeight: 700, marginTop: 6 }}>
            {symFor(currency)}{fmtNum(toDisplay(netWorth, "CNY", currency), 0)}
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
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL ASSETS · 资产</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--down)" }}>
            +{symFor(currency)}{fmtNum(toDisplay(totalAssets, "CNY", currency), 0)}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>{items.filter(i=>i.side==="asset").length} 项 · {assetCats.length} 类</div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>TOTAL LIABILITIES · 负债</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6, color: "var(--up)" }}>
            −{symFor(currency)}{fmtNum(toDisplay(totalLiabilities, "CNY", currency), 0)}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
            {items.filter(i=>i.side==="liability").length} 项 · 负债率 {totalAssets ? (totalLiabilities/totalAssets*100).toFixed(0) : 0}%
          </div>
        </Card>
        <Card padding={20}>
          <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", textTransform: "uppercase", color: "var(--ink-4)" }}>LIQUIDITY · 流动性</div>
          <div className="mono" style={{ fontSize: 28, fontWeight: 700, marginTop: 6 }}>
            {symFor(currency)}{fmtNum(toDisplay(liquidAssets, "CNY", currency), 0)}
          </div>
          <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 4 }}>
            现金+理财+投资 · {totalAssets ? (liquidAssets/totalAssets*100).toFixed(0) : 0}% of assets
          </div>
        </Card>
      </div>

      {/* Category breakdowns */}
      {(assetCats.length > 0 || liabCats.length > 0) && (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, marginBottom: 18 }}>
          <CatBreakdownCard title="资产分类 Asset Breakdown" cats={assetCats} total={totalAssets} currency={currency}/>
          <CatBreakdownCard title="负债分类 Liability Breakdown" cats={liabCats} total={totalLiabilities} currency={currency}/>
        </div>
      )}

      {/* Detail table */}
      <Card padding={0} style={{ marginBottom: 18 }}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div>
            <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>明细 Items</div>
            <div style={{ fontSize: 12, color: "var(--ink-3)", marginTop: 2 }}>点击条目查看跨快照历史</div>
          </div>
          <Tabs variant="pill" value={sideFilter} onChange={setSideFilter} tabs={[
            { id: "all",       label: `全部 ${items.length}` },
            { id: "asset",     label: `资产 ${items.filter(i=>i.side==="asset").length}` },
            { id: "liability", label: `负债 ${items.filter(i=>i.side==="liability").length}` },
          ]}/>
        </div>
        {sortedFiltered.length === 0 ? (
          <div style={{ padding: "40px 18px", textAlign: "center", color: "var(--ink-4)", fontSize: 13 }}>
            暂无条目 · <button style={{ background: "none", border: "none", cursor: "pointer", color: "var(--ink)", textDecoration: "underline", fontSize: 13 }} onClick={() => setEditItem({})}>新增条目</button>
          </div>
        ) : (
          <>
            <div style={{ display: "grid", gridTemplateColumns: "1.6fr 100px 80px 130px 130px 1fr 50px", gap: 10, padding: "9px 18px", borderBottom: "1px solid var(--line)", fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".1em", fontWeight: 600 }}>
              <span>NAME / ACCOUNT</span><span>CATEGORY</span><span>SIDE</span>
              <span style={{ textAlign: "right" }}>AMOUNT</span>
              <span style={{ textAlign: "right" }}>≈ {currency}</span>
              <span>NOTE</span>
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
      {showNewSnap && (
        <NewSnapModal onClose={() => setShowNewSnap(false)} onDone={handleSnapCreated}/>
      )}
      {showCopySnap && snap && (
        <CopySnapModal snap={snap} onClose={() => setShowCopySnap(false)} onDone={handleSnapCreated}/>
      )}
      {showEditSnap && snap && (
        <EditSnapModal snap={snap} onClose={() => setShowEditSnap(false)} onDone={handleSnapUpdated}/>
      )}
      {showImport && (
        <ImportModal onClose={() => setShowImport(false)} onDone={loadAll}/>
      )}
      {deleteTarget && (
        <ConfirmDeleteModal
          message={deleteTarget.type === "snapshot"
            ? "确认删除此快照及其所有条目？此操作不可撤销。"
            : "确认删除此条目？"}
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

const SnapBar = ({ snapshots, snapId, setSnapId, snap, isLatest, showSnapMenu, setShowSnapMenu, snapSeries, onNewSnap, onEditSnap, onDeleteSnap }) => {
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
            {isLatest ? "LATEST · 当前最新版" : "HISTORICAL · 历史快照"}
          </div>
          <div style={{ fontSize: 13.5, marginTop: 2 }}>
            <span className="mono" style={{ fontWeight: 600 }}>{snap.snapshot_date}</span>
            <span style={{ margin: "0 8px", color: "var(--ink-4)" }}>·</span>
            <span>{snap.label}</span>
            {snap.note && <span style={{ marginLeft: 8, color: "var(--ink-3)", fontSize: 12 }}>— {snap.note}</span>}
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 13, color: "var(--ink-3)" }}>暂无快照 · 请先创建</div>
      )}
    </div>
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      <Button variant="secondary" icon="plus" onClick={onNewSnap} title="新建快照"/>
      {snap && <Button variant="ghost" icon="edit" onClick={onEditSnap} title="编辑快照信息"/>}
      {snap && <Button variant="ghost" icon="trash" onClick={() => onDeleteSnap(snapId)} title="删除当前快照"/>}
      <div ref={menuRef} style={{ position: "relative" }}>
        <Button variant="secondary" iconRight="chevron-down" onClick={() => setShowSnapMenu(v => !v)}>
          切换快照 · {snapshots.length} 版
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
                      {sel && <Badge tone="info" size="sm">当前</Badge>}
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
                {symFor(currency)}{fmtNum(toDisplay(c.value,"CNY",currency),0)} · {pct.toFixed(0)}%
              </div>
            </div>
          </div>
        );
      })}
    </div>
  </Card>
);

// ── Item row ──────────────────────────────────────────────────────────────────

const ItemRow = ({ item: it, currency, last, onClick, onEdit, onDelete }) => {
  const dispAmt = toDisplay(it.amount, it.currency, currency);
  const cnyAmt  = toDisplay(it.amount, it.currency, "CNY");
  const iconBtn = (onClick, name) => (
    <button onClick={onClick} style={{ width: 22, height: 22, background: "transparent", border: "none", cursor: "pointer", color: "var(--ink-4)", display: "flex", alignItems: "center", justifyContent: "center" }}>
      <Icon name={name} size={12}/>
    </button>
  );
  return (
    <div onClick={onClick} style={{ display: "grid", gridTemplateColumns: "1.6fr 100px 80px 130px 130px 1fr 50px", gap: 10, padding: "11px 18px", alignItems: "center", borderBottom: last ? "none" : "1px solid var(--line)", fontSize: 12.5, cursor: "pointer" }}
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
          {it.category}
        </span>
      </span>
      <span><Badge tone={it.side === "asset" ? "down" : "up"} size="sm">{it.side === "asset" ? "资产" : "负债"}</Badge></span>
      <span className="mono" style={{ textAlign: "right", fontWeight: 600 }}>
        {fmtMoney(it.amount, it.currency, 0)}
      </span>
      <span className="mono" style={{ textAlign: "right", color: currency === "CNY" ? "var(--ink-3)" : "var(--ink)" }}>
        {currency !== it.currency ? `${symFor(currency)}${fmtNum(dispAmt, 0)}` : <span style={{ color: "var(--ink-4)" }}>—</span>}
      </span>
      <span style={{ color: "var(--ink-3)", fontSize: 12, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{it.note || "—"}</span>
      <div style={{ display: "flex", gap: 2 }} onClick={e => e.stopPropagation()}>
        {iconBtn(onEdit, "edit")}
        {iconBtn(onDelete, "trash")}
      </div>
    </div>
  );
};

// ── Net worth trend ───────────────────────────────────────────────────────────

const NetWorthTrend = ({ series, highlightId }) => {
  const W = 380, H = 80, pad = 12;
  const nets = series.map(s => s.net);
  const maxV = Math.max(...nets, 0);
  const minV = Math.min(...nets, 0);
  const range = maxV - minV || 1;
  const x = (i) => pad + (i / (series.length - 1)) * (W - pad * 2);
  const y = (v) => pad + (1 - (v - minV) / range) * (H - pad * 2);
  const netPath = "M " + series.map((s, i) => `${x(i).toFixed(1)},${y(s.net).toFixed(1)}`).join(" L ");
  const fill = netPath + ` L ${x(series.length-1).toFixed(1)},${y(0).toFixed(1)} L ${x(0).toFixed(1)},${y(0).toFixed(1)} Z`;
  const hi = series.findIndex(s => s.id === highlightId);
  return (
    <div>
      <div style={{ fontSize: 11, fontWeight: 600, letterSpacing: ".12em", color: "var(--ink-4)", textTransform: "uppercase", marginBottom: 4 }}>HISTORY · {series.length} snapshots</div>
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} style={{ display: "block" }} preserveAspectRatio="none">
        {minV < 0 && <line x1={pad} x2={W-pad} y1={y(0)} y2={y(0)} stroke="var(--line-2)" strokeDasharray="2 3"/>}
        <path d={fill} fill="var(--ink)" fillOpacity=".06"/>
        <path d={netPath} stroke="var(--ink)" strokeWidth="1.8" fill="none"/>
        {series.map((s, i) => (
          <circle key={s.id} cx={x(i)} cy={y(s.net)} r={i === hi ? 4 : 2.5}
            fill={i === hi ? "var(--up)" : "var(--ink)"} stroke="#fff" strokeWidth="1"/>
        ))}
      </svg>
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 2 }}>
        <span className="mono" style={{ fontSize: 9.5, color: "var(--ink-4)" }}>{series[0]?.date}</span>
        <span className="mono" style={{ fontSize: 9.5, color: "var(--ink-4)" }}>{series[series.length-1]?.date}</span>
      </div>
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
               i.category === item.category;
      }
      return i.name === item.name;
    })
    .map(i => ({ ...i, snap: snapshots.find(s => s.id === i.snapshot_id) }))
    .filter(i => i.snap)
    .sort((a, b) => a.snap.snapshot_date.localeCompare(b.snap.snapshot_date));

  return (
    <Modal open title={`历史记录 · ${item.name}`} onClose={onClose} width={580}>
      <div style={{ padding: "16px 20px 20px" }}>
      <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 12 }}>
        {item.side === "asset" ? "资产" : "负债"} · {item.category}
      </div>
      {history.length === 0 ? (
        <div style={{ color: "var(--ink-4)", fontSize: 13 }}>仅当前快照有此条目</div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ fontSize: 10.5, color: "var(--ink-4)", textTransform: "uppercase", letterSpacing: ".08em" }}>
              <th style={{ textAlign: "left", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>快照日期</th>
              <th style={{ textAlign: "left", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>快照标签</th>
              <th style={{ textAlign: "right", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>金额</th>
              <th style={{ textAlign: "right", padding: "6px 0", borderBottom: "1px solid var(--line)" }}>≈ {currency}</th>
            </tr>
          </thead>
          <tbody>
            {history.map((h, i) => (
              <tr key={h.id} style={{ background: h.snapshot_id === item.snapshot_id ? "var(--bg-deep)" : "" }}>
                <td style={{ padding: "8px 0", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  <span className="mono">{h.snap.snapshot_date}</span>
                  {h.snapshot_id === item.snapshot_id && <Badge tone="info" size="sm" style={{ marginLeft: 8 }}>当前</Badge>}
                </td>
                <td style={{ padding: "8px 8px", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>{h.snap.label}</td>
                <td className="mono" style={{ textAlign: "right", padding: "8px 0", fontWeight: 600, borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  {fmtMoney(h.amount, h.currency, 0)}
                </td>
                <td className="mono" style={{ textAlign: "right", padding: "8px 0", color: "var(--ink-3)", borderBottom: i < history.length-1 ? "1px solid var(--line)" : "" }}>
                  {symFor(currency)}{fmtNum(toDisplay(h.amount, h.currency, currency), 0)}
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

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

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
    if (!form.name.trim()) { setError("名称不能为空"); return; }
    if (!form.amount || isNaN(parseFloat(form.amount))) { setError("金额不合法"); return; }
    setLoading(true); setError(null);
    try {
      if (isEdit) await apiUpdateBalanceItem(item.id, buildPayload());
      else        await apiCreateBalanceItem(buildPayload());
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title={isEdit ? "编辑条目" : "新增条目"} onClose={onClose} width={480}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label="名称" span2>
            <Input value={form.name} onChange={v => set("name", v)} placeholder="例：招商银行存款" style={{ width: "100%" }}/>
          </BalField>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <BalField label="分类">
              <BalSelect value={form.category} onChange={v => set("category", v)}
                options={BALANCE_CATEGORIES.map(c => ({ value: c, label: c }))}/>
            </BalField>
            <BalField label="资产 / 负债">
              <BalSelect value={form.side} onChange={v => set("side", v)}
                options={[{ value: "asset", label: "资产" }, { value: "liability", label: "负债" }]}/>
            </BalField>
            <BalField label="金额">
              <Input type="number" value={form.amount} onChange={v => set("amount", v)} placeholder="0" style={{ width: "100%" }}/>
            </BalField>
            <BalField label="货币">
              <BalSelect value={form.currency} onChange={v => set("currency", v)}
                options={CURRENCIES.map(c => ({ value: c, label: c }))}/>
            </BalField>
            {parentAccounts.length > 0 && (
              <>
                <BalField label="账户">
                  <BalSelect value={form.account_id} onChange={v => { set("account_id", v); set("sub_account_id", ""); }}
                    options={[{ value: "", label: "— 不选 —" }, ...parentAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
                <BalField label="子账户">
                  <BalSelect value={form.sub_account_id} onChange={v => set("sub_account_id", v)}
                    disabled={!form.account_id || subAccounts.length === 0}
                    options={[{ value: "", label: "— 不选 —" }, ...subAccounts.map(a => ({ value: String(a.id), label: a.name }))]}/>
                </BalField>
              </>
            )}
            <BalField label="备注" span2>
              <Input value={form.note} onChange={v => set("note", v)} placeholder="可选" style={{ width: "100%" }}/>
            </BalField>
            {isLoan && (
              <>
                <BalField label="年利率 (如 0.0365)">
                  <Input type="number" value={form.interest_rate} onChange={v => set("interest_rate", v)} placeholder="0.0365" style={{ width: "100%" }}/>
                </BalField>
                <BalField label="月还款额">
                  <Input type="number" value={form.monthly_payment} onChange={v => set("monthly_payment", v)} placeholder="10400" style={{ width: "100%" }}/>
                </BalField>
                <BalField label="起始日期">
                  <Input type="date" value={form.start_date} onChange={v => set("start_date", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label="到期日期">
                  <Input type="date" value={form.end_date} onChange={v => set("end_date", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
            {isOption && (
              <>
                <BalField label="单价">
                  <Input type="number" value={form.price} onChange={v => set("price", v)} style={{ width: "100%" }}/>
                </BalField>
                <BalField label="数量">
                  <Input type="number" value={form.quantity} onChange={v => set("quantity", v)} style={{ width: "100%" }}/>
                </BalField>
              </>
            )}
          </div>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? "保存中…" : "保存"}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── New snapshot modal ────────────────────────────────────────────────────────

const NewSnapModal = ({ onClose, onDone }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate]   = React.useState(today);
  const [label, setLabel] = React.useState("");
  const [note, setNote]   = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError]     = React.useState(null);

  const handleSave = async () => {
    if (!label.trim()) { setError("请输入快照标签"); return; }
    setLoading(true); setError(null);
    try {
      const snap = await apiCreateBalanceSnapshot({ snapshot_date: date, label: label.trim(), note: note.trim() || undefined });
      onDone(snap.id);
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title="新建快照" onClose={onClose} width={400}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label="日期"><Input type="date" value={date} onChange={setDate} style={{ width: "100%" }}/></BalField>
          <BalField label="标签"><Input value={label} onChange={setLabel} placeholder="例：2026-Q1 复盘" style={{ width: "100%" }}/></BalField>
          <BalField label="备注（可选）"><Input value={note} onChange={setNote} placeholder="可选" style={{ width: "100%" }}/></BalField>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? "创建中…" : "创建"}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Copy snapshot modal ───────────────────────────────────────────────────────

const CopySnapModal = ({ snap, onClose, onDone }) => {
  const today = new Date().toISOString().slice(0, 10);
  const [date, setDate]   = React.useState(today);
  const [label, setLabel] = React.useState(snap.label + " (复制)");
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
    <Modal open title={`复制快照 · ${snap.label}`} onClose={onClose} width={400}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ fontSize: 12, color: "var(--ink-3)", marginBottom: 14 }}>
          复制 {snap.item_count} 个条目到新快照
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label="新快照日期"><Input type="date" value={date} onChange={setDate} style={{ width: "100%" }}/></BalField>
          <BalField label="新快照标签"><Input value={label} onChange={setLabel} style={{ width: "100%" }}/></BalField>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? "复制中…" : "复制"}</Button>
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
    if (!label.trim()) { setError("标签不能为空"); return; }
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
    <Modal open title="编辑快照" onClose={onClose} width={400}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <BalField label="日期"><Input type="date" value={date} onChange={setDate} style={{ width: "100%" }}/></BalField>
          <BalField label="标签"><Input value={label} onChange={setLabel} style={{ width: "100%" }}/></BalField>
          <BalField label="备注（可选）"><Input value={note} onChange={setNote} placeholder="可选" style={{ width: "100%" }}/></BalField>
        </div>
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 18 }}>
          <Button variant="secondary" onClick={onClose}>取消</Button>
          <Button variant="primary" onClick={handleSave} disabled={loading}>{loading ? "保存中…" : "保存"}</Button>
        </div>
      </div>
    </Modal>
  );
};

// ── Import modal ──────────────────────────────────────────────────────────────

const ImportModal = ({ onClose, onDone }) => {
  const [file, setFile]       = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [result, setResult]   = React.useState(null);
  const [error, setError]     = React.useState(null);

  const handleImport = async () => {
    if (!file) { setError("请选择 CSV 文件"); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const r = await apiImportBalance(file);
      setResult(r);
      onDone();
    } catch (e) { setError(e.message); }
    finally     { setLoading(false); }
  };

  return (
    <Modal open title="导入 Notion CSV" onClose={onClose} width={460}>
      <div style={{ padding: "16px 20px 20px" }}>
        <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginBottom: 14, lineHeight: 1.6 }}>
          支持从 Notion 导出的资产负债 CSV 文件（含"关联资产负债表"列）。
          已存在的条目（同快照 + 同名 + 同侧）将跳过。
        </div>
        <input type="file" accept=".csv" onChange={e => setFile(e.target.files[0])} style={{ fontSize: 13 }}/>
        {result && (
          <div style={{ marginTop: 14, padding: "10px 12px", background: "var(--bg-deep)", borderRadius: 8, fontSize: 12.5 }}>
            <div>✓ 新建快照：{result.snapshots_created} · 导入条目：{result.items_imported}</div>
            {result.skipped?.length > 0 && (
              <div style={{ marginTop: 6, color: "var(--ink-3)" }}>跳过 {result.skipped.length} 行</div>
            )}
          </div>
        )}
        {error && <div style={{ color: "var(--up)", fontSize: 12, marginTop: 10 }}>{error}</div>}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 16 }}>
          <Button variant="secondary" onClick={onClose}>关闭</Button>
          {!result && <Button variant="primary" onClick={handleImport} disabled={loading || !file}>{loading ? "导入中…" : "导入"}</Button>}
        </div>
      </div>
    </Modal>
  );
};

// ── Confirm delete modal ──────────────────────────────────────────────────────

const ConfirmDeleteModal = ({ message, onClose, onConfirm }) => (
  <Modal open title="确认删除" onClose={onClose} width={380}>
    <div style={{ padding: "16px 20px 20px" }}>
      <div style={{ fontSize: 13.5, color: "var(--ink)", marginBottom: 20 }}>{message}</div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
        <Button variant="secondary" onClick={onClose}>取消</Button>
        <Button variant="danger" onClick={onConfirm}>删除</Button>
      </div>
    </div>
  </Modal>
);

window.BalanceSheet = BalanceSheet;
