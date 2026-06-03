"""Recommendation, taste-profile, and app-config models.

`Recommendation` is the single source of truth for the JSON schema we force Claude to
emit (via tool-use) and validate. Keep its fields aligned with the prompt/tool schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from investbot.models.portfolio import RiskReport

Action = Literal["BUY", "HOLD", "WATCH", "TRIM", "SELL"]


class Recommendation(BaseModel):
    """A single advisory recommendation. Mirrors the Claude tool input schema."""

    action: Action
    ticker: str
    confidence: float = Field(ge=0.0, le=1.0)
    time_horizon: str
    reason: str
    risks: list[str] = Field(default_factory=list)
    what_would_change_my_mind: str
    suggested_position_size: str


class RiskRules(BaseModel):
    max_single_position_pct: float = 15.0
    max_sector_pct: float = 45.0
    min_cash_pct: float = 5.0
    allow_options: bool = False
    allow_margin: bool = False


class Preferences(BaseModel):
    likes: list[str] = Field(default_factory=list)
    avoids: list[str] = Field(default_factory=list)


class TasteProfile(BaseModel):
    risk: RiskRules = Field(default_factory=RiskRules)
    preferences: Preferences = Field(default_factory=Preferences)


class ClaudeConfig(BaseModel):
    model: str = "claude-opus-4-8"
    max_tokens: int = 2048
    memo_max_tokens: int = 3072


class IBKRConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 17
    timeout_seconds: int = 15


class DataConfig(BaseModel):
    default_source: Literal["live", "mock"] = "mock"
    snapshots_dir: str = "data/snapshots"
    memos_dir: str = "data/memos"
    fixtures_dir: str = "data/fixtures"
    recommendations_file: str = "data/recommendations.jsonl"


class AnalysisConfig(BaseModel):
    max_positions: int = 30
    benchmark_etf: str = "VOO"


class AppConfig(BaseModel):
    claude: ClaudeConfig = Field(default_factory=ClaudeConfig)
    ibkr: IBKRConfig = Field(default_factory=IBKRConfig)
    data: DataConfig = Field(default_factory=DataConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)


class MemoResult(BaseModel):
    """Full output of an `analyze` run."""

    as_of: datetime = Field(default_factory=datetime.now)
    model: str
    account_id: str | None = None
    benchmark_etf: str = "VOO"
    recommendations: list[Recommendation] = Field(default_factory=list)
    invalid_tickers: list[str] = Field(default_factory=list)
    memo_markdown: str = ""
    risk_report: RiskReport = Field(default_factory=RiskReport)
