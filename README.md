# investbot

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-29%20passing-brightgreen)
![Mode](https://img.shields.io/badge/mode-read--only%20%C2%B7%20no%20trades-orange)
![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude-8A2BE2)

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

## Project setup

### Requirements

- **Python 3.10–3.13** recommended. (Python 3.14 works for everything *except* live IBKR —
  see the note below.)
- An **Anthropic API key** for `analyze` and `stock`.
- For live mode only: a running **TWS** or **IB Gateway** instance.

### 1. Get the code

```bash
git clone https://github.com/hony2323/investbot.git
cd investbot
```

### 2. Create a virtual environment and install

Using [`uv`](https://docs.astral.sh/uv/) (fast, and works even where `python -m venv` can't
bootstrap pip):

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

Or with stock `pip`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Configure secrets

```bash
cp .env.example .env      # then fill in ANTHROPIC_API_KEY (and IB_* if using live mode)
```

`.env` is git-ignored and never committed. App settings (model, paths, IB host/port) live in
`config.yaml`; your investing rules live in `taste.yaml`.

### 4. Verify the install

```bash
pytest -q                                  # 29 tests, fully offline
investbot taste                            # render your taste profile
investbot portfolio --source mock          # render the bundled sample portfolio
investbot analyze --source mock --dry-run  # build the prompt without calling Claude (free)
```

If those work, you're set. `analyze` and `stock` (without `--dry-run`) additionally need
`ANTHROPIC_API_KEY` in `.env`.

### Live IBKR setup (optional)

Live mode needs **TWS** or **IB Gateway** running with the API enabled:
TWS → *Settings → API → Settings* → enable **ActiveX and Socket Clients**, and confirm the
socket port (`7497` for paper, `7496` for live) matches `config.yaml` / `IB_PORT`. Then
verify the link before pulling holdings:

```bash
investbot connect                  # prompts for host/port/client id, then probes (read-only)
investbot connect --no-input       # skip prompts; use configured values
investbot portfolio --source live  # once connect succeeds
```

`connect` only reads (`managedAccounts` / `positions`) and disconnects; on failure it prints
a checklist of the usual causes (API disabled, wrong port, untrusted IP, client-id clash).

Everything except live reads works offline with `--source mock`.

> **Python 3.14 note:** `ib_insync` (via `eventkit`) touches a removed asyncio API at import
> time, so it only imports on 3.14 with a pre-set event loop. investbot applies that workaround
> automatically in the live path, but for live IBKR use the smoothest experience is Python
> 3.11–3.13. Mock mode and all other commands are unaffected.

## Usage

```bash
investbot connect                        # interactively test the TWS/Gateway connection
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
