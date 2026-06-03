"""Portfolio summarization and output persistence (snapshots, memos, history)."""

from __future__ import annotations

import json
from pathlib import Path

from investbot.analysis.risk import sector_weights
from investbot.config.loader import (
    memo_path,
    recommendations_path,
    snapshot_path,
    today_str,
)
from investbot.models.portfolio import Portfolio, PortfolioSummary
from investbot.models.recommendation import AppConfig, MemoResult, Recommendation

ADVISORY_FOOTER = (
    "> _investbot is advisory only. These are recommendations, not orders — no trades were "
    "executed. This is not financial advice._"
)


def summarize(portfolio: Portfolio, top_n: int = 10) -> PortfolioSummary:
    """Build an aggregated, render-friendly view of a portfolio."""
    ranked = sorted(portfolio.positions, key=lambda p: p.market_value, reverse=True)
    return PortfolioSummary(
        account_id=portfolio.account_id,
        as_of=portfolio.as_of,
        base_currency=portfolio.base_currency,
        total_value=portfolio.total_value,
        invested_value=portfolio.invested_value,
        cash=portfolio.cash,
        cash_pct=portfolio.cash_pct,
        position_count=len(portfolio.positions),
        top_positions=ranked[:top_n],
        sector_weights=sector_weights(portfolio),
    )


def write_snapshot(portfolio: Portfolio, config: AppConfig, day: str | None = None) -> Path:
    """Persist the portfolio as data/snapshots/<day>_portfolio.json (idempotent per day)."""
    path = snapshot_path(config, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(portfolio.model_dump_json(indent=2), encoding="utf-8")
    return path


def build_memo_document(memo: MemoResult) -> str:
    """Assemble the full markdown memo: header, risk, rec table, narrative, footer."""
    lines: list[str] = []
    lines.append(f"# Investment Memo — {memo.as_of.date().isoformat()}")
    lines.append("")
    account = memo.account_id or "n/a"
    lines.append(
        f"_Account: {account} · Model: {memo.model} · Benchmark: {memo.benchmark_etf}_"
    )
    lines.append("")

    # Risk summary
    lines.append("## Risk summary")
    if memo.risk_report.violations:
        for v in memo.risk_report.violations:
            lines.append(f"- **[{v.severity}]** {v.rule}: {v.detail}")
    else:
        lines.append("- No rule violations detected.")
    lines.append("")

    # Recommendation table
    lines.append("## Recommendations")
    if memo.recommendations:
        lines.append("| Ticker | Action | Confidence | Horizon | Suggested size |")
        lines.append("| --- | --- | --- | --- | --- |")
        for r in memo.recommendations:
            lines.append(
                f"| {r.ticker} | {r.action} | {r.confidence:.2f} | "
                f"{r.time_horizon} | {r.suggested_position_size} |"
            )
    else:
        lines.append("_No valid recommendations were produced._")
    if memo.invalid_tickers:
        lines.append("")
        lines.append(
            "_Skipped (invalid model output): " + ", ".join(memo.invalid_tickers) + "._"
        )
    lines.append("")

    # Narrative
    if memo.memo_markdown:
        lines.append("## Analysis")
        lines.append("")
        lines.append(memo.memo_markdown.strip())
        lines.append("")

    lines.append(ADVISORY_FOOTER)
    lines.append("")
    return "\n".join(lines)


def write_memo(memo: MemoResult, config: AppConfig, day: str | None = None) -> Path:
    """Render and persist data/memos/<day>_memo.md."""
    path = memo_path(config, day)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_memo_document(memo), encoding="utf-8")
    return path


def append_recommendations(
    recommendations: list[Recommendation],
    config: AppConfig,
    command: str,
    account_id: str | None = None,
) -> Path:
    """Append each recommendation as one JSON line to recommendations.jsonl."""
    path = recommendations_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = today_str()
    with path.open("a", encoding="utf-8") as fh:
        for rec in recommendations:
            row = {
                "as_of": stamp,
                "command": command,
                "account_id": account_id,
                **rec.model_dump(),
            }
            fh.write(json.dumps(row) + "\n")
    return path
