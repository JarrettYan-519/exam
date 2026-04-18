"""Thin wrapper around the DeepSeek chat-completion API (OpenAI-compatible)."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI, APIError, APIConnectionError, AuthenticationError, RateLimitError

from .config import get_settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        settings = get_settings()
        _client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            timeout=settings.request_timeout_seconds,
        )
    return _client


async def stream_chat(system_prompt: str, user_prompt: str) -> AsyncIterator[str]:
    """Yield raw content tokens from DeepSeek, one chunk at a time.

    On errors, yields a single synthetic token like `[ERROR] ...` so the
    frontend can surface it without the SSE stream hanging.
    """
    settings = get_settings()
    client = get_client()

    try:
        stream = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            stream=True,
            temperature=0.3,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except AuthenticationError:
        logger.exception("DeepSeek authentication failed")
        yield "\n\n[ERROR] DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY 是否正确。"
    except RateLimitError:
        logger.exception("DeepSeek rate limit")
        yield "\n\n[ERROR] 调用频率超限，请稍后重试。"
    except APIConnectionError:
        logger.exception("DeepSeek connection error")
        yield "\n\n[ERROR] 无法连接到 DeepSeek 服务，请检查网络。"
    except APIError as exc:
        logger.exception("DeepSeek API error")
        yield f"\n\n[ERROR] DeepSeek 接口错误：{exc.message if hasattr(exc, 'message') else exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected LLM error")
        yield f"\n\n[ERROR] 未预期错误：{exc}"


async def stream_chat_messages(messages: list[dict]) -> AsyncIterator[str]:
    """Yield raw content tokens from DeepSeek given a pre-assembled message list.

    Same error handling pattern as stream_chat: yields synthetic [ERROR] tokens
    so the frontend can surface errors without the SSE stream hanging.
    """
    settings = get_settings()
    client = get_client()

    try:
        stream = await client.chat.completions.create(
            model=settings.deepseek_model,
            messages=messages,
            stream=True,
            temperature=0.3,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content
    except AuthenticationError:
        logger.exception("DeepSeek authentication failed")
        yield "\n\n[ERROR] DeepSeek 鉴权失败，请检查 DEEPSEEK_API_KEY 是否正确。"
    except RateLimitError:
        logger.exception("DeepSeek rate limit")
        yield "\n\n[ERROR] 调用频率超限，请稍后重试。"
    except APIConnectionError:
        logger.exception("DeepSeek connection error")
        yield "\n\n[ERROR] 无法连接到 DeepSeek 服务，请检查网络。"
    except APIError as exc:
        logger.exception("DeepSeek API error")
        yield f"\n\n[ERROR] DeepSeek 接口错误：{exc.message if hasattr(exc, 'message') else exc}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected LLM error")
        yield f"\n\n[ERROR] 未预期错误：{exc}"
