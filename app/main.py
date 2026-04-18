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
from .llm import stream_chat, stream_chat_messages
from .parsers import extract_text
from .prompts import (
    ANALYZE_SYSTEM_PROMPT,
    OPTIMIZE_SYSTEM_PROMPT,
    REFINE_ANALYSIS_SYSTEM_PROMPT,
    REFINE_RESUME_SYSTEM_PROMPT,
)
from .schemas import AnalyzeRequest, OptimizeRequest, ParseResponse, RefineRequest

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


def _sse_typed_event(event_type: str, token: str) -> str:
    """Format a typed SSE event as JSON with type and token fields."""
    payload = {"type": event_type, "token": token}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_typed_done() -> str:
    return "data: [DONE]\n\n"


async def _refine_sse_stream(req: RefineRequest) -> AsyncIterator[str]:
    """SSE stream that splits LLM output into typed reply/content events."""
    system_prompt = (
        REFINE_ANALYSIS_SYSTEM_PROMPT
        if req.mode == "analysis"
        else REFINE_RESUME_SYSTEM_PROMPT
    )

    context_parts = [
        f"[RESUME]\n{req.resume.strip()}",
        f"[JD]\n{req.jd.strip()}",
        f"[CURRENT]\n{req.current_content.strip()}",
    ]
    if req.mode == "resume" and req.analysis:
        context_parts.append(f"[ANALYSIS]\n{req.analysis.strip()}")
    context_block = "\n\n".join(context_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_block},
        {"role": "assistant", "content": "已理解简历与 JD，请告诉我想怎么调整。"},
        *[{"role": m.role, "content": m.content} for m in req.history],
        {"role": "user", "content": req.instruction},
    ]

    yield ": ping\n\n"

    MARKER_REPLY = "<<<REPLY>>>"
    MARKER_CONTENT = "<<<CONTENT>>>"
    MARKER_LEN = max(len(MARKER_REPLY), len(MARKER_CONTENT))

    state = "buffering"
    tail = ""
    has_emitted_reply = False
    content_fallback = ""

    async for token in stream_chat_messages(messages):
        if not token:
            continue

        if token.startswith("\n\n[ERROR]"):
            error_msg = token.replace("\n\n[ERROR] ", "").strip()
            yield _sse_typed_event("error", error_msg)
            continue

        content_fallback += token
        combined = tail + token

        while True:
            if state == "buffering":
                reply_idx = combined.find(MARKER_REPLY)
                if reply_idx != -1:
                    state = "emit_reply"
                    combined = combined[reply_idx + len(MARKER_REPLY):]
                    has_emitted_reply = True
                    continue
                else:
                    tail = combined[-MARKER_LEN:] if len(combined) >= MARKER_LEN else combined
                    break

            elif state == "emit_reply":
                content_idx = combined.find(MARKER_CONTENT)
                if content_idx != -1:
                    reply_text = combined[:content_idx].strip()
                    if reply_text:
                        yield _sse_typed_event("reply", reply_text)
                    state = "emit_content"
                    combined = combined[content_idx + len(MARKER_CONTENT):]
                    continue
                else:
                    safe_end = max(0, len(combined) - MARKER_LEN)
                    if safe_end > 0:
                        yield _sse_typed_event("reply", combined[:safe_end])
                        combined = combined[safe_end:]
                    tail = combined
                    break

            elif state == "emit_content":
                yield _sse_typed_event("content", combined)
                tail = ""
                break

        if state == "emit_content":
            tail = ""
            combined = ""

    if state == "emit_reply" and tail.strip():
        yield _sse_typed_event("reply", tail.strip())
    elif state == "emit_content" and tail:
        yield _sse_typed_event("content", tail)

    if not has_emitted_reply and content_fallback.strip():
        yield _sse_typed_event("reply", "已更新内容。")
        yield _sse_typed_event("content", content_fallback)

    yield _sse_typed_done()


@app.post("/api/refine")
async def refine(req: RefineRequest) -> StreamingResponse:
    return StreamingResponse(
        _refine_sse_stream(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
