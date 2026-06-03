"""Single-stock analysis orchestration for `investbot stock TICKER`.

Fetches fundamentals + headlines, asks Claude for one validated recommendation, and
returns it. Persistence is handled by the CLI so this stays easy to test.
"""

from __future__ import annotations

from investbot.analysis.claude import ClaudeClient
from investbot.data_sources.market import StockFacts, get_stock_facts
from investbot.data_sources.news import get_recent_headlines
from investbot.models.recommendation import Recommendation


def analyze_stock(ticker: str, client: ClaudeClient) -> tuple[Recommendation, StockFacts]:
    """Return a validated recommendation and the fetched facts for one ticker."""
    ticker = ticker.strip().upper()
    facts = get_stock_facts(ticker)
    headlines = get_recent_headlines(ticker)
    rec = client.recommend_for_stock(facts, headlines)
    return rec, facts
