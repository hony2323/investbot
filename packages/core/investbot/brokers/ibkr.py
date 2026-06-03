"""Interactive Brokers access — READ ONLY.

This module deliberately uses *only* read methods of the IB API (`portfolio`,
`positions`, `accountSummary`). It never imports `Order` or calls `placeOrder`, and it
must stay that way: investbot is advisory and does not execute trades. A safety test
asserts no order-execution symbols appear here.

`get_portfolio` is the single boundary the rest of the app uses; it returns a validated
`Portfolio` from either a live IB connection or a mock fixture.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from investbot.config.loader import fixture_path
from investbot.models.portfolio import Portfolio, Position
from investbot.models.recommendation import AppConfig


class BrokerError(Exception):
    """Raised when portfolio data cannot be obtained."""


class ConnectionInfo(BaseModel):
    """Result of a lightweight, read-only IBKR connection probe."""

    host: str
    port: int
    client_id: int
    connected: bool = False
    server_version: int | None = None
    accounts: list[str] = []
    num_positions: int = 0


def get_portfolio(source: str, config: AppConfig) -> Portfolio:
    """Return the current portfolio from `live` IBKR or a `mock` fixture."""
    source = source.lower()
    if source == "mock":
        return load_mock_portfolio(config)
    if source == "live":
        return load_live_portfolio(config)
    raise BrokerError(f"Unknown source {source!r}; expected 'live' or 'mock'.")


# --- Mock -----------------------------------------------------------------

def load_mock_portfolio(config: AppConfig, name: str = "sample_portfolio.json") -> Portfolio:
    path: Path = fixture_path(config, name)
    if not path.exists():
        raise BrokerError(f"Mock portfolio fixture not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BrokerError(f"Invalid JSON in fixture {path}: {exc}") from exc
    return Portfolio.model_validate(data)


# --- Live (read-only) -----------------------------------------------------

def load_live_portfolio(config: AppConfig) -> Portfolio:
    """Connect to TWS/IB Gateway and read positions + cash. Never places orders."""
    ib = _connect(config)
    try:
        account_values = ib.accountSummary()
        cash = _extract_cash(account_values, config.ibkr)
        account_id = _extract_account_id(account_values)
        positions = [_to_position(item) for item in ib.portfolio()]
        return Portfolio(
            account_id=account_id,
            base_currency="USD",
            cash=cash,
            positions=[p for p in positions if p is not None],
        )
    finally:
        try:
            ib.disconnect()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def probe_connection(config: AppConfig) -> ConnectionInfo:
    """Connect read-only and report basic account info, then disconnect.

    Used by the interactive `connect` command to verify TWS/Gateway reachability
    without pulling the full portfolio. Reads only; never places orders.
    """
    ibc = config.ibkr
    ib = _connect(config)
    try:
        accounts = [a for a in (ib.managedAccounts() or []) if a]
        server_version = None
        try:
            server_version = ib.client.serverVersion()
        except Exception:  # pragma: no cover - version call is best-effort
            pass
        num_positions = 0
        try:
            num_positions = len(ib.positions() or [])
        except Exception:  # pragma: no cover - positions sub may be unavailable
            num_positions = 0
        return ConnectionInfo(
            host=ibc.host,
            port=ibc.port,
            client_id=ibc.client_id,
            connected=True,
            server_version=server_version,
            accounts=accounts,
            num_positions=num_positions,
        )
    finally:
        try:
            ib.disconnect()
        except Exception:  # pragma: no cover - best-effort cleanup
            pass


def _connect(config: AppConfig):
    """Lazily import ib_insync and connect.

    ib_insync's dependency (eventkit) touches asyncio at import time, which breaks on
    newer Pythons unless an event loop is set first; we set one defensively. Importing
    lazily also keeps `mock` mode and the rest of the CLI working even if ib_insync is
    unavailable in the current environment.
    """
    import asyncio

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        from ib_insync import IB
    except Exception as exc:  # pragma: no cover - environment dependent
        raise BrokerError(
            "ib_insync could not be imported in this environment. Use --source mock, or "
            f"run on a supported Python with ib_insync installed. ({exc})"
        ) from exc

    ib = IB()
    ibc = config.ibkr
    try:
        ib.connect(ibc.host, ibc.port, clientId=ibc.client_id, timeout=ibc.timeout_seconds)
    except Exception as exc:
        raise BrokerError(
            f"Could not connect to IBKR at {ibc.host}:{ibc.port} (clientId={ibc.client_id}). "
            "Is TWS or IB Gateway running with the API enabled on that port? "
            f"({exc})"
        ) from exc
    return ib


def _extract_cash(account_values, ibc) -> float:
    """Pull TotalCashValue (base currency) from accountSummary rows."""
    for av in account_values:
        if getattr(av, "tag", None) == "TotalCashValue":
            currency = getattr(av, "currency", "") or ""
            if currency in ("", "BASE", "USD"):
                try:
                    return float(av.value)
                except (TypeError, ValueError):
                    continue
    return 0.0


def _extract_account_id(account_values) -> str | None:
    for av in account_values:
        acct = getattr(av, "account", None)
        if acct:
            return acct
    return None


def _to_position(item) -> Position | None:
    """Map an ib_insync PortfolioItem to our Position, skipping non-equity holdings."""
    contract = item.contract
    sec_type = getattr(contract, "secType", "STK")
    # Advisory MVP supports long equities only; ignore options/futures/etc.
    if sec_type not in ("STK", "ETF"):
        return None
    return Position(
        ticker=getattr(contract, "symbol", "") or "",
        name=getattr(contract, "localSymbol", None) or None,
        quantity=float(item.position),
        avg_cost=float(getattr(item, "averageCost", 0.0) or 0.0),
        market_price=float(getattr(item, "marketPrice", 0.0) or 0.0),
        sector=None,  # backfilled by data_sources.market when needed
        asset_class=sec_type,
    )
