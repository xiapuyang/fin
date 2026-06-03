"""Email template for triggered alert notifications.

Imported by both check_alerts.py (real cron path) and verify_email.py
(end-to-end verification), so the user always sees the same template.
All localized strings come from fin.i18n.t() — see config/i18n/{en,zh}.json.
"""

from html import escape

from fin.i18n import t


def _safe(s: str) -> str:
    """Strip CR/LF so user-supplied alert names can't break headers/text rows."""
    return s.replace("\r", " ").replace("\n", " ")


def build_summary_email(fired: list[tuple]) -> tuple[str, str, str]:
    """Build (subject, html, text) for a batch of triggered alerts.

    Args:
        fired: list of (AlertModel, price, change_pct) tuples.

    Returns:
        Tuple of (subject, html_body, text_body) localized via fin.i18n.
    """
    count = len(fired)
    if count == 1:
        alert, _, _ = fired[0]
        subject = t(
            "alert.email.subject_one",
            name=_safe(alert.name),
            symbol=_safe(alert.symbol),
        )
    else:
        subject = t("alert.email.subject_many", count=count)

    rows_html = ""
    rows_text = ""
    for alert, price, change_pct in fired:
        change_str = f"{'+' if change_pct >= 0 else ''}{change_pct:.2f}%"
        color = "#D9352B" if change_pct >= 0 else "#1F8A4C"
        label = t(f"alert.email.cond.{alert.condition}")
        cond_str = f"{label} {alert.value}{'%' if 'change' in alert.condition else ''}"
        rows_html += (
            f"<tr>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-weight:600'>{escape(alert.name)}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:#5C6270'>{escape(alert.symbol)}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5'>{escape(cond_str)}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;font-weight:600'>{price:.2f}</td>"
            f"<td style='padding:8px 0;border-bottom:1px solid #E7E1D5;font-family:monospace;color:{color};font-weight:600'>{change_str}</td>"
            f"</tr>"
        )
        rows_text += (
            f"• {_safe(alert.name)} ({_safe(alert.symbol)}): {cond_str}  "
            f"{t('alert.email.text_price')}={price:.2f}  "
            f"{t('alert.email.text_change')}={change_str}\n"
        )

    html_body = (
        f"<html><body style='font-family:sans-serif;color:#14161B;max-width:600px'>"
        f"<h2 style='margin-bottom:4px'>{t('alert.email.header')}</h2>"
        f"<p style='color:#5C6270;margin-top:0'>{t('alert.email.subtitle', count=count)}</p>"
        f"<table style='border-collapse:collapse;width:100%;font-size:14px'>"
        f"<thead><tr style='color:#5C6270;font-size:12px'>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>{t('alert.email.col.name')}</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>{t('alert.email.col.symbol')}</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>{t('alert.email.col.condition')}</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>{t('alert.email.col.price')}</th>"
        f"<th style='padding:4px 0;border-bottom:2px solid #E7E1D5;text-align:left'>{t('alert.email.col.change')}</th>"
        f"</tr></thead>"
        f"<tbody>{rows_html}</tbody>"
        f"</table>"
        f"<p style='font-size:12px;color:#8B8F9A;margin-top:16px'>{t('alert.email.footer')}</p>"
        f"</body></html>"
    )
    text_body = (
        f"{t('alert.email.text_lead', count=count)}\n\n"
        f"{rows_text}\n"
        f"{t('alert.email.text_footer')}"
    )

    return subject, html_body, text_body
