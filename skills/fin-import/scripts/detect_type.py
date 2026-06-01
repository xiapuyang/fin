"""Classify input text/CSV into one of fin's 7 import domains.

Score by domain-specific keyword matches in headers (weight 2) + body
(weight = occurrence count). Highest scorer wins if >= MIN_SCORE; ties
→ 'ambiguous'.
"""

import csv
import io
import sys

_DOMAIN_TOKENS = {
    "ledger": {"direction", "expense", "支出", "收入", "分类"},
    "balance": {"asset", "liability", "side", "snapshot", "资产", "负债"},
    "income": {"salary", "dividend", "interest", "工资", "股息", "利息"},
    "transactions": {"buy", "sell", "side", "shares", "trade", "买入", "卖出"},
    "holdings": {"avg_cost", "shares", "market", "持仓", "成本"},
    "alerts": {
        "condition",
        "price_gte",
        "price_lte",
        "change_gte",
        "change_lte",
        "提醒",
    },
    "watchlist": {"symbol", "watchlist", "ticker", "自选", "关注"},
}
_MIN_SCORE = 2


def detect(text: str) -> str:
    """Classify input text into one of fin's 7 import domains.

    Args:
        text: Raw input text (CSV or plain text).

    Returns:
        Domain name string (alerts, transactions, holdings, income, ledger,
        balance, watchlist) or 'ambiguous' when confidence is too low.
    """
    text_lower = text.lower()
    headers: set[str] = set()
    first = text.splitlines()[0] if text else ""
    if "," in first:
        try:
            row = next(csv.reader(io.StringIO(text)), None)
            if row:
                headers = {c.strip().lower() for c in row}
        except csv.Error:
            pass
    elif first.strip():
        headers = {first.strip().lower()}

    scores: dict[str, int] = {}
    for domain, tokens in _DOMAIN_TOKENS.items():
        s = 0
        for t in tokens:
            if t in headers:
                s += 2
            else:
                s += text_lower.count(t)
        scores[domain] = s

    best, best_s = max(scores.items(), key=lambda kv: kv[1])
    if best_s < _MIN_SCORE:
        return "ambiguous"
    ties = [d for d, s in scores.items() if s == best_s and d != best]
    if ties:
        return "ambiguous"
    return best


if __name__ == "__main__":
    print(detect(sys.stdin.read()))
