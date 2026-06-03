"""Deterministic risk metrics and rule checks."""

from __future__ import annotations

from investbot.analysis.risk import build_risk_report, sector_weights


def test_sector_weights_sorted_desc(sample_portfolio):
    sw = sector_weights(sample_portfolio)
    assert sw[0].sector == "Technology"
    assert sw[0].weight_pct >= sw[-1].weight_pct


def test_single_position_breach(sample_portfolio, taste):
    report = build_risk_report(sample_portfolio, taste)
    rules = {v.rule for v in report.violations}
    assert "max_single_position_pct" in rules
    # MSFT (40k of ~71k) and CRWD (28k) both exceed 15%.
    breached = [v for v in report.violations if v.rule == "max_single_position_pct"]
    assert any("MSFT" in v.detail for v in breached)


def test_sector_breach(sample_portfolio, taste):
    report = build_risk_report(sample_portfolio, taste)
    assert any(v.rule == "max_sector_pct" for v in report.violations)


def test_low_cash_warning(sample_portfolio, taste):
    report = build_risk_report(sample_portfolio, taste)
    cash_warns = [v for v in report.violations if v.rule == "min_cash_pct"]
    assert cash_warns and cash_warns[0].severity == "warn"


def test_metrics_present(sample_portfolio, taste):
    report = build_risk_report(sample_portfolio, taste)
    for key in ("total_value", "cash_pct", "largest_position_pct", "largest_sector_pct"):
        assert key in report.metrics


def test_compliant_portfolio_no_breach(taste):
    from investbot.models.portfolio import Portfolio

    pf = Portfolio(
        cash=10000,
        positions=[
            {"ticker": "A", "quantity": 10, "market_price": 100, "sector": "Tech"},
            {"ticker": "B", "quantity": 10, "market_price": 100, "sector": "Health"},
            {"ticker": "C", "quantity": 10, "market_price": 100, "sector": "Energy"},
        ],
    )
    report = build_risk_report(pf, taste)
    assert not report.has_breaches
