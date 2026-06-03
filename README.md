# investbot

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-32%20passing-brightgreen)
![Mode](https://img.shields.io/badge/mode-read--only%20%C2%B7%20no%20trades-orange)
![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude-8A2BE2)

A read-only, **advisory** investing assistant. It reads your Interactive Brokers portfolio,
applies your personal taste/risk rules, and uses Claude to produce structured, per-holding
recommendations — available as a **CLI**, an **HTTP API**, and a **web dashboard**.

> ⚠️ **investbot does not place trades.** No output is ever an order, and there are no
> order-execution code paths. Recommendations only — **not financial advice**.

## Monorepo layout

```
investobot/
├── packages/
│   └── core/        # the `investbot` library + CLI (analysis, brokers, models, config, tests)
└── apps/
    ├── api/         # FastAPI service wrapping the core library (investbot_api)
    └── web/         # React + Vite + TypeScript dashboard
```

The core library is the single source of truth; the API is a thin wrapper that returns the
same Pydantic models the CLI uses, and the web app renders them. See each package's README
for details: [`packages/core`](packages/core/README.md) ·
[`apps/api`](apps/api/README.md) · [`apps/web`](apps/web/README.md).

## Quick start

Requires [`uv`](https://docs.astral.sh/uv/) (Python) and Node 18+ (web).

```bash
make install            # uv sync (core + api) and npm install (web)
make test               # run the core test suite
```

Run the stack (two terminals, or `make dev` for both):

```bash
make api                # FastAPI on http://localhost:8000  (docs at /docs)
make web                # Vite dev server on http://localhost:5173
```

Open **http://localhost:5173** — the dashboard loads the bundled mock portfolio with its risk
checks. **No API key is needed** for the mock dashboard, `/api/health`, or `/api/taste`.

### Configure secrets (for live data / Claude analysis)

```bash
cp packages/core/.env.example packages/core/.env   # add ANTHROPIC_API_KEY (and IB_* for live)
```

`analyze`/`stock` (CLI) and `/api/analyze` · `/api/stock/{ticker}` (API) need
`ANTHROPIC_API_KEY`; live IBKR additionally needs a running TWS/IB Gateway. Everything else
works offline with `source=mock`.

## CLI

After `make install` the `investbot` command is available:

```bash
investbot portfolio --source mock          # render the sample portfolio + risk report
investbot analyze --source mock --dry-run  # build the prompt without calling Claude (free)
investbot taste                            # show your taste profile
```

Full command reference: [`packages/core/README.md`](packages/core/README.md).

## API endpoints

| Method | Path                     | Auth needed | Notes                              |
| ------ | ------------------------ | ----------- | ---------------------------------- |
| GET    | `/api/health`            | no          | liveness check                     |
| GET    | `/api/taste`             | no          | current taste profile              |
| GET    | `/api/portfolio?source=` | mock: no    | summary + risk (`mock` or `live`)  |
| GET    | `/api/stock/{ticker}`    | yes         | single-ticker recommendation       |
| POST   | `/api/analyze`           | unless dry  | full memo (`{source, dry_run}`)    |

## Disclaimer

investbot is a personal research tool. It produces opinions, not orders, and not financial
advice. Always do your own due diligence.
