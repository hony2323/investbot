"""Deterministic, locally computed risk metrics and rule checks.

This runs *before* Claude so every recommendation is grounded in real, reproducible
numbers rather than the model's estimates. Rules come from `taste.yaml`.
"""

from __future__ import annotations

from collections import defaultdict

from investbot.models.portfolio import (
    Portfolio,
    RiskReport,
    RuleViolation,
    SectorWeight,
)
from investbot.models.recommendation import TasteProfile


def sector_weights(portfolio: Portfolio) -> list[SectorWeight]:
    """Aggregate market value and weight by sector (cash excluded)."""
    totals: dict[str, float] = defaultdict(float)
    for pos in portfolio.positions:
        sector = pos.sector or "Unknown"
        totals[sector] += pos.market_value
    total_value = portfolio.total_value or 1.0
    weights = [
        SectorWeight(
            sector=sector,
            market_value=round(mv, 2),
            weight_pct=round(mv / total_value * 100, 2),
        )
        for sector, mv in totals.items()
    ]
    return sorted(weights, key=lambda s: s.weight_pct, reverse=True)


def build_risk_report(portfolio: Portfolio, taste: TasteProfile) -> RiskReport:
    """Compute metrics and check them against the taste profile's risk rules."""
    rules = taste.risk
    violations: list[RuleViolation] = []

    largest_pct = max((p.weight_pct for p in portfolio.positions), default=0.0)
    sectors = sector_weights(portfolio)
    largest_sector = sectors[0] if sectors else None

    metrics: dict[str, float] = {
        "total_value": portfolio.total_value,
        "invested_value": portfolio.invested_value,
        "cash_pct": portfolio.cash_pct,
        "position_count": float(len(portfolio.positions)),
        "largest_position_pct": largest_pct,
        "largest_sector_pct": largest_sector.weight_pct if largest_sector else 0.0,
    }

    # Single-position concentration.
    for pos in portfolio.positions:
        if pos.weight_pct > rules.max_single_position_pct:
            violations.append(
                RuleViolation(
                    rule="max_single_position_pct",
                    detail=(
                        f"{pos.ticker} is {pos.weight_pct:.1f}% of the portfolio "
                        f"(limit {rules.max_single_position_pct:.0f}%)."
                    ),
                    severity="breach",
                )
            )

    # Sector concentration.
    for sw in sectors:
        if sw.weight_pct > rules.max_sector_pct:
            violations.append(
                RuleViolation(
                    rule="max_sector_pct",
                    detail=(
                        f"Sector '{sw.sector}' is {sw.weight_pct:.1f}% of the portfolio "
                        f"(limit {rules.max_sector_pct:.0f}%)."
                    ),
                    severity="breach",
                )
            )

    # Minimum cash buffer.
    if portfolio.cash_pct < rules.min_cash_pct:
        violations.append(
            RuleViolation(
                rule="min_cash_pct",
                detail=(
                    f"Cash is {portfolio.cash_pct:.1f}% "
                    f"(minimum {rules.min_cash_pct:.0f}%)."
                ),
                severity="warn",
            )
        )

    return RiskReport(metrics=metrics, violations=violations)
