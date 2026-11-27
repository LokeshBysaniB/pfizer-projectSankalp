# Channel check (scheme cap and claims window): run it on your laptop

1. Open this folder in VS Code (File > Open Folder).
2. Open the terminal in VS Code (Terminal > New Terminal) and run, one line at a time.

Mac or Linux:
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt uvicorn pytest httpx

Windows (PowerShell):
    py -3.12 -m venv .venv
    .venv\Scripts\Activate.ps1
    pip install -r requirements.txt uvicorn pytest httpx

3. Run the tests. They need no key and no internet:
    pytest -q
    python checks/run_checks.py
   You should see all tests passing and 15/15 golden checks ok.

4. Add your key: copy .env.example to .env, then put your OpenRouter key after OPENROUTER_API_KEY=
5. Start the app:
    uvicorn app:app --reload
   Open http://127.0.0.1:8000 and click one of the example questions.
   Claims: type a batch, a date and a claim type to check one claim, or ask for the recovery list.
   The CSV of every checked claim downloads from the link on the page (/api/recovery-list.csv).

Only if you get new sales data: put the file at data/primary_sales.csv and run
    python prepare_data.py

Only if you get a new claims register: put the file at data/expiry_claims.csv and run
    python prepare_claims.py
