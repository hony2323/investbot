"""HTTP API over the investbot advisory engine.

Thin wrappers around the existing library functions — the handlers return the same
Pydantic v2 models the CLI uses, which FastAPI serializes directly. Like the CLI, this
service is read-only and never executes trades.

Offline-friendly: `/api/health`, `/api/taste`, and `/api/portfolio?source=mock` need no
secrets. `/api/stock` and `/api/analyze` (without dry_run) require ANTHROPIC_API_KEY.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from investbot.analysis import portfolio as port
from investbot.analysis.claude import ClaudeClient, ClaudeError
from investbot.analysis.risk import build_risk_report
from investbot.analysis.stock import analyze_stock
from investbot.brokers.ibkr import BrokerError, get_portfolio
from investbot.config.loader import (
    ConfigError,
    get_anthropic_api_key,
    load_config,
    load_taste,
)
from investbot.models.portfolio import PortfolioSummary, RiskReport
from investbot.models.recommendation import (
    AppConfig,
    MemoResult,
    Recommendation,
    TasteProfile,
)

app = FastAPI(
    title="investbot API",
    description="Read-only, advisory investing assistant. Recommends — never trades.",
    version="0.1.0",
)

# The Vite dev server runs on :5173 and proxies /api here, but allow direct
# browser calls too during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- helpers --------------------------------------------------------------

def _resolve_source(source: Optional[str], config: AppConfig) -> str:
    src = (source or config.data.default_source).lower()
    if src not in ("live", "mock"):
        raise HTTPException(status_code=400, detail=f"source must be 'live' or 'mock', got {src!r}")
    return src


def _load() -> tuple[AppConfig, TasteProfile]:
    try:
        return load_config(), load_taste()
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def _client(config: AppConfig, taste: TasteProfile) -> ClaudeClient:
    try:
        return ClaudeClient(
            taste, config.claude, config.analysis.benchmark_etf, api_key=get_anthropic_api_key()
        )
    except ClaudeError as exc:
        # Missing/invalid API key — the caller asked for a Claude-backed route.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --- response models ------------------------------------------------------

class PortfolioResponse(BaseModel):
    summary: PortfolioSummary
    risk: RiskReport


class AnalyzeRequest(BaseModel):
    source: Optional[str] = None
    dry_run: bool = False
    no_market: bool = False


# --- routes ---------------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/taste", response_model=TasteProfile)
def taste() -> TasteProfile:
    try:
        return load_taste()
    except ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/portfolio", response_model=PortfolioResponse)
def portfolio(source: Optional[str] = None) -> PortfolioResponse:
    """Portfolio summary + risk report. `source=mock` works fully offline."""
    config, taste_profile = _load()
    src = _resolve_source(source, config)
    try:
        pf = get_portfolio(src, config)
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    port.write_snapshot(pf, config)
    return PortfolioResponse(
        summary=port.summarize(pf),
        risk=build_risk_report(pf, taste_profile),
    )


@app.get("/api/stock/{ticker}", response_model=Recommendation)
def stock(ticker: str) -> Recommendation:
    """Single-ticker recommendation. Requires ANTHROPIC_API_KEY."""
    config, taste_profile = _load()
    client = _client(config, taste_profile)
    try:
        rec, _facts = analyze_stock(ticker, client)
    except ClaudeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    port.append_recommendations([rec], config, command="stock")
    return rec


@app.post("/api/analyze", response_model=MemoResult)
def analyze(req: AnalyzeRequest) -> MemoResult:
    """Full portfolio memo. Mirrors `investbot analyze`. Requires a key unless dry_run."""
    config, taste_profile = _load()
    src = _resolve_source(req.source, config)
    try:
        pf = get_portfolio(src, config)
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    port.write_snapshot(pf, config)
    risk = build_risk_report(pf, taste_profile)
    holdings = pf.positions[: config.analysis.max_positions]

    if req.dry_run:
        return MemoResult(
            model=config.claude.model,
            account_id=pf.account_id,
            benchmark_etf=config.analysis.benchmark_etf,
            recommendations=[],
            invalid_tickers=[],
            memo_markdown="_Dry run — no Claude calls were made._",
            risk_report=risk,
        )

    client = _client(config, taste_profile)
    recs: list[Recommendation] = []
    invalid: list[str] = []
    for pos in holdings:
        facts = None
        if not req.no_market:
            from investbot.data_sources.market import get_stock_facts

            facts = get_stock_facts(pos.ticker)
        try:
            recs.append(client.recommend_for_holding(pos, facts, pf, risk))
        except ClaudeError:
            invalid.append(pos.ticker)

    memo_md = ""
    if recs:
        try:
            memo_md = client.synthesize_memo(recs, pf, risk)
        except ClaudeError:
            memo_md = ""

    result = MemoResult(
        model=config.claude.model,
        account_id=pf.account_id,
        benchmark_etf=config.analysis.benchmark_etf,
        recommendations=recs,
        invalid_tickers=invalid,
        memo_markdown=memo_md,
        risk_report=risk,
    )
    port.write_memo(result, config)
    port.append_recommendations(recs, config, command="analyze", account_id=pf.account_id)
    return result
