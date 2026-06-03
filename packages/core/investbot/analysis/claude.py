"""Anthropic client wrapper.

Centralizes model config, prompt caching, tool-forced JSON generation, safe validation,
and a single repair retry. The underlying client is injectable so tests can run fully
offline with a fake.
"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import ValidationError

from investbot.analysis import prompt_builder as pb
from investbot.models.portfolio import Portfolio, Position, RiskReport
from investbot.models.recommendation import (
    ClaudeConfig,
    Recommendation,
    TasteProfile,
)


class ClaudeError(Exception):
    """Raised when Claude cannot produce a usable response."""


class _MessagesClient(Protocol):
    """Minimal surface we need from anthropic.Anthropic (for typing + fakes)."""

    messages: Any


def _build_anthropic(api_key: str) -> _MessagesClient:
    try:
        import anthropic
    except Exception as exc:  # pragma: no cover - import/runtime guard
        raise ClaudeError(f"anthropic SDK unavailable: {exc}") from exc
    return anthropic.Anthropic(api_key=api_key)


class ClaudeClient:
    """Wraps an Anthropic client with investbot-specific calls."""

    def __init__(
        self,
        taste: TasteProfile,
        config: ClaudeConfig,
        benchmark_etf: str = "VOO",
        api_key: str | None = None,
        client: _MessagesClient | None = None,
    ) -> None:
        self.taste = taste
        self.config = config
        self.benchmark_etf = benchmark_etf
        if client is not None:
            self._client = client
        else:
            if not api_key:
                raise ClaudeError(
                    "ANTHROPIC_API_KEY is not set. Add it to .env, or use --dry-run."
                )
            self._client = _build_anthropic(api_key)
        self._system_text = pb.system_prompt(taste, benchmark_etf)
        self._tool = pb.recommendation_tool_schema()

    # --- public API -------------------------------------------------------

    def recommend_for_holding(
        self, position: Position, facts, portfolio: Portfolio, risk_report: RiskReport
    ) -> Recommendation:
        user = pb.holding_user_prompt(
            position, facts, portfolio, risk_report, self.benchmark_etf
        )
        return self._tool_call(user, expected_ticker=position.ticker)

    def recommend_for_stock(self, facts, headlines) -> Recommendation:
        user = pb.stock_user_prompt(facts, headlines, self.benchmark_etf)
        return self._tool_call(user, expected_ticker=getattr(facts, "ticker", None))

    def synthesize_memo(
        self,
        recommendations: list[Recommendation],
        portfolio: Portfolio,
        risk_report: RiskReport,
    ) -> str:
        user = pb.memo_user_prompt(
            recommendations, portfolio, risk_report, self.benchmark_etf
        )
        resp = self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.memo_max_tokens,
            system=self._cached_system(),
            messages=[{"role": "user", "content": user}],
        )
        return _extract_text(resp)

    # --- internals --------------------------------------------------------

    def _cached_system(self) -> list[dict]:
        # Mark the stable persona/taste block for prompt caching so repeated
        # per-holding calls reuse it.
        return [
            {
                "type": "text",
                "text": self._system_text,
                "cache_control": {"type": "ephemeral"},
            }
        ]

    def _tool_call(self, user: str, expected_ticker: str | None) -> Recommendation:
        rec = self._attempt_tool_call(user)
        if rec is None:
            # One repair retry with the error fed back into the prompt.
            repair = (
                user
                + "\n\nIMPORTANT: your previous response was invalid. Call "
                + f"{pb.TOOL_NAME} again. 'action' MUST be one of "
                + "BUY/HOLD/WATCH/TRIM/SELL and 'confidence' MUST be a number "
                + "between 0.0 and 1.0. Provide all required fields."
            )
            rec = self._attempt_tool_call(repair)
        if rec is None:
            raise ClaudeError("Claude did not return a valid recommendation after retry.")
        if expected_ticker and rec.ticker.upper() != expected_ticker.upper():
            # Trust the holding we asked about over the model's echo.
            rec.ticker = expected_ticker.upper()
        else:
            rec.ticker = rec.ticker.upper()
        return rec

    def _attempt_tool_call(self, user: str) -> Recommendation | None:
        resp = self._client.messages.create(
            model=self.config.model,
            max_tokens=self.config.max_tokens,
            system=self._cached_system(),
            tools=[self._tool],
            tool_choice={"type": "tool", "name": pb.TOOL_NAME},
            messages=[{"role": "user", "content": user}],
        )
        tool_input = _extract_tool_input(resp, pb.TOOL_NAME)
        if tool_input is None:
            return None
        try:
            return Recommendation.model_validate(tool_input)
        except ValidationError:
            return None


def _extract_tool_input(resp, tool_name: str) -> dict | None:
    """Return the input dict of the first matching tool_use block, or None."""
    content = getattr(resp, "content", None) or []
    for block in content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
            data = getattr(block, "input", None)
            if isinstance(data, dict):
                return data
    return None


def _extract_text(resp) -> str:
    """Concatenate text blocks from a message response."""
    content = getattr(resp, "content", None) or []
    parts = [
        getattr(block, "text", "")
        for block in content
        if getattr(block, "type", None) == "text"
    ]
    return "\n".join(p for p in parts if p).strip()
