"""Email template for triggered alert notifications.

Imported by both check_alerts.py (real cron path) and verify_email.py
(end-to-end verification), so the user always sees the same template.
"""

_COND_LABELS = {
    "price_gte": "价格 ≥",
    "price_lte": "价格 ≤",
    "change_gte": "涨幅 ≥",
    "change_lte": "跌幅 ≤",
}


def build_summary_email(fired: list[tuple]) -> tuple[str, str, str]:
    """Build (subject, html, text) for a batch of triggered alerts.

    fired: list of (AlertModel, price, change_pct) tuples.
    """
    if len(fired) == 1:
        alert, _, _ = fired[0]
        subject = f"[fin] 提醒触发: {alert.name} ({alert.symbol})"
    else:
        subject = f"[fin] {len(fired)} 个提醒触发"

    rows_html = ""
    rows_text = ""
    for alert, price, change_pct in fired:
        change_str = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
        color = "#D9352B" if change_pct >= 0 else "#1F8A4C"
        label = _COND_LABELS.get(alert.condition, alert.condition)
        cond_str = f"{label} {alert.value}{'%' if 'change' in alert.condition else ''}"
        rows_html += (
            f"<tr>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-weight:600'>{alert.name}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:#5C6270'>{alert.symbol}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5'>{cond_str}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;font-weight:600'>{price:.2f}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:{color};font-weight:600'>{change_str}</td>"
            f"</tr>"
        )
        rows_text += f"• {alert.name} ({alert.symbol}): {cond_str}  价格={price:.2f}  涨跌={change_str}\n"

    html_body = (
        f"<html><body style='font-family:sans-serif;color:#14161B;max-width:600px'>"
        f"<h2 style='margin-bottom:4px'>📊 股票提醒触发</h2>"
        f"<p style='color:#5C6270;margin-top:0'>fin · {len(fired)} 个提醒已触发</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>"
        f"<thead><tr style='color:#5C6270;font-size:12px'>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>名称</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>代码</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>条件</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>价格</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>涨跌</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
        f"<p style='font-size:12px;color:#8B8F9A;margin-top:16px'>以上提醒已自动禁用，请前往 fin 管理页面重新启用。</p>"
        f"</body></html>"
    )
    text_body = f"触发 {len(fired)} 个提醒:\n\n{rows_text}\n以上提醒已自动禁用。"

    return subject, html_body, text_body
