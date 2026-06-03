# investbot (core)

The `investbot` library + CLI: the read-only, **advisory** investing engine. It connects to
your Interactive Brokers portfolio, applies your personal taste/risk rules, and uses Claude to
produce a structured investment memo with per-holding recommendations.

> ⚠️ **investbot does not place trades.** It has no order-execution code paths. Every output is a
> *recommendation only* and is **not financial advice**. No options or margin support.

This package is consumed two ways:

- directly as a CLI (`investbot ...`), and
- imported by the FastAPI service in `apps/api`, which powers the web UI.

## What it does

- Reads your IBKR portfolio (or a mock fixture) and prints a summary.
- Computes deterministic risk metrics locally (position %, sector %, cash %, rule breaches).
- Asks Claude — acting as a conservative analyst — for a recommendation per holding
  (`BUY / HOLD / WATCH / TRIM / SELL`), always weighed against doing nothing or buying a broad ETF.
- Writes a dated markdown memo and a JSONL history of recommendations.

## Install (standalone)

From the repo root the workspace install (`make install` / `uv sync`) covers this. To install
just the core package on its own:

```bash
uv pip install -e "packages/core[dev]"
```

## Configure secrets

```bash
cp packages/core/.env.example packages/core/.env   # fill in ANTHROPIC_API_KEY (and IB_* for live)
```

`.env` is git-ignored. App settings (model, paths, IB host/port) live in
`packages/core/config.yaml`; your investing rules live in `packages/core/taste.yaml`. All paths
are resolved relative to this package directory, so the CLI and API behave identically regardless
of where they're launched from.

## Usage

```bash
investbot connect                          # interactively test the TWS/Gateway connection
investbot portfolio --source mock          # render the sample portfolio + risk report
investbot portfolio --source live          # read your real IBKR account
investbot analyze --source mock            # full memo (needs ANTHROPIC_API_KEY)
investbot analyze --source mock --dry-run  # build prompt, skip Claude (free)
investbot stock AAPL                        # analyze a single ticker
investbot taste                            # show your taste profile
investbot edit-taste                       # edit taste.yaml in $EDITOR
```

## Tests

```bash
pytest packages/core            # from the repo root
# or: cd packages/core && pytest
```

## Files (under `packages/core/`)

- `config.yaml` — model, IB connection, paths.
- `taste.yaml` — your risk rules and likes/avoids.
- `data/snapshots/YYYY-MM-DD_portfolio.json` — daily portfolio snapshots.
- `data/memos/YYYY-MM-DD_memo.md` — generated memos.
- `data/recommendations.jsonl` — append-only recommendation history.

## Live IBKR setup (optional)

Live mode needs **TWS** or **IB Gateway** running with the API enabled:
TWS → *Settings → API → Settings* → enable **ActiveX and Socket Clients**, and confirm the
socket port (`7497` for paper, `7496` for live) matches `config.yaml` / `IB_PORT`. Then:

```bash
investbot connect                  # prompts for host/port/client id, then probes (read-only)
investbot connect --no-input       # skip prompts; use configured values
investbot portfolio --source live  # once connect succeeds
```

> **Python 3.14 note:** `ib_insync` (via `eventkit`) touches a removed asyncio API at import
> time, so live IBKR is smoothest on Python 3.11–3.13. Mock mode and all other commands are
> unaffected.
