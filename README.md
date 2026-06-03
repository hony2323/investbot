# investbot

A read-only, **advisory** CLI investing assistant. It connects to your Interactive Brokers
portfolio, applies your personal taste/risk rules, and uses Claude to produce a structured
investment memo with per-holding recommendations.

> ⚠️ **investbot does not place trades.** It has no order-execution code paths. Every output is a
> *recommendation only* and is **not financial advice**. No options or margin support.

## What it does

- Reads your IBKR portfolio (or a mock fixture) and prints a summary.
- Computes deterministic risk metrics locally (position %, sector %, cash %, rule breaches).
- Asks Claude — acting as a conservative analyst — for a recommendation per holding
  (`BUY / HOLD / WATCH / TRIM / SELL`), always weighed against doing nothing or buying a broad ETF.
- Writes a dated markdown memo and a JSONL history of recommendations.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # then fill in ANTHROPIC_API_KEY
```

`ib_insync` requires a running **TWS** or **IB Gateway** with the API enabled
(TWS → Settings → API → Enable ActiveX and Socket Clients; port `7497` for paper).
You can do everything except live IBKR reads with `--source mock`.

## Usage

```bash
investbot portfolio --source mock        # render the sample portfolio + risk report
investbot portfolio --source live        # read your real IBKR account
investbot analyze --source mock          # full memo (needs ANTHROPIC_API_KEY)
investbot analyze --source mock --dry-run  # build prompt, skip Claude (free)
investbot stock AAPL                      # analyze a single ticker
investbot taste                           # show your taste profile
investbot edit-taste                      # edit taste.yaml in $EDITOR
```

## Files

- `config.yaml` — model, IB connection, paths.
- `taste.yaml` — your risk rules and likes/avoids.
- `data/snapshots/YYYY-MM-DD_portfolio.json` — daily portfolio snapshots.
- `data/memos/YYYY-MM-DD_memo.md` — generated memos.
- `data/recommendations.jsonl` — append-only recommendation history.

## Disclaimer

investbot is a personal research tool. It produces opinions, not orders, and not financial advice.
Always do your own due diligence.
