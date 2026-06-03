"""Portfolio data models.

`Position` and `Portfolio` are populated from either Interactive Brokers (live) or a
mock fixture. Derived figures (market value, unrealized P&L, weight) are computed here so
the rest of the app — and Claude — always reason from consistent numbers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator


class Position(BaseModel):
    """A single long equity position. No options/margin are represented."""

    ticker: str
    name: str | None = None
    quantity: float
    avg_cost: float = 0.0
    market_price: float = 0.0
    sector: str | None = None
    asset_class: str = "STK"

    # Assigned by Portfolio after total value is known. 0 until then.
    weight_pct: float = 0.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def market_value(self) -> float:
        return round(self.quantity * self.market_price, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cost_basis(self) -> float:
        return round(self.quantity * self.avg_cost, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unrealized_pnl(self) -> float:
        return round(self.market_value - self.cost_basis, 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return round(self.unrealized_pnl / self.cost_basis * 100, 2)


class Portfolio(BaseModel):
    """A snapshot of cash plus long equity positions at a point in time."""

    account_id: str | None = None
    as_of: datetime = Field(default_factory=datetime.now)
    base_currency: str = "USD"
    cash: float = 0.0
    positions: list[Position] = Field(default_factory=list)

    @model_validator(mode="after")
    def _assign_weights(self) -> "Portfolio":
        total = self.total_value
        if total > 0:
            for pos in self.positions:
                pos.weight_pct = round(pos.market_value / total * 100, 2)
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def invested_value(self) -> float:
        return round(sum(p.market_value for p in self.positions), 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_value(self) -> float:
        return round(self.cash + sum(p.market_value for p in self.positions), 2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cash_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return round(self.cash / self.total_value * 100, 2)


class SectorWeight(BaseModel):
    sector: str
    market_value: float
    weight_pct: float


class PortfolioSummary(BaseModel):
    """Aggregated view used for rendering and prompt context."""

    account_id: str | None
    as_of: datetime
    base_currency: str
    total_value: float
    invested_value: float
    cash: float
    cash_pct: float
    position_count: int
    top_positions: list[Position]
    sector_weights: list[SectorWeight]


Severity = Literal["info", "warn", "breach"]


class RuleViolation(BaseModel):
    rule: str
    detail: str
    severity: Severity = "warn"


class RiskReport(BaseModel):
    """Deterministic, locally computed risk metrics and rule checks.

    Computed *before* Claude so recommendations are grounded in real numbers.
    """

    metrics: dict[str, float] = Field(default_factory=dict)
    violations: list[RuleViolation] = Field(default_factory=list)

    @property
    def has_breaches(self) -> bool:
        return any(v.severity == "breach" for v in self.violations)
