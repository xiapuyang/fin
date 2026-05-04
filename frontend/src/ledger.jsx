/* Module 3 — Ledger */

const Ledger = () => {
  const total = LEDGER.reduce((s, l) => s + l.amount, 0);
  const expenses = LEDGER.filter(l => l.amount < 0).reduce((s, l) => s + l.amount, 0);
  const income = LEDGER.filter(l => l.amount > 0).reduce((s, l) => s + l.amount, 0);

  const byCat = {};
  LEDGER.filter(l => l.amount < 0).forEach(l => {
    const cat = l.category;
    byCat[cat] = (byCat[cat] || 0) - l.amount;
  });
  const catData = Object.entries(byCat).map(([k, v], i) => ({
    label: k, value: v,
    color: ["#1F4FE0", "#C8821F", "#6B4FB8", "#1F8A4C", "#B8447B", "#5C6270"][i % 6]
  }));

  // Mock 30-day spending bar chart
  const days = Array.from({ length: 30 }, (_, i) => ({
    label: i % 5 === 0 ? `${i + 1}` : "",
    value: 30 + Math.abs(Math.sin(i * 0.6) * 200) + Math.random() * 80,
    color: i === 28 ? "var(--ink)" : "var(--ink-5)",
  }));

  return (
    <div className="fade-in" style={{ padding: "28px 32px 80px", maxWidth: 1480, margin: "0 auto" }}>
      <SectionHeader
        kicker="MODULE 03 · LEDGER"
        title="记账"
        subtitle="Personal Ledger · 自动分类 · 月度报表 · Telegram 推送"
        right={<Button variant="primary" icon="plus">添加记录</Button>}
      />

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
        <SummaryTile label="收入 INCOME" value={`+¥${fmtNum(income, 0)}`} sub="this week" tone="up"/>
        <SummaryTile label="支出 EXPENSE" value={`−¥${fmtNum(Math.abs(expenses), 0)}`} sub="this week" tone="down"/>
        <SummaryTile label="净结余 NET" value={`${total >=0 ? "+":"−"}¥${fmtNum(Math.abs(total), 0)}`} sub="this week" tone={total >=0 ? "up" : "down"}/>
        <SummaryTile label="储蓄率 SAVINGS" value="34.2%" sub="3-month avg" tone="info"/>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1.4fr 1fr", gap: 14, marginBottom: 22 }}>
        <Card padding={20}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <div>
              <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>近 30 天支出</div>
              <div style={{ fontSize: 12, color: "var(--ink-3)" }}>Daily expenses · CNY</div>
            </div>
            <Tabs variant="pill" value="30d" onChange={()=>{}} tabs={[{id:"7d",label:"7D"},{id:"30d",label:"30D"},{id:"90d",label:"90D"},{id:"1y",label:"1Y"}]}/>
          </div>
          <BarChart data={days} width={780} height={180}/>
        </Card>
        <Card padding={20}>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700, marginBottom: 12 }}>分类占比</div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <Donut data={catData} size={150} thickness={22} centerValue={`¥${fmtNum(Math.abs(expenses), 0)}`} centerSub="total"/>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, fontSize: 12, flex: 1 }}>
              {catData.map(c => (
                <div key={c.label} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: c.color }}/>
                  <span style={{ flex: 1, color: "var(--ink-2)" }}>{c.label}</span>
                  <span className="mono" style={{ color: "var(--ink-3)" }}>{(c.value/Math.abs(expenses)*100).toFixed(0)}%</span>
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Card padding={0}>
        <div style={{ padding: "14px 18px", borderBottom: "1px solid var(--line)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div className="serif-cn" style={{ fontSize: 17, fontWeight: 700 }}>最近交易 Recent</div>
          <Input placeholder="搜索…" prefix={<Icon name="search" size={13}/>} style={{ width: 240, height: 30 }}/>
        </div>
        {LEDGER.map((l, i) => {
          const isUp = l.amount >= 0;
          return (
            <div key={i} style={{ padding: "12px 18px", display: "grid", gridTemplateColumns: "100px 1fr 1fr 130px", gap: 12, alignItems: "center", borderBottom: i < LEDGER.length - 1 ? "1px solid var(--line)" : "none" }}>
              <span className="mono" style={{ color: "var(--ink-3)", fontSize: 12 }}>{l.date}</span>
              <Badge tone={isUp ? "up" : "neutral"} size="sm">{l.category}</Badge>
              <span style={{ fontSize: 13, color: "var(--ink-2)" }}>{l.note}</span>
              <span className="mono" style={{ textAlign: "right", fontSize: 14, fontWeight: 600, color: isUp ? "var(--up)" : "var(--ink)" }}>
                {isUp ? "+" : "−"}¥{fmtNum(Math.abs(l.amount), 2)}
              </span>
            </div>
          );
        })}
      </Card>

      <ComingSoonBanner module="Ledger" features={["银行账单 OCR 导入", "智能分类规则", "Telegram bot 实时录入", "月度报表 PDF 导出"]} />
    </div>
  );
};

const SummaryTile = ({ label, value, sub, tone }) => {
  const c = { up: "var(--up)", down: "var(--down)", info: "var(--info)" }[tone] || "var(--ink)";
  return (
    <Card padding={16}>
      <div style={{ fontSize: 10.5, fontWeight: 600, color: "var(--ink-4)", letterSpacing: ".12em" }}>{label}</div>
      <div className="mono" style={{ fontSize: 22, fontWeight: 700, marginTop: 6, color: c }}>{value}</div>
      <div style={{ fontSize: 11.5, color: "var(--ink-4)", marginTop: 2 }}>{sub}</div>
    </Card>
  );
};

window.Ledger = Ledger;
window.SummaryTile = SummaryTile;
