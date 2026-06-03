# investbot-web

React + Vite + TypeScript frontend for investbot. The dashboard reads
`/api/portfolio?source=mock` (proxied to the FastAPI service) and renders the portfolio
summary, positions, sector exposure, and risk checks — no API key needed.

```bash
npm install
npm run dev      # http://localhost:5173 (needs the API running on :8000 — see repo root)
```
