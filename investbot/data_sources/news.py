"""Optional recent-headlines lookup.

MVP stub: returns recent headlines from yfinance when available, otherwise an empty list.
Designed to degrade gracefully and never raise into the CLI. A future version could pull
from a dedicated news API via `requests`.
"""

from __future__ import annotations

from pydantic import BaseModel


class Headline(BaseModel):
    title: str
    publisher: str | None = None
    link: str | None = None


def get_recent_headlines(ticker: str, limit: int = 5) -> list[Headline]:
    """Best-effort recent headlines for a ticker. Returns [] on any problem."""
    ticker = ticker.strip().upper()
    try:
        import yfinance as yf

        raw = yf.Ticker(ticker).news or []
    except Exception:
        return []

    headlines: list[Headline] = []
    for item in raw[:limit]:
        # yfinance news shape has shifted over versions; handle both flat and nested.
        content = item.get("content", item) if isinstance(item, dict) else {}
        title = content.get("title") or (item.get("title") if isinstance(item, dict) else None)
        if not title:
            continue
        provider = content.get("provider") or {}
        publisher = provider.get("displayName") if isinstance(provider, dict) else None
        publisher = publisher or (item.get("publisher") if isinstance(item, dict) else None)
        headlines.append(Headline(title=title, publisher=publisher))
    return headlines
