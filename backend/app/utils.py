from __future__ import annotations

from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def month_key(value: str) -> str:
    return value[:7]


INDICATOR_META = {
    "exchange_rate": {
        "label": "원/달러 환율",
        "short_label": "환율",
        "unit": "원/USD",
        "decimals": 2,
    },
    "base_rate": {
        "label": "한국은행 기준금리",
        "short_label": "기준금리",
        "unit": "%",
        "decimals": 2,
    },
    "cpi": {
        "label": "소비자물가지수(CPI)",
        "short_label": "CPI",
        "unit": "2020=100",
        "decimals": 2,
    },
}
