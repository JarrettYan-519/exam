# Multi-Turn Refine Design Spec

## Overview

Add a multi-turn conversational refinement feature to the Resume Optimization Agent. After receiving initial analysis (Step 2) or an optimized resume (Step 3), users can open a chat drawer to iteratively ask for adjustments. Each turn produces both a brief Agent reply (shown in chat bubbles) and a full content update (streamed into the Canvas area).

## Decisions Made

| Decision | Choice |
|---|---|
| Which steps support refinement | Step 2 (analysis) and Step 3 (resume) |
| Output per turn | Chat reply + full content replacement (Canvas pattern) |
| LLM context per turn | Full conversation history (all prior turns) + original resume/JD + current content version |
| Session state location | Frontend only (in-memory); backend remains stateless |
| UI layout | Right-side drawer (desktop), bottom sheet (mobile <=768px) |
| Backend API | Single unified endpoint `POST /api/refine` with typed SSE events |

## Architecture

```
Browser
  Existing 3-step flow (input -> analysis -> optimize) unchanged
  New: "Continue Refining" button on Step 2 / Step 3 cards
       -> opens right-side drawer (chat bubbles + input)
       -> fetch POST /api/refine (SSE)
          -> typed events:
               {"type":"reply","token":"..."}   -> chat bubble
               {"type":"content","token":"..."} -> Canvas markdown update
               data: [DONE]

Backend
  POST /api/refine
    body: { mode, resume, jd, analysis?, current_content, history, instruction }
    -> StreamingResponse with typed SSE events
    -> LLM messages: system prompt + context + history + new instruction
    -> Marker-based state machine splits stream into reply/content segments
```

## Backend

### Endpoint: `POST /api/refine`

**Request body** (`RefineRequest`):

```python
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

### LLM Message Assembly

```python
messages = [
    {"role": "system",    "content": REFINE_ANALYSIS_PROMPT or REFINE_RESUME_PROMPT},
    {"role": "user",      "content": context_block},   # [RESUME] + [JD] + [CURRENT] + optional [ANALYSIS]
    {"role": "assistant", "content": "已理解简历与 JD，请告诉我想怎么调整。"},
    *[m.model_dump() for m in request.history],
    {"role": "user",      "content": request.instruction},
]
```

`context_block` format:
```
[RESUME]
{resume}
[JD]
{jd}
[CURRENT]
{current_content}
[ANALYSIS]        <-- only when mode=="resume"
{analysis}
```

### Output Format: Marker-Based Splitting

The system prompt forces the LLM to output:

```
<<<REPLY>>>
<1-2 sentence Chinese explanation of what was changed and why>
<<<CONTENT>>>
<complete new Markdown content>
```

**State machine** in `main.py`:

- Initial state: ` buffering` (collect until marker detected)
- On `<<<REPLY>>>`: switch to `emit_reply`, yield `{"type":"reply","token":...}`
- On `<<<CONTENT>>>`: switch to `emit_content`, yield `{"type":"content","token":...}`
- Uses a 20-character tail buffer to handle markers split across chunks
- **Fallback**: if stream ends without `<<<REPLY>>>`, treat entire output as content and inject a default reply "已更新内容"

### SSE Wire Format

```
: ping

data: {"type":"reply","token":"好的，我"}
data: {"type":"reply","token":"强化了项目经验…"}
data: {"type":"content","token":"## 项目经验\n\n"}
data: {"type":"content","token":"- **Agent 框架**：…"}
...
data: [DONE]
```

Each `data:` line is JSON-encoded. `type` is either `reply`, `content`, or `error`.

### Prompts

**`REFINE_ANALYSIS_SYSTEM_PROMPT`**: Instructs the model to refine the match analysis while preserving the four-section structure (overall match / highlights / gaps / suggestions). Must cite evidence from resume/JD. No fabrication.

**`REFINE_RESUME_SYSTEM_PROMPT`**: Inherits fabrication-prohibition and `[可量化]` placeholder rules from existing `OPTIMIZE_SYSTEM_PROMPT`. Maintains six-section resume structure. Refines based on user instruction.

Both prompts end with the same output format block:

```
输出格式（严格遵守）：
先输出 <<<REPLY>>> 标记，然后用 1-2 句中文简短说明你做了什么改动以及为什么。
再输出 <<<CONTENT>>> 标记，然后输出完整的新版 Markdown 内容。
不要输出任何其他标记或说明。
```

### New LLM Function

`app/llm.py` gains:

```python
async def stream_chat_messages(messages: list[dict]) -> AsyncIterator[str]:
```

Accepts a pre-assembled message list (unlike existing `stream_chat` which takes system+user strings). Same streaming and error handling pattern as the existing function.

## Frontend

### State Model

```js
const refineState = {
  analysis: { open: false, history: [], streaming: false },
  resume:   { open: false, history: [], streaming: false }
}
```

`history` stores completed turns as `{role, content}` pairs. The currently-streaming turn is not in history until `[DONE]`.

The global `analysisMarkdown` / `resumeMarkdown` strings remain the source of truth for Canvas content. Refine turns update these strings.

### Drawer Component

Single `#refine-drawer` DOM element, fixed positioned:

```
+----------------------------------+
| 💬 迭代优化（分析 / 简历）   ✕  |  header: title from mode
+----------------------------------+
|                                  |
|   [user bubble]                  |
|   [assistant bubble]             |  body: scrollable, auto-scroll
|   [user bubble]                  |
|   [assistant bubble ...]         |  streaming: blinking cursor
|                                  |
+----------------------------------+
| 清空本轮对话                     |
| [textarea]             [发送 ^]  |  footer: Enter=send, Shift+Enter=newline
+----------------------------------+
```

Desktop: right-side, 380px wide.
Mobile (`@media max-width: 768px`): bottom sheet, 80vh height, full width, top-only border-radius.

### Turn Flow

1. User clicks "Continue Refining" button on Step 2 or Step 3 card.
2. Drawer opens with the matching `mode`.
3. User types instruction, presses Enter or clicks Send.
4. Frontend immediately renders a user bubble and an empty assistant bubble.
5. `fetch POST /api/refine` with full payload (mode, resume, jd, analysis, current_content=latest markdown, history, instruction).
6. SSE consumption:
   - `{"type":"reply","token":"..."}` -> append text to assistant bubble
   - `{"type":"content","token":"..."}` -> append to `contentBuffer`, re-render Canvas markdown in real-time via `marked.parse()`
7. On `[DONE]`:
   - Finalize assistant bubble
   - Push user instruction and assistant reply into `refineState[mode].history`
   - Overwrite `analysisMarkdown` / `resumeMarkdown` with `contentBuffer`
   - Clear streaming flag, re-enable input

### Interactions

- Send button disabled when: instruction is empty or streaming is true
- Enter sends, Shift+Enter inserts newline
- Escape closes drawer (history preserved)
- "Clear conversation" link clears `history` only; Canvas content stays
- Closing drawer during stream: `AbortController.abort()`, discard the empty assistant bubble, do not push to history. Canvas already-replaced content is not rolled back.

### Integration with Existing Code

`streamPost()` helper gains a `typed` boolean option:
- `typed: false` (default): existing behavior, all tokens are content
- `typed: true`: parses `{"type","token"}` JSON events and calls `onEvent({type, token})` callback

Existing analyze/optimize calls continue using `typed: false`. Only refine uses `typed: true`.

### HTML Changes

- Step 2 and Step 3 card `actions` divs: add "Continue Refining" button (icon + text)
- New `<aside id="refine-drawer">` element (header, scrollable body, footer with textarea)

### CSS Changes

- `.refine-drawer`: fixed right, 380px, full height, white bg, shadow, z-index above cards
- `.refine-drawer.open`: slide-in transition
- `@media (max-width: 768px)`: bottom sheet variant
- `.bubble.user` / `.bubble.assistant`: chat bubble styles matching Apple theme
- `.refine-input`: pill-shaped textarea matching existing button style

## Error Handling

| Scenario | Behavior |
|---|---|
| DeepSeek auth/rate-limit/network failure | Emit `{"type":"error","message":"..."}` event, show red error bar on current assistant bubble, end stream normally with `[DONE]` |
| LLM omits `<<<REPLY>>>` marker | Treat entire output as content; frontend injects default reply "已更新内容"; log warning |
| LLM outputs `<<<REPLY>>>` but no `<<<CONTENT>>>` | Reply portion already emitted; remaining buffer treated as content fallback |
| Pydantic validation failure (422) | Frontend shows toast error, does not start SSE parsing |
| User closes drawer mid-stream | `AbortController.abort()`, discard incomplete assistant bubble, don't push to history, Canvas not rolled back |
| Context too long | Rely on DeepSeek error -> error event -> shown to user |

## Implementation Order

1. **Backend** (schemas -> prompts -> llm -> main) -> curl smoke test
2. **Frontend** (HTML structure -> CSS -> JS logic) -> manual browser test
3. **README update** (API reference + verification checklist)
4. **Docker rebuild** -> full manual regression

## Verification Checklist (additions to README)

- [ ] Step 2 analysis complete -> click "Continue Refining" -> drawer opens -> send "重点强化技术栈部分" -> see chat reply bubble + Canvas analysis stream-updated
- [ ] Send second turn with back-reference ("刚才那个再加强一点") -> both turns visible in chat, Canvas updates again
- [ ] Close drawer, reopen -> history preserved; click "Clear conversation" -> history cleared, Canvas unchanged
- [ ] Step 3 resume -> same drawer flow works for resume refinement
- [ ] `curl -N -X POST http://localhost:8000/api/refine ...` returns typed SSE events and `[DONE]`
