"""FastAPI entrypoint for the resume-optimization agent."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .llm import stream_chat
from .parsers import extract_text
from .prompts import ANALYZE_SYSTEM_PROMPT, OPTIMIZE_SYSTEM_PROMPT
from .schemas import AnalyzeRequest, OptimizeRequest, ParseResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(
    title="Resume Optimization Agent",
    description="基于 DeepSeek 的简历匹配分析与优化 Agent",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _startup() -> None:
    # Fail fast if the key is missing — surfaces config errors in `docker logs`.
    settings = get_settings()
    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    logging.getLogger(__name__).info(
        "Starting resume-agent | model=%s base_url=%s",
        settings.deepseek_model,
        settings.deepseek_base_url,
    )


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.post("/api/parse", response_model=ParseResponse)
async def parse_file(file: UploadFile = File(...)) -> ParseResponse:
    settings = get_settings()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="空文件")
    text = extract_text(file.filename or "upload", data, settings.max_upload_mb)
    return ParseResponse(filename=file.filename or "upload", text=text)


def _sse_format(payload: str) -> str:
    """Format a single SSE `data:` frame with JSON-encoded payload."""
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


async def _sse_stream(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
    # Initial ping so browsers/proxies flush headers immediately.
    yield ": ping\n\n"
    async for token in stream_chat(system_prompt, user_prompt):
        if token:
            yield _sse_format(token)
    yield "data: [DONE]\n\n"


@app.post("/api/analyze")
async def analyze(req: AnalyzeRequest) -> StreamingResponse:
    user_prompt = (
        f"[RESUME]\n{req.resume.strip()}\n\n"
        f"[JD]\n{req.jd.strip()}"
    )
    return StreamingResponse(
        _sse_stream(ANALYZE_SYSTEM_PROMPT, user_prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/optimize")
async def optimize(req: OptimizeRequest) -> StreamingResponse:
    user_prompt = (
        f"[RESUME]\n{req.resume.strip()}\n\n"
        f"[JD]\n{req.jd.strip()}\n\n"
        f"[ANALYSIS]\n{req.analysis.strip()}"
    )
    return StreamingResponse(
        _sse_stream(OPTIMIZE_SYSTEM_PROMPT, user_prompt),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
