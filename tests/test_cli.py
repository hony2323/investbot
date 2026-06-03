"""End-to-end CLI tests via Typer's CliRunner. All offline.

A temporary config/taste/fixture is written under tmp_path so tests never touch the real
data/ directory. The full `analyze` path is exercised with a fake Claude client.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from investbot import cli
from investbot.analysis.claude import ClaudeClient
from investbot.models.recommendation import ClaudeConfig
from tests.conftest import FakeAnthropic, _default_tool_input

runner = CliRunner()


@pytest.fixture
def project(tmp_path, sample_portfolio_dict) -> dict:
    """Write a self-contained config/taste/fixture tree and return their paths."""
    (tmp_path / "snapshots").mkdir()
    (tmp_path / "memos").mkdir()
    fixtures = tmp_path / "fixtures"
    fixtures.mkdir()
    (fixtures / "sample_portfolio.json").write_text(json.dumps(sample_portfolio_dict))

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "claude": {"model": "claude-opus-4-8"},
                "ibkr": {"host": "127.0.0.1", "port": 7497, "client_id": 1},
                "data": {
                    "default_source": "mock",
                    "snapshots_dir": str(tmp_path / "snapshots"),
                    "memos_dir": str(tmp_path / "memos"),
                    "fixtures_dir": str(fixtures),
                    "recommendations_file": str(tmp_path / "recommendations.jsonl"),
                },
                "analysis": {"max_positions": 30, "benchmark_etf": "VOO"},
            }
        )
    )

    taste_path = tmp_path / "taste.yaml"
    taste_path.write_text(
        yaml.safe_dump(
            {
                "risk": {
                    "max_single_position_pct": 15,
                    "max_sector_pct": 45,
                    "min_cash_pct": 5,
                    "allow_options": False,
                    "allow_margin": False,
                },
                "preferences": {"likes": ["strong moats"], "avoids": ["meme stocks"]},
            }
        )
    )
    return {
        "config": str(config_path),
        "taste": str(taste_path),
        "tmp": tmp_path,
    }


def test_taste_command(project):
    result = runner.invoke(cli.app, ["taste", "--taste", project["taste"]])
    assert result.exit_code == 0
    assert "Risk rules" in result.stdout
    assert "strong moats" in result.stdout


def test_portfolio_command_writes_snapshot(project):
    result = runner.invoke(
        cli.app,
        ["portfolio", "--source", "mock", "--config", project["config"], "--taste", project["taste"]],
    )
    assert result.exit_code == 0, result.stdout
    assert "MSFT" in result.stdout
    snaps = list((project["tmp"] / "snapshots").glob("*_portfolio.json"))
    assert len(snaps) == 1


def test_analyze_dry_run_no_claude(project):
    result = runner.invoke(
        cli.app,
        ["analyze", "--source", "mock", "--config", project["config"],
         "--taste", project["taste"], "--dry-run"],
    )
    assert result.exit_code == 0, result.stdout
    assert "DRY RUN" in result.stdout
    # Snapshot written, but no memo produced.
    assert list((project["tmp"] / "snapshots").glob("*.json"))
    assert not list((project["tmp"] / "memos").glob("*.md"))


def test_analyze_full_path_with_fake_claude(project, monkeypatch):
    """Patch the Claude client + API key so analyze runs fully offline."""
    monkeypatch.setattr(cli, "get_anthropic_api_key", lambda: "test-key")

    def _fake_client(taste, claude_cfg, benchmark, api_key=None):
        fake = FakeAnthropic(
            tool_inputs=[
                _default_tool_input(ticker="MSFT", action="TRIM"),
                _default_tool_input(ticker="CRWD", action="HOLD"),
                _default_tool_input(ticker="NEE", action="HOLD"),
            ],
            memo_text="# Memo\nBottom line: trim concentration.",
        )
        return ClaudeClient(taste, ClaudeConfig(), benchmark, client=fake)

    monkeypatch.setattr(cli, "ClaudeClient", _fake_client)

    result = runner.invoke(
        cli.app,
        ["analyze", "--source", "mock", "--config", project["config"],
         "--taste", project["taste"], "--no-market"],
    )
    assert result.exit_code == 0, result.stdout
    # Memo written.
    memos = list((project["tmp"] / "memos").glob("*_memo.md"))
    assert len(memos) == 1
    memo_text = memos[0].read_text()
    assert "Recommendations" in memo_text
    assert "advisory only" in memo_text.lower()
    # Recommendations appended to history.
    rec_file = Path(project["tmp"] / "recommendations.jsonl")
    lines = [l for l in rec_file.read_text().splitlines() if l.strip()]
    assert len(lines) == 3
    row = json.loads(lines[0])
    assert row["command"] == "analyze"
    assert row["action"] in {"BUY", "HOLD", "WATCH", "TRIM", "SELL"}


def test_connect_success(project, monkeypatch):
    from investbot.brokers.ibkr import ConnectionInfo

    def _fake_probe(config):
        return ConnectionInfo(
            host=config.ibkr.host,
            port=config.ibkr.port,
            client_id=config.ibkr.client_id,
            connected=True,
            server_version=176,
            accounts=["DU0000001"],
            num_positions=3,
        )

    monkeypatch.setattr(cli, "probe_connection", _fake_probe)
    result = runner.invoke(
        cli.app, ["connect", "--config", project["config"], "--no-input"]
    )
    assert result.exit_code == 0, result.stdout
    assert "Connected" in result.stdout
    assert "DU0000001" in result.stdout


def test_connect_failure_gives_guidance(project, monkeypatch):
    from investbot.brokers.ibkr import BrokerError

    def _boom(config):
        raise BrokerError("Could not connect to IBKR at 127.0.0.1:7497")

    monkeypatch.setattr(cli, "probe_connection", _boom)
    result = runner.invoke(
        cli.app, ["connect", "--config", project["config"], "--no-input"]
    )
    assert result.exit_code == 1
    assert "Connection failed" in result.stdout
    assert "Checklist" in result.stdout


def test_connect_flag_overrides(project, monkeypatch):
    captured = {}

    def _fake_probe(config):
        from investbot.brokers.ibkr import ConnectionInfo

        captured["host"] = config.ibkr.host
        captured["port"] = config.ibkr.port
        captured["client_id"] = config.ibkr.client_id
        return ConnectionInfo(
            host=config.ibkr.host, port=config.ibkr.port,
            client_id=config.ibkr.client_id, connected=True,
        )

    monkeypatch.setattr(cli, "probe_connection", _fake_probe)
    result = runner.invoke(
        cli.app,
        ["connect", "--config", project["config"], "--no-input",
         "--host", "10.0.0.5", "--port", "4002", "--client-id", "9"],
    )
    assert result.exit_code == 0, result.stdout
    assert captured == {"host": "10.0.0.5", "port": 4002, "client_id": 9}


def test_stock_command_with_fake_claude(project, monkeypatch):
    monkeypatch.setattr(cli, "get_anthropic_api_key", lambda: "test-key")
    # Avoid network: stub fundamentals.
    from investbot.data_sources.market import StockFacts

    monkeypatch.setattr(
        "investbot.analysis.stock.get_stock_facts",
        lambda t: StockFacts(ticker=t.upper(), name="Test Co", sector="Technology"),
    )
    monkeypatch.setattr("investbot.analysis.stock.get_recent_headlines", lambda t: [])

    def _fake_client(taste, claude_cfg, benchmark, api_key=None):
        fake = FakeAnthropic(tool_inputs=[_default_tool_input(ticker="AAPL", action="WATCH")])
        return ClaudeClient(taste, ClaudeConfig(), benchmark, client=fake)

    monkeypatch.setattr(cli, "ClaudeClient", _fake_client)

    result = runner.invoke(
        cli.app,
        ["stock", "AAPL", "--config", project["config"], "--taste", project["taste"]],
    )
    assert result.exit_code == 0, result.stdout
    assert "AAPL" in result.stdout
    assert "WATCH" in result.stdout
