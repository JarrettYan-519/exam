# 简历优化 Agent (Resume Optimization Agent)

一个可运行的简历优化 Agent 应用：用户提供 **简历** 与 **目标职位描述 (JD)**，系统基于 DeepSeek LLM 以流式方式给出匹配度分析（亮点 / 缺口 / 建议），在用户确认后再生成一份**优化后的简历**，并支持 Markdown 下载与复制。

整个应用被打包为一个 Docker 镜像，对外暴露 `http://localhost:8000`，按本 README 操作即可完成启动与验收。

---

## ✨ 功能特性

- **两阶段 Agent 流程**
  - Step 1 — 输入：支持纯文本粘贴 + **PDF / DOCX / Markdown / TXT** 文件上传
  - Step 2 — 匹配分析：结构化输出「整体匹配度 / 匹配亮点 / 主要缺口 / 具体优化建议」四个小节
  - Step 3 — **需用户点击「确认并生成」才会触发**：依据分析结果重写简历（纯 Markdown）
- **流式体验**：所有 LLM 响应通过 **Server-Sent Events (SSE)** 实时推送到前端，边生成边渲染
- **Markdown 导出**：一键下载 `.md` 文件 / 一键复制源码
- **单容器部署**：FastAPI 后端 + 原生 HTML 前端同镜像，无需外部依赖
- **安全**：API Key 仅通过环境变量注入，**代码中没有硬编码**；应用无状态，不保存任何简历数据
- **健壮性**：`/healthz` 健康检查、启动期 Key 校验、LLM 错误被下发到前端而不是吊死连接

---

## 🧱 技术栈

| 层级         | 选型                                                |
| ------------ | --------------------------------------------------- |
| 后端         | Python 3.12 + FastAPI + Uvicorn                     |
| LLM 客户端   | `openai` SDK（DeepSeek 兼容 OpenAI 协议）            |
| 流式协议     | Server-Sent Events（`StreamingResponse`）            |
| 文件解析     | `pypdf`（PDF）、`python-docx`（DOCX）                |
| 前端         | 原生 HTML / CSS / JavaScript + `marked` (CDN)       |
| 部署         | Docker / Docker Compose                             |

---

## 📁 目录结构

```
exam-2026/
├── Dockerfile               # 单容器构建
├── docker-compose.yml       # 推荐启动方式
├── .dockerignore
├── .env.example             # 环境变量模板
├── requirements.txt
├── README.md
├── app/                     # FastAPI 后端
│   ├── __init__.py
│   ├── main.py              # 路由入口 + SSE
│   ├── config.py            # 环境变量加载
│   ├── llm.py               # DeepSeek 流式客户端
│   ├── prompts.py           # 两段 system prompt
│   ├── parsers.py           # PDF/DOCX/MD/TXT 文本抽取
│   └── schemas.py           # Pydantic 模型
└── static/                  # 原生前端
    ├── index.html
    ├── style.css
    └── app.js
```

---

## 🔐 环境变量

| 变量                       | 必填 | 默认值                    | 说明                                          |
| -------------------------- | :--: | ------------------------- | --------------------------------------------- |
| `DEEPSEEK_API_KEY`         |  ✅  | 无                        | DeepSeek API Key，申请入口见官网              |
| `DEEPSEEK_BASE_URL`        |      | `https://api.deepseek.com`| DeepSeek API 基础地址                         |
| `DEEPSEEK_MODEL`           |      | `deepseek-chat`           | 模型名称，可改为 `deepseek-reasoner`          |
| `MAX_UPLOAD_MB`            |      | `5`                       | 文件上传大小上限                              |
| `REQUEST_TIMEOUT_SECONDS`  |      | `120`                     | 单次 LLM 调用超时时间                         |

> ⚠️ **不允许硬编码 Key**：`DEEPSEEK_API_KEY` 必须通过环境变量提供，否则应用启动失败。

---

## 🚀 快速开始

### 前置条件

- 已安装 [Docker](https://docs.docker.com/get-docker/)（含 Docker Compose v2）

### 1. 配置环境变量

```bash
cp .env.example .env
# 然后编辑 .env，把 DEEPSEEK_API_KEY 改成你的真实 Key
```

> 本次面试评估提供的 Key：`sk-40e97e965deb40ed9925c3017fe660cf`
>
> 请把它写入 `.env` 的 `DEEPSEEK_API_KEY` 字段。

### 2. 启动服务（任选一种）

#### 方式一（推荐）：docker compose

```bash
docker compose up --build
```

首次构建约需 1–2 分钟。启动成功后日志会显示：

```
Uvicorn running on http://0.0.0.0:8000
```

#### 方式二：原生 docker

```bash
docker build -t resume-agent .
docker run --rm -p 8000:8000 --env-file .env resume-agent
```

#### 方式三：本地开发（无 Docker）

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY=sk-xxxxxxxx        # 或使用 .env
uvicorn app.main:app --reload --port 8000
```

### 3. 访问应用

浏览器打开 **<http://localhost:8000>** 即可。

健康检查：

```bash
curl http://localhost:8000/healthz
# => {"status":"ok"}
```

---

## 🧑‍💻 使用流程

1. **Step 1 输入**
   - 左侧：粘贴简历文本，或点「📎 上传文件」选择 PDF / DOCX / MD / TXT，文件会被后端解析后自动回填。
   - 右侧：粘贴目标岗位 JD。
   - 不想准备素材？点击 **「载入示例」** 可以用内置样例体验全流程。
2. 点 **「🔍 开始分析匹配度」** —— 后端流式返回分析结果，包含：
   - 📊 整体匹配度（含百分比估计）
   - ✨ 匹配亮点
   - ⚠️ 主要缺口
   - 💡 具体优化建议
3. **人工确认环节**：审阅分析结果，满意后点 **「✅ 确认并生成优化后的简历」**。
   - 这一步是考题要求的"用户确认后再生成"的关键节点，系统不会自动进入下一步。
4. **Step 3 结果**：优化后的 Markdown 简历流式出现，可切换「预览 / Markdown 源码」视图。
   - 「📋 复制 Markdown」→ 粘贴到任何编辑器
   - 「⬇️ 下载 .md」→ 保存到本地（文件名自动带时间戳）

---

## 🛠 API 参考

### `GET /healthz`
健康检查，返回 `{"status":"ok"}`。

### `POST /api/parse`
解析上传的简历文件为纯文本。

- `multipart/form-data` 字段 `file`
- 支持 `.pdf` / `.docx` / `.md` / `.txt`
- 响应：`{ "filename": "...", "text": "..." }`

### `POST /api/analyze`  *(SSE)*
输入简历 + JD，流式输出匹配分析 Markdown。

请求体：
```json
{ "resume": "...", "jd": "..." }
```

响应格式（`text/event-stream`）：
```
: ping

data: "## 📊 整体"
data: "匹配度"
...
data: [DONE]
```

示例 `curl`：
```bash
curl -N -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"resume":"...","jd":"..."}'
```

### `POST /api/optimize`  *(SSE)*
在用户确认分析之后调用，流式输出优化后的 Markdown 简历。

请求体：
```json
{ "resume": "...", "jd": "...", "analysis": "...(上一步累积的 markdown)..." }
```

响应格式同 `/api/analyze`。

---

## 🧠 LLM 交互设计说明

**为什么是两步走而不是一步到位？**
考题核心诉求是"分析 → 用户**确认** → 再改写"。两次独立调用有以下好处：
1. 用户在看到匹配分析后才选择是否继续，给了明确的人工把关节点；
2. 第二次调用会把第一步的分析结果作为上下文传入，等于"先做结构化思考再写作"，质量明显高于"一次提示大模型同时分析 + 改写"；
3. 两次调用相互独立，若用户对分析不满意，可以重新编辑简历/JD 再分析，不浪费 Token。

**Prompt 设计要点**（见 `app/prompts.py`）
- **分析 Prompt** 强制模型输出固定四段 Markdown 结构（整体匹配度 / 亮点 / 缺口 / 建议），每条必须引用简历或 JD 中的原文证据，避免"空对空"。
- **改写 Prompt** 明确禁止捏造事实与数字，缺失量化指标时保留原本定性表述并追加 `[可量化]` 占位；固定输出结构（个人信息 / 概要 / 技能 / 工作经历 / 项目 / 教育），禁止寒暄。

**为什么选 SSE 而不是轮询或 WebSocket？**
DeepSeek 的 `chat.completions` 原生支持 `stream=True`，SSE 刚好是"单向、文本、基于 HTTP"的最小解；前端 `fetch + ReadableStream` 即可消费，没有额外依赖。

**错误处理**
`app/llm.py` 在遇到鉴权失败 / 限流 / 网络中断时，会**向流中下发一个 `[ERROR] ...` token 再正常结束**，前端会原样渲染出来。这样可以避免"转圈圈卡死"的糟糕体验。

---

## 🧪 验收自查清单

启动后依次验证：

- [ ] `docker compose up --build` 正常起来，日志显示 `Uvicorn running on http://0.0.0.0:8000`
- [ ] 浏览器打开 <http://localhost:8000> 看到三段式 UI
- [ ] 点「载入示例」→ 点「开始分析匹配度」→ 观察到 Markdown 分段流式出现
- [ ] 点「确认并生成优化后的简历」→ 观察到新简历流式出现
- [ ] 点「下载 .md」→ 得到本地文件且内容一致
- [ ] 上传一份 `.pdf` / `.docx` / `.md` → 文本被正确抽取回填
- [ ] `curl http://localhost:8000/healthz` 返回 `{"status":"ok"}`
- [ ] 故意不设 `DEEPSEEK_API_KEY` 启动，容器立即以清晰错误退出

---

## ⚠️ 已知限制

- **扫描件 PDF 不可识别**：仅抽取文本层，不含 OCR。对应情况请改为手动粘贴。
- **无持久化**：应用不使用数据库，任何简历/分析在容器重启后即丢失。这是刻意为之以降低部署复杂度与隐私风险。
- **无鉴权**：面试演示项目，未接入登录系统；部署到公网前请自行加鉴权或放入内网。
- **单会话并发**：一次性最多同时处理若干个简历分析，若 DeepSeek 限流会在流里下发错误 token。

---

## 📝 许可

仅用于面试评估与学习用途。
