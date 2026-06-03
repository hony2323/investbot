"""investbot command-line interface.

Five commands: portfolio, analyze, stock, taste, edit-taste. Rendering uses Rich.
investbot is advisory and never executes trades.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from investbot.analysis import portfolio as port
from investbot.analysis.claude import ClaudeClient, ClaudeError
from investbot.analysis.risk import build_risk_report
from investbot.analysis.stock import analyze_stock
from investbot.brokers.ibkr import BrokerError, get_portfolio, probe_connection
from investbot.config.loader import (
    ConfigError,
    get_anthropic_api_key,
    load_config,
    load_taste,
    taste_path,
)
from investbot.models.portfolio import Portfolio, RiskReport
from investbot.models.recommendation import (
    AppConfig,
    MemoResult,
    Recommendation,
    TasteProfile,
)

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Read-only, advisory investing assistant. Recommends — never trades.",
)

console = Console()
err_console = Console(stderr=True)

_ACTION_STYLE = {
    "BUY": "bold green",
    "HOLD": "cyan",
    "WATCH": "yellow",
    "TRIM": "magenta",
    "SELL": "bold red",
}
_SEVERITY_STYLE = {"info": "blue", "warn": "yellow", "breach": "bold red"}


# --- helpers --------------------------------------------------------------

def _money(x: float, currency: str = "USD") -> str:
    sym = "$" if currency == "USD" else ""
    return f"{sym}{x:,.2f}"


def _fail(message: str) -> None:
    err_console.print(f"[bold red]Error:[/] {message}")
    raise typer.Exit(code=1)


def _load(config_path: Optional[str], taste_path_opt: Optional[str]) -> tuple[AppConfig, TasteProfile]:
    try:
        config = load_config(config_path)
        taste = load_taste(taste_path_opt)
    except ConfigError as exc:
        _fail(str(exc))
    return config, taste  # type: ignore[return-value]


def _resolve_source(source: Optional[str], config: AppConfig) -> str:
    src = (source or config.data.default_source).lower()
    if src not in ("live", "mock"):
        _fail(f"--source must be 'live' or 'mock', got {src!r}")
    return src


def _fetch_portfolio(source: str, config: AppConfig) -> Portfolio:
    try:
        return get_portfolio(source, config)
    except BrokerError as exc:
        _fail(str(exc))
        raise  # unreachable; satisfies type-checkers


# --- rendering ------------------------------------------------------------

def _render_portfolio(portfolio: Portfolio, risk: RiskReport) -> None:
    summary = port.summarize(portfolio)
    cur = portfolio.base_currency

    table = Table(title="Positions", header_style="bold")
    table.add_column("Ticker", style="bold")
    table.add_column("Name")
    table.add_column("Qty", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Mkt Value", justify="right")
    table.add_column("Weight %", justify="right")
    table.add_column("Unreal. P&L", justify="right")
    table.add_column("Sector")
    for p in summary.top_positions:
        pnl_style = "green" if p.unrealized_pnl >= 0 else "red"
        table.add_row(
            p.ticker,
            (p.name or "")[:22],
            f"{p.quantity:g}",
            _money(p.market_price, cur),
            _money(p.market_value, cur),
            f"{p.weight_pct:.1f}",
            Text(f"{_money(p.unrealized_pnl, cur)} ({p.unrealized_pnl_pct:.1f}%)", style=pnl_style),
            p.sector or "—",
        )
    console.print(table)

    summary_lines = [
        f"Account: {portfolio.account_id or 'n/a'}",
        f"As of: {portfolio.as_of.isoformat(timespec='seconds')}",
        f"Total value: {_money(summary.total_value, cur)}",
        f"Invested: {_money(summary.invested_value, cur)}",
        f"Cash: {_money(summary.cash, cur)} ({summary.cash_pct:.1f}%)",
        f"Positions: {summary.position_count}",
    ]
    console.print(Panel("\n".join(summary_lines), title="Summary", expand=False))

    if summary.sector_weights:
        st = Table(title="Sector exposure", header_style="bold")
        st.add_column("Sector")
        st.add_column("Weight %", justify="right")
        for sw in summary.sector_weights:
            st.add_row(sw.sector, f"{sw.weight_pct:.1f}")
        console.print(st)

    _render_violations(risk)


def _render_violations(risk: RiskReport) -> None:
    if not risk.violations:
        console.print("[green]✓ No risk-rule violations.[/]")
        return
    table = Table(title="Risk-rule checks", header_style="bold")
    table.add_column("Severity")
    table.add_column("Rule")
    table.add_column("Detail")
    for v in risk.violations:
        style = _SEVERITY_STYLE.get(v.severity, "white")
        table.add_row(Text(v.severity.upper(), style=style), v.rule, v.detail)
    console.print(table)


def _render_recommendation(rec: Recommendation) -> None:
    style = _ACTION_STYLE.get(rec.action, "white")
    body = [
        Text.assemble(("Action: ", "bold"), (rec.action, style),
                      (f"   Confidence: {rec.confidence:.2f}", "dim")),
        Text(f"Time horizon: {rec.time_horizon}"),
        Text(f"Suggested size: {rec.suggested_position_size}"),
        Text(""),
        Text.assemble(("Reason: ", "bold"), (rec.reason, "")),
    ]
    if rec.risks:
        body.append(Text(""))
        body.append(Text("Risks:", style="bold"))
        for r in rec.risks:
            body.append(Text(f"  • {r}"))
    body.append(Text(""))
    body.append(Text.assemble(("What would change my mind: ", "bold"),
                              (rec.what_would_change_my_mind, "")))
    panel = Panel(
        Text("\n").join(_flatten(body)),
        title=f"{rec.ticker} — recommendation",
        border_style=style,
    )
    console.print(panel)


def _flatten(items):
    out = []
    for it in items:
        out.append(it if isinstance(it, Text) else Text(str(it)))
    return out


# --- commands -------------------------------------------------------------

@app.command()
def portfolio(
    source: Optional[str] = typer.Option(None, help="Data source: live | mock."),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml."),
    taste_file: Optional[str] = typer.Option(None, "--taste", help="Path to taste.yaml."),
) -> None:
    """Connect to IBKR (or mock) and print the current portfolio summary."""
    config, taste = _load(config_path, taste_file)
    src = _resolve_source(source, config)
    pf = _fetch_portfolio(src, config)
    risk = build_risk_report(pf, taste)
    _render_portfolio(pf, risk)
    snap = port.write_snapshot(pf, config)
    console.print(f"[dim]Snapshot saved → {snap}[/]")


@app.command()
def connect(
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml."),
    host: Optional[str] = typer.Option(None, help="Override IBKR host."),
    port: Optional[int] = typer.Option(None, help="Override IBKR port."),
    client_id: Optional[int] = typer.Option(None, help="Override IBKR client id."),
    no_input: bool = typer.Option(
        False, "--no-input", help="Skip prompts; use configured/flag values."
    ),
) -> None:
    """Interactively test the connection to TWS / IB Gateway (read-only)."""
    try:
        config = load_config(config_path)
    except ConfigError as exc:
        _fail(str(exc))

    ibc = config.ibkr
    h = host or ibc.host
    p = port if port is not None else ibc.port
    cid = client_id if client_id is not None else ibc.client_id

    if not no_input:
        console.print(
            "[dim]Make sure TWS or IB Gateway is running and the API is enabled "
            "(Settings → API → Enable ActiveX and Socket Clients).[/]"
        )
        h = typer.prompt("IBKR host", default=h)
        p = int(typer.prompt("IBKR port", default=str(p)))
        cid = int(typer.prompt("Client id", default=str(cid)))

    config.ibkr.host, config.ibkr.port, config.ibkr.client_id = h, p, cid
    console.print(
        Panel(f"Connecting to [bold]{h}:{p}[/] (client id {cid})…", border_style="cyan", expand=False)
    )

    try:
        with console.status("[bold]Contacting IBKR…[/]"):
            info = probe_connection(config)
    except BrokerError as exc:
        console.print(f"[bold red]Connection failed:[/] {exc}")
        console.print(
            "\n[bold]Checklist:[/]\n"
            "  • Is TWS or IB Gateway running and logged in?\n"
            "  • API enabled? Settings → API → 'Enable ActiveX and Socket Clients'.\n"
            f"  • Does the socket port match? (you tried {p}; paper=7497, live=7496)\n"
            "  • Is 127.0.0.1 in API → 'Trusted IPs' (or accept the TWS prompt)?\n"
            "  • Is another client using the same client id? Try a different one."
        )
        raise typer.Exit(code=1)

    lines = [
        "[green]✓ Connected[/]",
        f"Host: {info.host}:{info.port} (client id {info.client_id})",
        f"Server version: {info.server_version or 'n/a'}",
        f"Accounts: {', '.join(info.accounts) or 'none reported'}",
        f"Open positions: {info.num_positions}",
    ]
    console.print(Panel("\n".join(lines), title="IBKR connection", border_style="green", expand=False))
    console.print("[dim]Read-only check complete. Run `investbot portfolio --source live` to view holdings.[/]")


@app.command()
def analyze(
    source: Optional[str] = typer.Option(None, help="Data source: live | mock."),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml."),
    taste_file: Optional[str] = typer.Option(None, "--taste", help="Path to taste.yaml."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build prompts but do not call Claude."),
    max_positions: Optional[int] = typer.Option(None, help="Cap holdings analyzed."),
    no_market: bool = typer.Option(False, "--no-market", help="Skip yfinance fundamentals."),
) -> None:
    """Fetch the portfolio, apply taste/risk rules, and generate an investment memo."""
    config, taste = _load(config_path, taste_file)
    src = _resolve_source(source, config)
    pf = _fetch_portfolio(src, config)
    snap = port.write_snapshot(pf, config)
    console.print(f"[dim]Snapshot saved → {snap}[/]")

    risk = build_risk_report(pf, taste)
    _render_violations(risk)

    cap = max_positions or config.analysis.max_positions
    holdings = pf.positions[:cap]

    if dry_run:
        from investbot.analysis import prompt_builder as pb

        console.print(Panel("[bold]DRY RUN[/] — no Claude calls will be made.", border_style="yellow"))
        console.print(Panel(pb.system_prompt(taste, config.analysis.benchmark_etf),
                            title="System prompt", expand=False))
        if holdings:
            example = pb.holding_user_prompt(
                holdings[0], None, pf, risk, config.analysis.benchmark_etf
            )
            console.print(Panel(example, title=f"Example holding prompt ({holdings[0].ticker})",
                                expand=False))
        console.print(f"[dim]Would analyze {len(holdings)} holding(s).[/]")
        return

    api_key = get_anthropic_api_key()
    try:
        client = ClaudeClient(taste, config.claude, config.analysis.benchmark_etf, api_key=api_key)
    except ClaudeError as exc:
        _fail(str(exc))

    recs: list[Recommendation] = []
    invalid: list[str] = []
    with console.status("[bold]Analyzing holdings with Claude…[/]"):
        for pos in holdings:
            facts = None
            if not no_market:
                from investbot.data_sources.market import get_stock_facts

                facts = get_stock_facts(pos.ticker)
            try:
                rec = client.recommend_for_holding(pos, facts, pf, risk)
                recs.append(rec)
            except ClaudeError:
                invalid.append(pos.ticker)

    memo_md = ""
    if recs:
        try:
            memo_md = client.synthesize_memo(recs, pf, risk)
        except ClaudeError as exc:
            console.print(f"[yellow]Memo narrative unavailable: {exc}[/]")

    result = MemoResult(
        model=config.claude.model,
        account_id=pf.account_id,
        benchmark_etf=config.analysis.benchmark_etf,
        recommendations=recs,
        invalid_tickers=invalid,
        memo_markdown=memo_md,
        risk_report=risk,
    )

    for rec in recs:
        _render_recommendation(rec)
    if invalid:
        console.print(f"[yellow]Skipped (invalid model output): {', '.join(invalid)}[/]")

    memo_file = port.write_memo(result, config)
    port.append_recommendations(recs, config, command="analyze", account_id=pf.account_id)
    console.print(f"[green]Memo saved → {memo_file}[/]")


@app.command()
def stock(
    ticker: str = typer.Argument(..., help="Ticker symbol, e.g. AAPL."),
    config_path: Optional[str] = typer.Option(None, "--config", help="Path to config.yaml."),
    taste_file: Optional[str] = typer.Option(None, "--taste", help="Path to taste.yaml."),
) -> None:
    """Analyze a single stock according to your taste/risk profile."""
    config, taste = _load(config_path, taste_file)
    api_key = get_anthropic_api_key()
    try:
        client = ClaudeClient(taste, config.claude, config.analysis.benchmark_etf, api_key=api_key)
    except ClaudeError as exc:
        _fail(str(exc))

    with console.status(f"[bold]Analyzing {ticker.upper()}…[/]"):
        try:
            rec, facts = analyze_stock(ticker, client)
        except ClaudeError as exc:
            _fail(str(exc))
            return
    if getattr(facts, "error", None):
        console.print(f"[yellow]Note: {facts.error}[/]")
    _render_recommendation(rec)
    port.append_recommendations([rec], config, command="stock")


@app.command()
def taste(
    taste_file: Optional[str] = typer.Option(None, "--taste", help="Path to taste.yaml."),
) -> None:
    """Show your current investing taste profile."""
    try:
        profile = load_taste(taste_file)
    except ConfigError as exc:
        _fail(str(exc))

    r = profile.risk
    rt = Table(title="Risk rules", header_style="bold")
    rt.add_column("Rule")
    rt.add_column("Value", justify="right")
    rt.add_row("Max single position %", f"{r.max_single_position_pct:.0f}")
    rt.add_row("Max sector %", f"{r.max_sector_pct:.0f}")
    rt.add_row("Min cash %", f"{r.min_cash_pct:.0f}")
    rt.add_row("Allow options", str(r.allow_options))
    rt.add_row("Allow margin", str(r.allow_margin))
    console.print(rt)

    likes = "\n".join(f"  • {x}" for x in profile.preferences.likes) or "  (none)"
    avoids = "\n".join(f"  • {x}" for x in profile.preferences.avoids) or "  (none)"
    console.print(Panel(likes, title="Likes", border_style="green", expand=False))
    console.print(Panel(avoids, title="Avoids", border_style="red", expand=False))


@app.command(name="edit-taste")
def edit_taste(
    taste_file: Optional[str] = typer.Option(None, "--taste", help="Path to taste.yaml."),
) -> None:
    """Open the taste profile in $EDITOR and re-validate on save."""
    path = taste_path(taste_file)
    if not path.exists():
        _fail(f"Taste file not found: {path}")
    typer.launch(str(path), wait=True)
    try:
        load_taste(taste_file)
    except ConfigError as exc:
        _fail(f"Saved file is invalid (left unchanged on disk):\n{exc}")
    console.print(f"[green]✓ Taste profile valid → {path}[/]")


if __name__ == "__main__":
    app()
