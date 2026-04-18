# Multi-Turn Refine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a multi-turn conversational refinement feature — users can chat with the Agent to iteratively refine analysis (Step 2) or the optimized resume (Step 3) via a right-side drawer.

**Architecture:** Single new backend endpoint `POST /api/refine` with typed SSE events (`reply`/`content`). Frontend holds all state in-memory. A marker-based state machine splits the LLM stream into reply and content segments. Right-side drawer UI on desktop, bottom sheet on mobile.

**Tech Stack:** FastAPI + Pydantic + openai SDK (existing); vanilla JS + `marked` CDN (existing). No new dependencies.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `app/schemas.py` | Modify | Add `ChatMessage`, `RefineRequest` models |
| `app/prompts.py` | Modify | Add `REFINE_ANALYSIS_SYSTEM_PROMPT`, `REFINE_RESUME_SYSTEM_PROMPT` |
| `app/llm.py` | Modify | Add `stream_chat_messages()` function |
| `app/main.py` | Modify | Add marker state machine `_refine_sse_stream()`, route `POST /api/refine` |
| `static/index.html` | Modify | Add refine buttons on Step 2/3, drawer `<aside>` element |
| `static/style.css` | Modify | Add drawer, bubble, refine-input, mobile sheet styles |
| `static/app.js` | Modify | Add `refineState`, `openRefine()`, `closeRefine()`, `sendRefine()`, typed SSE in `streamPost()` |
| `README.md` | Modify | Add `/api/refine` API docs, update verification checklist |

---

### Task 1: Add RefineRequest and ChatMessage to schemas.py

**Files:**
- Modify: `app/schemas.py`

- [ ] **Step 1: Add ChatMessage and RefineRequest models**

Append to `app/schemas.py` after the existing `ParseResponse` class:

```python
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AnalyzeRequest(BaseModel):
    resume: str = Field(..., min_length=10, max_length=20000)
    jd: str = Field(..., min_length=10, max_length=10000)


class OptimizeRequest(AnalyzeRequest):
    analysis: str = Field(..., min_length=10, max_length=20000)


class ParseResponse(BaseModel):
    filename: str
    text: str


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=5000)


class RefineRequest(BaseModel):
    mode: Literal["analysis", "resume"]
    resume: str = Field(min_length=10, max_length=20000)
    jd: str = Field(min_length=10, max_length=10000)
    analysis: str | None = Field(default=None, max_length=20000)
    current_content: str = Field(min_length=10, max_length=20000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=30)
    instruction: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def resume_mode_requires_analysis(self):
        if self.mode == "resume" and not self.analysis:
            raise ValueError("analysis is required when mode is 'resume'")
        return self
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /Users/jarrett/Desktop/exam-2026 && python -c "from app.schemas import RefineRequest, ChatMessage; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/schemas.py
git commit -m "feat: add ChatMessage and RefineRequest schemas for refine endpoint"
```

---

### Task 2: Add refine system prompts to prompts.py

**Files:**
- Modify: `app/prompts.py`

- [ ] **Step 1: Append two new prompt constants**

Add after `OPTIMIZE_SYSTEM_PROMPT` in `app/prompts.py`:

```python
REFINE_ANALYSIS_SYSTEM_PROMPT = """你是一位资深的招聘顾问与简历教练。用户已经拿到了你之前给出的匹配度分析结果，现在想针对某些方面进行调整。

你将收到以下输入：
- [RESUME] 候选人简历原文
- [JD] 目标岗位描述
- [CURRENT] 当前版本的分析结果
- 之前的对话历史（如有）
- 用户本轮的调整指令

请在 [CURRENT] 的基础上，按用户的指令重新调整分析。调整时注意：
1. 保留四段 Markdown 结构不变：## 📊 整体匹配度、## ✨ 匹配亮点、## ⚠️ 主要缺口、## 💡 具体优化建议
2. 只修改用户要求的方面，其他部分保持原样
3. 所有条目仍必须引用简历/JD 中的具体内容，禁止编造
4. 全部用中文

输出格式（严格遵守）：
先输出 <<<REPLY>>> 标记，然后用 1-2 句中文简短说明你做了什么改动以及为什么。
再输出 <<<CONTENT>>> 标记，然后输出完整的新版 Markdown 分析内容。
不要输出任何其他标记或说明。
"""

REFINE_RESUME_SYSTEM_PROMPT = """你是一位专业的中文简历改写顾问。用户已经拿到了你之前给出的优化简历，现在想针对某些部分进行进一步调整。

你将收到以下输入：
- [RESUME] 候选人原始简历
- [JD] 目标岗位描述
- [ANALYSIS] 匹配度分析结果
- [CURRENT] 当前版本的优化简历
- 之前的对话历史（如有）
- 用户本轮的调整指令

请在 [CURRENT] 的基础上，按用户的指令重新调整简历。调整时注意：
1. 绝对不得捏造事实、公司、头衔、时间、数字或业绩。凡是原简历中没有的量化指标，保留原本的定性表述并追加 `[可量化]` 占位标记
2. 保留原简历中所有真实经历，只做重写/重排/关键词替换
3. 简历结构固定为以下小节（顺序不变）：# 个人信息、## 概要、## 核心技能、## 工作经历、## 项目经历、## 教育背景、## 其他（可选）
4. 措辞和关键词要尽量贴合 JD 的重点要求
5. 全部用中文

输出格式（严格遵守）：
先输出 <<<REPLY>>> 标记，然后用 1-2 句中文简短说明你做了什么改动以及为什么。
再输出 <<<CONTENT>>> 标记，然后输出完整的新版 Markdown 简历内容。
不要输出任何其他标记或说明。
"""
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /Users/jarrett/Desktop/exam-2026 && python -c "from app.prompts import REFINE_ANALYSIS_SYSTEM_PROMPT, REFINE_RESUME_SYSTEM_PROMPT; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/prompts.py
git commit -m "feat: add refine system prompts for analysis and resume iteration"
```

---

### Task 3: Add stream_chat_messages to llm.py

**Files:**
- Modify: `app/llm.py`

- [ ] **Step 1: Add stream_chat_messages function**

Append to `app/llm.py` after the existing `stream_chat` function:

```python
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
```

- [ ] **Step 2: Verify the module loads**

Run: `cd /Users/jarrett/Desktop/exam-2026 && python -c "from app.llm import stream_chat_messages; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app/llm.py
git commit -m "feat: add stream_chat_messages for pre-assembled message lists"
```

---

### Task 4: Add marker state machine and /api/refine route to main.py

**Files:**
- Modify: `app/main.py`

- [ ] **Step 1: Add imports**

In `app/main.py`, update the imports at the top. Change the llm import line and add the new schema/prompt imports:

```python
from .llm import stream_chat, stream_chat_messages
from .parsers import extract_text
from .prompts import (
    ANALYZE_SYSTEM_PROMPT,
    OPTIMIZE_SYSTEM_PROMPT,
    REFINE_ANALYSIS_SYSTEM_PROMPT,
    REFINE_RESUME_SYSTEM_PROMPT,
)
from .schemas import AnalyzeRequest, OptimizeRequest, ParseResponse, RefineRequest
```

- [ ] **Step 2: Add typed SSE helpers and refine route**

Append after the existing `optimize` route function (after line 124), before the file ends:

```python
def _sse_typed_event(event_type: str, token: str) -> str:
    """Format a typed SSE event as JSON with type and token fields."""
    payload = {"type": event_type, "token": token}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _sse_typed_done() -> str:
    return "data: [DONE]\n\n"


async def _refine_sse_stream(req: RefineRequest) -> AsyncIterator[str]:
    """SSE stream that splits LLM output into typed reply/content events.

    The LLM is prompted to output:
        <<<REPLY>>>
        <brief explanation>
        <<<CONTENT>>>
        <full new markdown>

    A state machine scans the token stream for these markers and emits
    typed SSE events accordingly. If no <<<REPLY>>> marker is found,
    the entire output is treated as content with a default reply injected.
    """
    # Select system prompt based on mode
    system_prompt = (
        REFINE_ANALYSIS_SYSTEM_PROMPT
        if req.mode == "analysis"
        else REFINE_RESUME_SYSTEM_PROMPT
    )

    # Build context block
    context_parts = [
        f"[RESUME]\n{req.resume.strip()}",
        f"[JD]\n{req.jd.strip()}",
        f"[CURRENT]\n{req.current_content.strip()}",
    ]
    if req.mode == "resume" and req.analysis:
        context_parts.append(f"[ANALYSIS]\n{req.analysis.strip()}")
    context_block = "\n\n".join(context_parts)

    # Assemble message list
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": context_block},
        {"role": "assistant", "content": "已理解简历与 JD，请告诉我想怎么调整。"},
        *[{"role": m.role, "content": m.content} for m in req.history],
        {"role": "user", "content": req.instruction},
    ]

    yield ": ping\n\n"

    # Marker state machine
    MARKER_REPLY = "<<<REPLY>>>"
    MARKER_CONTENT = "<<<CONTENT>>>"
    MARKER_LEN = max(len(MARKER_REPLY), len(MARKER_CONTENT))  # 14

    state = "buffering"  # buffering -> emit_reply -> emit_content
    tail = ""  # small buffer for detecting markers split across chunks
    has_emitted_reply = False
    content_fallback = ""  # accumulates all tokens as fallback if no markers found

    async for token in stream_chat_messages(messages):
        if not token:
            continue

        # Check for error tokens from the LLM client
        if token.startswith("\n\n[ERROR]"):
            error_msg = token.replace("\n\n[ERROR] ", "").strip()
            yield _sse_typed_event("error", error_msg)
            continue

        # Always accumulate for fallback
        content_fallback += token

        combined = tail + token

        # Process the combined buffer, scanning for markers
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

    # Flush remaining tail based on final state
    if state == "emit_reply" and tail.strip():
        yield _sse_typed_event("reply", tail.strip())
    elif state == "emit_content" and tail:
        yield _sse_typed_event("content", tail)

    # Fallback: no <<<REPLY>>> marker was ever found
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
```

- [ ] **Step 3: Verify the app starts**

Run: `cd /Users/jarrett/Desktop/exam-2026 && DEEPSEEK_API_KEY=test python -c "from app.main import app; print('routes:', [r.path for r in app.routes])"`
Expected: Output includes `/api/refine`

- [ ] **Step 4: Commit**

```bash
git add app/main.py
git commit -m "feat: add /api/refine endpoint with marker-based typed SSE stream"
```

---

### Task 5: Add drawer HTML and refine buttons to index.html

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add "Continue Refining" button to Step 2 actions**

In the Step 2 card (`id="step-analysis"`), in the `<div class="actions">` block (around line 72-76), add a new button after `btn-reanalyze`:

Change the actions div from:
```html
      <div class="actions">
        <button id="btn-optimize" class="btn primary" disabled>✅ 确认并生成优化后的简历</button>
        <button id="btn-reanalyze" class="btn ghost" type="button">重新分析</button>
        <span id="optimize-status" class="status-inline"></span>
      </div>
```
To:
```html
      <div class="actions">
        <button id="btn-optimize" class="btn primary" disabled>✅ 确认并生成优化后的简历</button>
        <button id="btn-refine-analysis" class="btn ghost" type="button">💬 继续追问</button>
        <button id="btn-reanalyze" class="btn ghost" type="button">重新分析</button>
        <span id="optimize-status" class="status-inline"></span>
      </div>
```

- [ ] **Step 2: Add "Continue Refining" button to Step 3 actions**

In the Step 3 card (`id="step-result"`), in the `<div class="actions">` block (around line 93-98), add a new button after `btn-download`:

Change the actions div from:
```html
      <div class="actions">
        <button id="btn-copy" class="btn primary">📋 复制 Markdown</button>
        <button id="btn-download" class="btn">⬇️ 下载 .md</button>
        <button id="btn-restart" class="btn ghost" type="button">重新开始</button>
        <span id="copy-status" class="status-inline"></span>
      </div>
```
To:
```html
      <div class="actions">
        <button id="btn-copy" class="btn primary">📋 复制 Markdown</button>
        <button id="btn-download" class="btn">⬇️ 下载 .md</button>
        <button id="btn-refine-resume" class="btn ghost" type="button">💬 继续追问</button>
        <button id="btn-restart" class="btn ghost" type="button">重新开始</button>
        <span id="copy-status" class="status-inline"></span>
      </div>
```

- [ ] **Step 3: Add drawer aside element before closing `</body>` tag**

Insert before `</body>` (before the `<script>` tag at line 106):

```html
  <!-- Refine drawer -->
  <aside id="refine-drawer" class="refine-drawer">
    <div class="refine-header">
      <span class="refine-title">💬 迭代优化</span>
      <button id="refine-close" class="refine-close-btn">✕</button>
    </div>
    <div id="refine-body" class="refine-body"></div>
    <div class="refine-footer">
      <button id="refine-clear" class="refine-clear-btn">清空本轮对话</button>
      <div class="refine-input-row">
        <textarea id="refine-input" class="refine-input" placeholder="说说你想怎么改……" rows="1"></textarea>
        <button id="refine-send" class="refine-send-btn">↑</button>
      </div>
    </div>
  </aside>
```

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: add refine buttons and drawer HTML structure"
```

---

### Task 6: Add drawer, bubble, and refine styles to style.css

**Files:**
- Modify: `static/style.css`

- [ ] **Step 1: Append refine styles at the end of style.css**

Add the following block at the end of `static/style.css`:

```css
/* ================================================================
 * Refine drawer
 * ================================================================ */

.refine-drawer {
  position: fixed;
  top: 0;
  right: 0;
  width: 400px;
  height: 100vh;
  background: var(--surface);
  border-left: 1px solid var(--border-soft);
  box-shadow: -4px 0 24px rgba(0, 0, 0, 0.06);
  z-index: 50;
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.refine-drawer.open {
  transform: translateX(0);
}

.refine-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 22px;
  border-bottom: 1px solid var(--border-soft);
}

.refine-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.refine-close-btn {
  background: none;
  border: none;
  font-size: 18px;
  color: var(--text-subtle);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: background-color 0.15s ease, color 0.15s ease;
}

.refine-close-btn:hover {
  background: rgba(0, 0, 0, 0.05);
  color: var(--text);
}

.refine-body {
  flex: 1;
  overflow-y: auto;
  padding: 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.refine-footer {
  padding: 14px 22px 18px;
  border-top: 1px solid var(--border-soft);
}

.refine-clear-btn {
  background: none;
  border: none;
  color: var(--text-subtle);
  font-size: 12px;
  cursor: pointer;
  padding: 0 0 10px;
  font-family: inherit;
  transition: color 0.15s ease;
}

.refine-clear-btn:hover {
  color: var(--accent);
}

.refine-input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bg);
  border-radius: 22px;
  padding: 6px 6px 6px 16px;
  border: 1px solid var(--border-soft);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.refine-input-row:focus-within {
  border-color: var(--accent);
  box-shadow: var(--shadow-focus);
}

.refine-input {
  flex: 1;
  border: none;
  background: transparent;
  resize: none;
  min-height: 24px;
  max-height: 120px;
  padding: 4px 0;
  font-family: var(--font-sans);
  font-size: 14px;
  line-height: 1.5;
  color: var(--text);
  outline: none;
}

.refine-send-btn {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--accent);
  color: #fff;
  border: none;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: background-color 0.15s ease, transform 0.12s ease;
}

.refine-send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.refine-send-btn:active:not(:disabled) {
  transform: scale(0.92);
  background: var(--accent-press);
}

.refine-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* Chat bubbles */

.bubble {
  max-width: 88%;
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
}

.bubble-user {
  background: var(--accent);
  color: #fff;
  align-self: flex-end;
  border-bottom-right-radius: 4px;
}

.bubble-assistant {
  background: var(--bg);
  color: var(--text);
  align-self: flex-start;
  border-bottom-left-radius: 4px;
}

.bubble-error {
  background: #fef2f0;
  color: var(--danger);
  align-self: flex-start;
  border-bottom-left-radius: 4px;
  border: 1px solid rgba(191, 72, 0, 0.15);
}

.bubble-cursor::after {
  content: "▎";
  animation: blink 0.8s step-end infinite;
  color: var(--text-subtle);
}

@keyframes blink {
  50% { opacity: 0; }
}

/* Mobile: bottom sheet */

@media (max-width: 768px) {
  .refine-drawer {
    top: auto;
    bottom: 0;
    left: 0;
    right: 0;
    width: 100%;
    height: 80vh;
    border-left: none;
    border-top: 1px solid var(--border-soft);
    border-radius: var(--radius-lg) var(--radius-lg) 0 0;
    box-shadow: 0 -4px 24px rgba(0, 0, 0, 0.08);
    transform: translateY(100%);
  }

  .refine-drawer.open {
    transform: translateY(0);
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add static/style.css
git commit -m "feat: add drawer, bubble, and refine input styles"
```

---

### Task 7: Add refine JS logic to app.js

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: Add DOM element references and state**

After the existing `let resultMarkdown = "";` (line 32), add:

```js
  // ---------- refine state ----------
  const drawer = $("refine-drawer");
  const refineBody = $("refine-body");
  const refineInput = $("refine-input");
  const refineSendBtn = $("refine-send");
  const refineCloseBtn = $("refine-close");
  const refineClearBtn = $("refine-clear");
  const btnRefineAnalysis = $("btn-refine-analysis");
  const btnRefineResume = $("btn-refine-resume");

  let refineAbortController = null;

  const refineState = {
    analysis: { open: false, history: [], streaming: false },
    resume:   { open: false, history: [], streaming: false }
  };
```

- [ ] **Step 2: Add typed SSE support to streamPost**

Replace the existing `streamPost` function (lines 73-106) with a version that supports a `typed` option:

```js
  async function streamPost(url, body, onToken, { typed = false, onEvent = null, signal = null } = {}) {
    const fetchOpts = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    };
    if (signal) fetchOpts.signal = signal;

    const res = await fetch(url, fetchOpts);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() || "";
      for (const evt of events) {
        for (const line of evt.split("\n")) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6);
          if (raw === "[DONE]") return;
          try {
            const parsed = JSON.parse(raw);
            if (typed && onEvent) {
              onEvent(parsed);
            } else {
              onToken(parsed);
            }
          } catch {
            // ignore malformed fragments
          }
        }
      }
    }
  }
```

Note: existing callers of `streamPost` use positional `(url, body, onToken)` — they pass no options object, so `typed` defaults to `false` and `onEvent` is `null`. The old behavior is preserved.

- [ ] **Step 3: Add refine UI functions**

After the sample data section (after line 289), add the following functions before the closing `})();`:

```js
  // ---------- refine drawer ----------

  function getRefineMode() {
    if (refineState.analysis.open) return "analysis";
    if (refineState.resume.open) return "resume";
    return null;
  }

  function getCanvasContent(mode) {
    return mode === "analysis" ? analysisMarkdown : resultMarkdown;
  }

  function setCanvasContent(mode, content) {
    if (mode === "analysis") {
      analysisMarkdown = content;
      analysisOutput.innerHTML = marked.parse(content);
    } else {
      resultMarkdown = content;
      resultPreview.innerHTML = marked.parse(content);
      resultSource.textContent = content;
    }
  }

  function getCanvasElement(mode) {
    return mode === "analysis" ? analysisOutput : resultPreview;
  }

  function openRefine(mode) {
    // Close other mode if open
    const other = mode === "analysis" ? "resume" : "analysis";
    refineState[other].open = false;

    refineState[mode].open = true;
    drawer.classList.add("open");
    refineInput.focus();

    // Re-render history
    refineBody.innerHTML = "";
    for (const msg of refineState[mode].history) {
      const div = document.createElement("div");
      div.className = msg.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant";
      div.textContent = msg.content;
      refineBody.appendChild(div);
    }
    _scrollDrawer();
  }

  function closeRefine() {
    const mode = getRefineMode();
    if (mode && refineState[mode].streaming && refineAbortController) {
      refineAbortController.abort();
      refineState[mode].streaming = false;
      // Remove the last empty assistant bubble
      const lastBubble = refineBody.querySelector(".bubble-assistant:last-child");
      if (lastBubble && !lastBubble.textContent.trim()) {
        lastBubble.remove();
      }
    }
    drawer.classList.remove("open");
    if (mode) refineState[mode].open = false;
  }

  function _scrollDrawer() {
    refineBody.scrollTop = refineBody.scrollHeight;
  }

  function _addBubble(role, text, extraClass) {
    const div = document.createElement("div");
    div.className = `bubble bubble-${role}` + (extraClass ? ` ${extraClass}` : "");
    div.textContent = text || "";
    refineBody.appendChild(div);
    _scrollDrawer();
    return div;
  }

  async function sendRefine() {
    const mode = getRefineMode();
    if (!mode) return;
    const instruction = refineInput.value.trim();
    if (!instruction || refineState[mode].streaming) return;

    refineState[mode].streaming = true;
    refineSendBtn.disabled = true;
    refineInput.value = "";

    // Show user bubble
    _addBubble("user", instruction);

    // Show empty assistant bubble with cursor
    const assistantBubble = _addBubble("assistant", "", "bubble-cursor");

    const body = {
      mode,
      resume: resumeEl.value.trim(),
      jd: jdEl.value.trim(),
      current_content: getCanvasContent(mode),
      history: refineState[mode].history,
      instruction,
    };
    if (mode === "resume") {
      body.analysis = analysisMarkdown;
    }

    let replyBuffer = "";
    let contentBuffer = getCanvasContent(mode);
    refineAbortController = new AbortController();

    try {
      await streamPost("/api/refine", body, null, {
        typed: true,
        signal: refineAbortController.signal,
        onEvent: (event) => {
          if (event.type === "reply") {
            replyBuffer += event.token;
            assistantBubble.textContent = replyBuffer;
            _scrollDrawer();
          } else if (event.type === "content") {
            contentBuffer += event.token;
            setCanvasContent(mode, contentBuffer);
          } else if (event.type === "error") {
            assistantBubble.textContent = event.token;
            assistantBubble.classList.remove("bubble-cursor");
            assistantBubble.classList.add("bubble-error");
          }
        },
      });

      // Finalize: remove cursor
      assistantBubble.classList.remove("bubble-cursor");

      // Default reply if empty
      if (!replyBuffer.trim()) {
        replyBuffer = "已更新内容。";
        assistantBubble.textContent = replyBuffer;
      }

      // Push to history
      refineState[mode].history.push(
        { role: "user", content: instruction },
        { role: "assistant", content: replyBuffer },
      );
    } catch (e) {
      if (e.name === "AbortError") {
        // User closed drawer mid-stream — don't update history
      } else {
        assistantBubble.textContent = `出错了: ${e.message}`;
        assistantBubble.classList.remove("bubble-cursor");
        assistantBubble.classList.add("bubble-error");
      }
    } finally {
      refineState[mode].streaming = false;
      refineSendBtn.disabled = false;
      refineAbortController = null;
    }
  }

  // ---------- refine event listeners ----------

  btnRefineAnalysis.addEventListener("click", () => openRefine("analysis"));
  btnRefineResume.addEventListener("click", () => openRefine("resume"));
  refineCloseBtn.addEventListener("click", closeRefine);

  refineSendBtn.addEventListener("click", sendRefine);

  refineInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendRefine();
    }
  });

  refineClearBtn.addEventListener("click", () => {
    const mode = getRefineMode();
    if (!mode) return;
    refineState[mode].history = [];
    refineBody.innerHTML = "";
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && drawer.classList.contains("open")) {
      closeRefine();
    }
  });
```

- [ ] **Step 4: Commit**

```bash
git add static/app.js
git commit -m "feat: add refine drawer JS logic with typed SSE and state management"
```

---

### Task 8: Update README with refine API docs and verification checklist

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add /api/refine section to API reference**

In the `## API 参考` section, after the `/api/optimize` block, add:

```markdown
### `POST /api/refine`  *(SSE)*
在用户追问时调用，流式输出类型化事件（reply + content）。

请求体：
```json
{
  "mode": "analysis" | "resume",
  "resume": "...",
  "jd": "...",
  "analysis": "...(mode=resume 时必填)...",
  "current_content": "...(当前 Canvas 中的完整内容)...",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "instruction": "本轮用户的追问指令"
}
```

响应格式（`text/event-stream`）：
```
: ping

data: {"type":"reply","token":"好的，我强化了..."}
data: {"type":"content","token":"## 项目经历\n\n- ..."}
...
data: [DONE]
```

- `type: "reply"` — Agent 的简短中文回复，显示在聊天气泡
- `type: "content"` — 完整新版 Markdown 片段，替换 Canvas 内容
- `type: "error"` — 错误信息

示例 `curl`：
```bash
curl -N -X POST http://localhost:8000/api/refine \
  -H "Content-Type: application/json" \
  -d '{"mode":"resume","resume":"...","jd":"...","analysis":"...","current_content":"...","history":[],"instruction":"项目经验再突出一下"}'
```
```

- [ ] **Step 2: Add verification items to the checklist**

In the `## 验收自查清单` section, append these items:

```markdown
- [ ] Step 2 分析完成后点「💬 继续追问」→ 右侧抽屉打开 → 发送「重点强化技术栈部分」→ 看到聊天气泡回复 + Canvas 分析内容被流式更新
- [ ] 连续追问第二轮（含指代，如「刚才那个再加强一点」）→ 两轮对话都在气泡中保留、Canvas 再次更新
- [ ] 关闭抽屉再打开 → 历史对话仍在；点「清空本轮对话」→ 历史清空、Canvas 内容不变
- [ ] Step 3 简历完成后同样可以追问，抽屉和更新流程一致
- [ ] `curl -N -X POST http://localhost:8000/api/refine ...` 返回类型化 SSE 事件并以 `[DONE]` 结束
```

- [ ] **Step 3: Add a paragraph to LLM design section**

In the `## LLM 交互设计说明` section, after the existing paragraph about error handling (after "避免'转圈圈卡死'的糟糕体验。"), add:

```markdown
**多轮迭代设计**（见 `/api/refine`）
用户在看到分析结果或优化简历后，可以打开右侧抽屉追问。每次追问把完整对话历史 + 原始简历/JD + 当前 Canvas 内容一起发给 DeepSeek，保证模型理解上下文中的指代关系。模型输出通过 `<<<REPLY>>>` / `<<<CONTENT>>>` 标记分成两段：简短中文回复（聊天气泡）和完整新版 Markdown（Canvas 替换）。后端用一个状态机实时扫描 token 流，将标记前后的内容分别包装成 `reply` / `content` 类型的 SSE 事件下发前端。
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: add /api/refine API reference and multi-turn verification checklist"
```

---

### Task 9: Smoke test — backend curl

**Files:** None (manual verification)

- [ ] **Step 1: Start the app locally**

Run (in one terminal):
```bash
cd /Users/jarrett/Desktop/exam-2026
DEEPSEEK_API_KEY=sk-40e97e965deb40ed9925c3017fe660cf uvicorn app.main:app --port 8000
```

- [ ] **Step 2: Hit /api/refine with curl**

Run (in another terminal):
```bash
curl -N -X POST http://localhost:8000/api/refine \
  -H "Content-Type: application/json" \
  -d '{
    "mode": "analysis",
    "resume": "张三\n手机：138-0000-0000\n3 年后端开发经验，熟悉 Python/Go",
    "jd": "AI Infra 后端工程师\n3 年以上后端经验，Go 或 Python 精通其一",
    "current_content": "## 整体匹配度\n约 60%\n## 匹配亮点\n- 技术栈吻合\n## 缺口\n- 缺少大规模系统经验\n## 建议\n- 补充项目细节",
    "history": [],
    "instruction": "请重点分析一下在分布式系统方面的缺口"
  }'
```

Expected: A stream of `data: {"type":"reply","token":"..."}` followed by `data: {"type":"content","token":"..."}` ending with `data: [DONE]`.

- [ ] **Step 3: Verify Pydantic validation catches missing analysis**

Run:
```bash
curl -s -X POST http://localhost:8000/api/refine \
  -H "Content-Type: application/json" \
  -d '{"mode":"resume","resume":"test content 12345","jd":"test jd content 12345","current_content":"current content test 12345","history":[],"instruction":"test"}' | python -m json.tool
```

Expected: HTTP 422 with error message `"analysis is required when mode is 'resume'"`.

---

### Task 10: Smoke test — browser UI

**Files:** None (manual verification)

- [ ] **Step 1: Open http://localhost:8000 in browser**

Click "载入示例" → "开始分析匹配度" → wait for analysis to complete.

- [ ] **Step 2: Test Step 2 refine**

Click "💬 继续追问" in Step 2. Verify drawer slides in from right. Type "重点强化技术栈部分" and press Enter. Verify:
- User bubble appears immediately
- Assistant bubble streams in with reply text
- Canvas analysis content updates in real-time
- Drawer auto-scrolls

- [ ] **Step 3: Test multi-turn with back-reference**

Type "刚才那个再加强一下" and press Enter. Verify:
- Two rounds of bubbles visible
- Canvas updates again
- The second reply shows the model understood the reference

- [ ] **Step 4: Test drawer close/reopen and clear**

Close drawer (✕ button or ESC). Re-open by clicking "💬 继续追问". Verify history is preserved. Click "清空本轮对话". Verify bubbles clear but Canvas content stays.

- [ ] **Step 5: Test Step 3 refine**

Click "✅ 确认并生成优化后的简历". Wait for resume. Click "💬 继续追问" in Step 3. Send "把项目经验部分再优化一下". Verify same drawer flow works for resume.

- [ ] **Step 6: Test mobile layout**

Resize browser to < 768px width. Verify drawer appears as bottom sheet instead of right panel.

- [ ] **Step 7: Final commit if any hotfixes were needed**

```bash
git add -A
git commit -m "fix: hotfixes from smoke testing"
```
