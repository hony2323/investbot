"""Build prompts and the tool schema for Claude.

The system prompt encodes a conservative-analyst persona and injects the user's taste
rules. The recommendation tool schema is derived from the `Recommendation` Pydantic model
so the forced JSON and our validation can never drift apart.
"""

from __future__ import annotations

import json

from investbot.models.portfolio import Portfolio, Position, RiskReport
from investbot.models.recommendation import Recommendation, TasteProfile

TOOL_NAME = "emit_recommendation"

# Human-readable guidance layered onto the auto-generated schema to steer the model.
_FIELD_DESCRIPTIONS = {
    "action": "One of BUY, HOLD, WATCH, TRIM, SELL. Default to HOLD/WATCH unless there is a clear reason to act.",
    "ticker": "The ticker symbol this recommendation is about (uppercase).",
    "confidence": "Your confidence in this call, 0.0-1.0. Be honest; low confidence is fine.",
    "time_horizon": "Intended holding horizon, e.g. '2-5 years'. Favor long horizons.",
    "reason": "Concise, specific rationale grounded in the provided facts and the user's taste profile.",
    "risks": "Key risks that could invalidate this thesis.",
    "what_would_change_my_mind": "Concrete evidence that would flip this recommendation.",
    "suggested_position_size": "Target size as a percent range of the portfolio, e.g. '0-5%'.",
}


def recommendation_tool_schema() -> dict:
    """Anthropic tool definition whose input_schema is the Recommendation model."""
    schema = Recommendation.model_json_schema()
    schema.pop("title", None)
    schema["additionalProperties"] = False
    for name, prop in schema.get("properties", {}).items():
        if name in _FIELD_DESCRIPTIONS:
            prop["description"] = _FIELD_DESCRIPTIONS[name]
    return {
        "name": TOOL_NAME,
        "description": (
            "Emit a single structured investment recommendation for one ticker. "
            "Always weigh the recommendation against doing nothing and against buying a "
            "broad-market ETF."
        ),
        "input_schema": schema,
    }


def system_prompt(taste: TasteProfile, benchmark_etf: str = "VOO") -> str:
    """The conservative-analyst persona + the user's taste/risk rules.

    Returned as a single string; the caller wraps it in a cache_control block.
    """
    likes = "\n".join(f"  - {x}" for x in taste.preferences.likes) or "  - (none specified)"
    avoids = "\n".join(f"  - {x}" for x in taste.preferences.avoids) or "  - (none specified)"
    r = taste.risk
    return f"""You are a conservative, long-term investment analyst assisting a single retail investor.

ROLE AND TONE
- You behave like a disciplined analyst, not a hype machine. No price predictions, no
  guarantees, no "to the moon" language.
- You are honest about uncertainty. Low confidence is an acceptable and useful answer.
- You think in years, not days. You dislike short-term trading.

NON-NEGOTIABLE RULES
- This tool is ADVISORY ONLY. You never place trades; you only suggest. Never imply an
  order will be executed.
- For EVERY recommendation, explicitly weigh it against two baselines:
    (1) doing nothing (holding current positions / cash), and
    (2) buying a broad-market ETF ({benchmark_etf}).
  If the idea is not clearly better than those baselines, prefer HOLD or WATCH.
- No options and no margin. Ignore/avoid any such strategies.
- Respect the investor's risk limits below when sizing and when flagging concentration.

INVESTOR RISK LIMITS (from their taste profile)
- Max single position: {r.max_single_position_pct:.0f}% of portfolio
- Max sector exposure: {r.max_sector_pct:.0f}% of portfolio
- Minimum cash buffer: {r.min_cash_pct:.0f}% of portfolio
- Options allowed: {str(r.allow_options).lower()} | Margin allowed: {str(r.allow_margin).lower()}

WHAT THE INVESTOR LIKES
{likes}

WHAT THE INVESTOR AVOIDS
{avoids}

When a holding clearly conflicts with the "avoids" list or breaches a risk limit, say so
plainly and lean toward TRIM/SELL/WATCH as appropriate. When a holding fits the "likes"
list, has durable fundamentals, and sits within risk limits, HOLD/BUY may be justified —
but only if it beats the two baselines above."""


def _facts_block(facts) -> str:
    """Render optional StockFacts (or None) as a compact context block."""
    if facts is None:
        return "Market data: (not fetched)"
    if getattr(facts, "error", None):
        return f"Market data: unavailable ({facts.error})"
    fields = {
        "name": facts.name,
        "sector": facts.sector,
        "industry": facts.industry,
        "price": facts.price,
        "market_cap": facts.market_cap,
        "trailing_pe": facts.trailing_pe,
        "forward_pe": facts.forward_pe,
        "profit_margin": facts.profit_margin,
        "revenue_growth": facts.revenue_growth,
        "free_cashflow": facts.free_cashflow,
        "debt_to_equity": facts.debt_to_equity,
        "52w_high": facts.fifty_two_week_high,
        "52w_low": facts.fifty_two_week_low,
    }
    lines = [f"  {k}: {v}" for k, v in fields.items() if v is not None]
    body = "\n".join(lines) if lines else "  (no fundamental fields available)"
    summary = f"\n  business: {facts.short_summary}" if facts.short_summary else ""
    return "Market data (yfinance):\n" + body + summary


def holding_user_prompt(
    position: Position,
    facts,
    portfolio: Portfolio,
    risk_report: RiskReport,
    benchmark_etf: str = "VOO",
) -> str:
    """Per-holding prompt for the recommendation tool call."""
    violations = [v for v in risk_report.violations if position.ticker in v.detail]
    viol_text = (
        "\n".join(f"  - [{v.severity}] {v.detail}" for v in violations)
        if violations
        else "  - none specific to this holding"
    )
    return f"""Analyze this single holding and call {TOOL_NAME} with your recommendation.

HOLDING
  ticker: {position.ticker}
  name: {position.name or 'n/a'}
  quantity: {position.quantity}
  avg_cost: {position.avg_cost}
  market_price: {position.market_price}
  market_value: {position.market_value}
  unrealized_pnl: {position.unrealized_pnl} ({position.unrealized_pnl_pct}%)
  weight_pct: {position.weight_pct}% of portfolio
  sector: {position.sector or 'Unknown'}

PORTFOLIO CONTEXT
  total_value: {portfolio.total_value}
  cash_pct: {portfolio.cash_pct}%
  position_count: {len(portfolio.positions)}

RISK FLAGS FOR THIS HOLDING
{viol_text}

{_facts_block(facts)}

Remember: weigh HOLD/TRIM/SELL/BUY/WATCH against doing nothing and against buying {benchmark_etf}."""


def stock_user_prompt(facts, headlines, benchmark_etf: str = "VOO") -> str:
    """Standalone single-stock prompt (no existing position)."""
    news = ""
    if headlines:
        news = "\nRecent headlines:\n" + "\n".join(
            f"  - {h.title}" + (f" ({h.publisher})" if h.publisher else "") for h in headlines
        )
    ticker = getattr(facts, "ticker", "the stock")
    return f"""Analyze this stock as a potential or existing holding and call {TOOL_NAME}.
The investor does not necessarily own it; size your suggestion accordingly.

TICKER: {ticker}

{_facts_block(facts)}{news}

Weigh your recommendation against doing nothing and against buying {benchmark_etf}."""


def memo_user_prompt(
    recommendations: list[Recommendation],
    portfolio: Portfolio,
    risk_report: RiskReport,
    benchmark_etf: str = "VOO",
) -> str:
    """Prompt to synthesize a narrative memo from already-validated recommendations."""
    recs_json = json.dumps([r.model_dump() for r in recommendations], indent=2)
    violations = (
        "\n".join(f"  - [{v.severity}] {v.rule}: {v.detail}" for v in risk_report.violations)
        or "  - none"
    )
    return f"""Write a concise investment memo in Markdown synthesizing the per-holding
recommendations below. Do NOT invent new tickers or contradict the structured calls.

Structure:
1. A short "Bottom line" paragraph.
2. "Portfolio risk" — interpret the rule violations and concentration.
3. "By holding" — one short bullet per ticker referencing its action.
4. "The do-nothing / index baseline" — honestly assess whether the investor would likely
   be better off just holding cash + {benchmark_etf}.
Keep it sober and specific. No hype. End with a one-line reminder that this is advisory
only and not financial advice.

PORTFOLIO
  total_value: {portfolio.total_value}, cash_pct: {portfolio.cash_pct}%, positions: {len(portfolio.positions)}

RULE VIOLATIONS
{violations}

STRUCTURED RECOMMENDATIONS (authoritative)
{recs_json}"""
