"""Basic market & fundamental data via yfinance.

Everything here degrades gracefully: yfinance can be rate-limited, offline, or missing
fields. Failures return partial/empty data so analysis can still proceed — they never
raise into the CLI.
"""

from __future__ import annotations

from pydantic import BaseModel


class StockFacts(BaseModel):
    """A small, robust set of fundamentals used as Claude context. All optional."""

    ticker: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    price: float | None = None
    market_cap: float | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    free_cashflow: float | None = None
    total_debt: float | None = None
    debt_to_equity: float | None = None
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None
    short_summary: str | None = None
    error: str | None = None


_FIELD_MAP = {
    "name": "longName",
    "sector": "sector",
    "industry": "industry",
    "price": "currentPrice",
    "market_cap": "marketCap",
    "trailing_pe": "trailingPE",
    "forward_pe": "forwardPE",
    "profit_margin": "profitMargins",
    "revenue_growth": "revenueGrowth",
    "free_cashflow": "freeCashflow",
    "total_debt": "totalDebt",
    "debt_to_equity": "debtToEquity",
    "fifty_two_week_high": "fiftyTwoWeekHigh",
    "fifty_two_week_low": "fiftyTwoWeekLow",
    "short_summary": "longBusinessSummary",
}


def get_stock_facts(ticker: str) -> StockFacts:
    """Fetch a compact fundamentals snapshot for a ticker, never raising."""
    ticker = ticker.strip().upper()
    try:
        import yfinance as yf

        info = yf.Ticker(ticker).info or {}
    except Exception as exc:  # network/parse/rate-limit — degrade gracefully
        return StockFacts(ticker=ticker, error=f"market data unavailable: {exc}")

    if not info or info.get("quoteType") is None and not info.get("longName"):
        return StockFacts(ticker=ticker, error="no data returned")

    values: dict[str, object] = {}
    for field, key in _FIELD_MAP.items():
        val = info.get(key)
        if field == "short_summary" and isinstance(val, str):
            val = val[:400]
        values[field] = val

    return StockFacts(ticker=ticker, **values)  # type: ignore[arg-type]


def get_sector(ticker: str) -> str | None:
    """Convenience: just the sector, for backfilling positions. Never raises."""
    return get_stock_facts(ticker).sector
