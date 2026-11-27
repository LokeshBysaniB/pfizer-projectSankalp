# Project Sankalp — Pfizer GM channel pilot

Fictional **FDE Academy** case. **Private repository** — do not make public.

LangGraph assistant for Pfizer Limited General Medicines trade channel:

1. **Scheme cap** (CO-POL-014 §4.4) — free goods at PTS ≤ 3% of quarter primary sales (routes A & B).
2. **Expiry claim window** (claims policy §5.2) — 90-day rules for near-expiry and expired claims (routes C & D).

The model only **routes** and **explains**; every number comes from tested Python tools reading prepared CSVs. **A person always decides.**

| Doc | Purpose |
|-----|---------|
| `AGENTS.md` | Rules for the coding agent (architecture, policy, constraints) |
| `ARCHITECTURE_NOTE.md` | Technical architecture note for submission (~2 pp; PDF via script below) |
| `RUN_ME_FIRST.md` | Step-by-step local setup |

## LangGraph workflow

```
START → understand (LLM) → route A|B|C|D (code) → explain (LLM) → END
                         → decline (template) → END
```

Implementation: `agent/graph.py`. Business rules: `agent/rules.py`. Scheme tools: `agent/tools.py`. Claims: `agent/claims.py`. LLM (OpenRouter): `agent/llm.py`.

| Route | What it does |
|-------|----------------|
| A | Actual quarters vs 3% cap |
| B | Planned offer estimate vs cap |
| C | Intake — one claim vs 90-day window |
| D | Recovery list over the register |
| other | Polite decline |

Offline prep (run when raw data changes): `prepare_data.py`, `prepare_claims.py` → `data/scheme_by_*.csv`, `data/claims_window_check.csv`.

## Repository layout

```
app.py                 FastAPI (Vercel entrypoint)
agent/graph.py         LangGraph workflow
agent/tools.py         Scheme cap tools
agent/claims.py        Claims window tools
agent/rules.py         Policy logic (pytest-covered)
agent/llm.py           OpenRouter configuration
data/                  Prepared tables + batch/sku masters
public/                Static UI (HTML, CSS, JS)
tests/                   pytest (no API key)
checks/                  Golden checks (15/15, no API key)
```

## Run locally

Requires **Python 3.12+** (3.9 breaks `str | None` typing in the graph).

```bash
cd "sankalp 3"
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # set OPENROUTER_API_KEY for live LLM calls
pytest -q
python checks/run_checks.py
uvicorn app:app --reload
```

Open http://127.0.0.1:8000

### API

- `POST /api/ask` — run the graph
- `GET /api/recovery-list.csv` — full claims window check export
- `GET /api/health` — liveness and key configured flag

## Tests

```bash
pytest -q                  # unit + API tests (uses fake LLM, no network)
python checks/run_checks.py   # 15 golden policy checks on real prepared data
```

## Deploy (Vercel)

1. Push this repo to **private** GitHub.
2. Import project in Vercel; set `OPENROUTER_API_KEY` (optional `MODEL`).
3. Deploy; `public/` is served from the CDN, `/api/*` hits `app.py`.

## Architecture PDF

```bash
python3 scripts/export_architecture_pdf.py   # writes ARCHITECTURE_NOTE.pdf
```

## Out of scope (pilot)

Demand forecasting (CFO ask), repeat-credit, billing-match, quantity and breakage checks, approvals list, per-quarter chart — see `AGENTS.md`.