"""FastAPI entrypoint. Vercel finds the FastAPI instance named `app` in app.py.

Run locally:   uvicorn app:app --reload        then open http://127.0.0.1:8000
On Vercel:     the files in public/ are served from the CDN; /api/* reaches this app.
"""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from agent.claims import recovery_list_csv_path
from agent.graph import run_question

app = FastAPI(title="Project Sankalp pilot")
ROOT = Path(__file__).resolve().parent


class Ask(BaseModel):
    question: str


@app.get("/api/health")
def health():
    """Quick check that the deployment is alive and the key is configured."""
    return {"ok": True, "model_key_set": bool(os.getenv("OPENROUTER_API_KEY"))}


@app.post("/api/ask")
def ask(body: Ask):
    """Run one question through the graph and return the answer and the evidence."""
    try:
        return run_question(body.question)
    except ValueError as err:  # missing key or bad input: say so instead of a bare 500
        return JSONResponse({"error": str(err)}, status_code=503)


@app.get("/api/recovery-list.csv")
def recovery_list():
    """The claims window check for every credited and pending claim. Filter the 'group' column in Excel."""
    return FileResponse(recovery_list_csv_path(), media_type="text/csv", filename="claims_window_check.csv")


NO_CACHE = {"Cache-Control": "no-cache, must-revalidate"}


def _public_file(name: str, media_type: str) -> FileResponse:
    return FileResponse(ROOT / "public" / name, media_type=media_type, headers=NO_CACHE)


@app.get("/")
def index():
    return _public_file("index.html", "text/html")


@app.get("/app.js")
def app_js():
    return _public_file("app.js", "application/javascript")


@app.get("/style.css")
def style_css():
    return _public_file("style.css", "text/css")


# On Vercel the public/ folder is served by the platform, and Vercel's docs say not to
# mount it. On your laptop nothing serves it, so mount it only when not on Vercel.
if not os.getenv("VERCEL"):
    from starlette.staticfiles import StaticFiles

    class _NoCacheStaticFiles(StaticFiles):
        def file_response(self, *args, **kwargs):
            resp = super().file_response(*args, **kwargs)
            resp.headers["Cache-Control"] = "no-cache, must-revalidate"
            return resp

    app.mount("/", _NoCacheStaticFiles(directory=ROOT / "public"), name="public")
