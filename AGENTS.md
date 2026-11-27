# Instructions for the coding agent

Read this file before every task. Keep it short and keep it true.

## What we are building
A chat assistant for Pfizer Limited's General Medicines trade channel with two checks.
1. Scheme cap (policy CO-POL-014 section 4.4: free goods at PTS must not exceed 3% of a quarter's primary sales).
2. Expiry claim window (claims policy section 5.2: a near-expiry claim is valid only in the 90 days before the batch's expiry date; an expired claim only within 90 days after it).
Scheme cap users: Sales (the NSM) checks a planned offer before the circular goes out; the CFO and the Controller
review how past quarters did and see the cost of any exception. The tool only recommends. A person decides.
Evidence so far: free goods were above the cap in 7 quarters (Q3 FY25 to Q1 FY27), INR 3.95 crore in total,
about INR 1.58 crore a year.
Claims evidence so far (credited claims, expiry from the batch master): 184 outside the window, INR 34.5 lakh, about INR 13.8 lakh a year.
Of these, 64 (INR 10.7 lakh) are more than 90 days after expiry ("firm"); 120 (INR 23.8 lakh) need the claims team to confirm first
(101 raised more than 90 days before expiry, 19 labelled near expiry but raised 1 to 90 days after). 47 claims (INR 4.3 lakh) have a batch not in the master: escalate, never reject.
The claims tool has two modes that share one rule: intake (check one new claim) and the recovery list (the same rule over the register).

## Architecture
understand (model) -> route A: actual numbers (code) -> explain (model) -> a person decides
                   -> route B: estimate for a planned offer (code) -> explain (model)
                   -> route C: check one claim against the 90-day window (code) -> explain (model)
                   -> route D: recovery list over past claims (code) -> explain (model)
                   -> decline (code, for anything else)
Model nodes: `understand` and `explain` only. Everything else is plain code.
Data is prepared once by `prepare_data.py` into `data/scheme_by_quarter.csv` and `data/scheme_by_tier.csv`.
Claims are prepared once by `prepare_claims.py` into `data/claims_window_check.csv`, using the same rule function as intake.
The app reads those small tables and the batch master; it never reads the raw sales or claims files.

## Rules
- Facts come from tools that read `data/`. The model never writes a batch number, date,
  quantity or amount that did not come from a tool result.
- Business rules (the 3% cap, excess, offer projection) live in plain Python in
  `agent/rules.py`, each with a pytest test in `tests/test_rules.py`.
- Sales base is billed packs x PTS (free packs excluded). Free goods are free packs x PTS.
  Fiscal year runs April to March (Q3 FY25 = Oct to Dec 2024).
- Route B is an estimate: same orders as the basis quarter (the latest full quarter, Q1 FY27, when the requested quarter has no data yet). Always show the assumptions.
- A rupee amount is the whole free goods for that request unless the wording says extra, then it sits on top of the current offer. Amounts are added on top of an offer ratio. Scheme-name-only requests are not supported.
- The claims window rule lives in `agent/rules.py` (`window_check`), tested in `tests/test_window_rules.py`. Expiry always comes from the batch master. A batch not in the master is escalated, never rejected. Breakage and short supply are not covered by this rule yet (group `not_checked`).
- The "firm" group is only claims more than 90 days after expiry. Raised-too-early and near-expiry-label-after-expiry claims are "confirm": the policy does not say whether they are rejected or refiled, so ask the claims team.
- Not built: repeat credits, billing match, quantity, breakage start date (the other claim checks).
- One small change per task. Run `pytest -q` after each change. Do not touch files the task
  does not need.
- Do not add a database, a vector store, a new framework or a new folder without asking.
- The frontend stays in `public/` as plain HTML, CSS and JavaScript.
- Secrets live only in `.env` locally and in Vercel environment variables. Never commit them.

## How to run
pip install -r requirements.txt uvicorn pytest httpx
pytest -q
uvicorn app:app --reload

## Current task
Claims window slice: intake check (route C) and recovery list (route D) working end to end, all tests passing, deployed to Vercel.
Scheme cap slice (routes A and B) is finished.
Not built yet: repeat-credit, billing-match, quantity and breakage checks; an approvals list; a per-quarter chart.
