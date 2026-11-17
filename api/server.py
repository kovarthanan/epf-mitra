"""
EPF Mitra - FastAPI backend for the web UI.

- Loads the Retriever ONCE at startup (no 25s wait per question).
- POST /api/ask         -> answer + cited sources + cost, rate-limited per user per day.
- POST /api/ask/stream  -> same, streamed as Server-Sent Events (typing effect in the UI).
- GET  /api/meta  -> "data as of" date, document count, questions left today.
- GET  /api/health

Usage (from the project root):
    pip install fastapi "uvicorn[standard]"
    uvicorn api.server:app --reload --port 8000
    # docs: http://localhost:8000/docs
"""

import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "rag"))
os.chdir(ROOT)  # rag/ scripts use paths relative to the project root (data/...)

from answer import answer, answer_stream  # noqa: E402
from retrieve import Retriever  # noqa: E402

DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", "10"))
MANIFEST = ROOT / "data" / "manifest.jsonl"
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:4200").split(",")
FRESHNESS_LINE = "Newer rules may exist; check epfindia.gov.in."

state: dict = {}
usage: dict[tuple[str, str], int] = {}  # (client_id, yyyy-mm-dd) -> questions asked
lock = threading.Lock()                 # one question at a time: CPU reranker + small VPS


def data_as_of() -> dict:
    """Newest document date in the manifest = how fresh the knowledge is."""
    dates, count = [], 0
    if MANIFEST.exists():
        for line in MANIFEST.read_text(encoding="utf-8").splitlines():
            if line.strip():
                count += 1
                d = json.loads(line).get("date")
                if d:
                    dates.append(d)
    return {"data_as_of": max(dates) if dates else None, "documents": count}


@asynccontextmanager
async def lifespan(app: FastAPI):
    state["retriever"] = Retriever(rerank=True)  # the slow part, done once
    state["meta"] = data_as_of()
    yield
    state.clear()


app = FastAPI(title="EPF Mitra API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"], allow_headers=["*"],
)


class AskIn(BaseModel):
    question: str = Field(min_length=5, max_length=500)


def client_id(request: Request) -> str:
    # Behind Traefik the real IP is the first entry of X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for")
    return fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "unknown")


def questions_left(cid: str) -> int:
    return max(0, DAILY_LIMIT - usage.get((cid, date.today().isoformat()), 0))


def with_freshness(text: str, cited: list[int]) -> str:
    """Guaranteed in code, not left to the LLM; skipped when nothing was cited ("not found" answers)."""
    if cited and FRESHNESS_LINE.lower() not in text.lower():
        text += f"\n\n{FRESHNESS_LINE}"
    return text


def check_limit(cid: str) -> tuple[str, str]:
    key = (cid, date.today().isoformat())
    if usage.get(key, 0) >= DAILY_LIMIT:
        raise HTTPException(429, f"Daily limit of {DAILY_LIMIT} questions reached. Please come back tomorrow.")
    return key


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/api/health")
def health():
    return {"status": "ok", "retriever_loaded": "retriever" in state}


@app.get("/api/meta")
def meta(request: Request):
    return {**state.get("meta", {}), "daily_limit": DAILY_LIMIT,
            "questions_left": questions_left(client_id(request))}


@app.post("/api/ask")
def ask(body: AskIn, request: Request):  # sync def -> FastAPI runs it in a thread pool
    cid = client_id(request)
    key = check_limit(cid)

    with lock:
        r = answer(state["retriever"], body.question.strip())
    usage[key] = usage.get(key, 0) + 1

    text = with_freshness(r["answer"], r["cited"])

    return {
        "question": r["question"],
        "answer": text,
        "sources": [{**s, "cited": s["rank"] in r["cited"]} for s in r["sources"]],
        "cost_inr": r["cost_inr"],
        "latency_s": r["latency_s"],
        "questions_left": questions_left(cid),
        "data_as_of": state["meta"]["data_as_of"],
    }


@app.post("/api/ask/stream")
def ask_stream(body: AskIn, request: Request):
    """Server-Sent Events: `sources` once, `token` many times, then `done` (or `error`)."""
    cid = client_id(request)
    key = check_limit(cid)  # 429 is returned as a normal HTTP error, before the stream starts
    question = body.question.strip()

    def events():
        gen = answer_stream(state["retriever"], question)
        try:
            # Only retrieval (CPU-heavy re-ranking) runs under the lock. The LLM streaming part
            # does not hold it: if a user closes the tab mid-answer, nobody else gets blocked.
            with lock:
                kind, payload = next(gen)
            yield sse(kind, payload)
            for kind, payload in gen:
                if kind == "token":
                    yield sse("token", {"text": payload})
                elif kind == "done":
                    usage[key] = usage.get(key, 0) + 1
                    extra = with_freshness(payload["answer"], payload["cited"])[len(payload["answer"]):]
                    if extra:
                        yield sse("token", {"text": extra})
                    yield sse("done", {
                        "answer": payload["answer"] + extra,
                        "cited": payload["cited"],
                        "cost_inr": payload["cost_inr"],
                        "latency_s": payload["latency_s"],
                        "questions_left": questions_left(cid),
                        "data_as_of": state["meta"]["data_as_of"],
                    })
        except Exception:  # noqa: BLE001 - never leave the UI waiting on a broken stream
            yield sse("error", {"detail": "Something went wrong while answering. Please try again."})

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
