(() => {
  const $ = (id) => document.getElementById(id);

  const resumeEl = $("resume");
  const jdEl = $("jd");
  const resumeCountEl = $("resume-count");
  const jdCountEl = $("jd-count");
  const fileNameEl = $("file-name");
  const fileInput = $("resume-file");

  const btnAnalyze = $("btn-analyze");
  const btnSample = $("btn-sample");
  const btnOptimize = $("btn-optimize");
  const btnReanalyze = $("btn-reanalyze");
  const btnCopy = $("btn-copy");
  const btnDownload = $("btn-download");
  const btnRestart = $("btn-restart");

  const analyzeStatus = $("analyze-status");
  const optimizeStatus = $("optimize-status");
  const copyStatus = $("copy-status");

  const stepAnalysis = $("step-analysis");
  const stepResult = $("step-result");
  const analysisOutput = $("analysis-output");
  const analysisSpinner = $("analysis-spinner");
  const resultPreview = $("result-preview");
  const resultSource = $("result-source");
  const resultSpinner = $("result-spinner");

  let analysisMarkdown = "";
  let resultMarkdown = "";

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

  // ---------- char counters ----------
  const updateCount = () => {
    resumeCountEl.textContent = resumeEl.value.length;
    jdCountEl.textContent = jdEl.value.length;
  };
  resumeEl.addEventListener("input", updateCount);
  jdEl.addEventListener("input", updateCount);
  updateCount();

  // ---------- file upload ----------
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files?.[0];
    if (!file) return;
    fileNameEl.textContent = `解析中: ${file.name}`;
    const form = new FormData();
    form.append("file", file);
    try {
      const res = await fetch("/api/parse", { method: "POST", body: form });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }
      const data = await res.json();
      resumeEl.value = data.text;
      updateCount();
      fileNameEl.textContent = `✅ 已解析: ${file.name} (${data.text.length} 字)`;
    } catch (e) {
      fileNameEl.textContent = `❌ 解析失败: ${e.message}`;
    }
  });

  // ---------- sample ----------
  btnSample.addEventListener("click", () => {
    resumeEl.value = SAMPLE_RESUME;
    jdEl.value = SAMPLE_JD;
    updateCount();
  });

  // ---------- SSE stream helper ----------
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

  // ---------- analyze ----------
  btnAnalyze.addEventListener("click", async () => {
    const resume = resumeEl.value.trim();
    const jd = jdEl.value.trim();
    if (resume.length < 10 || jd.length < 10) {
      analyzeStatus.textContent = "简历和 JD 都至少需要 10 个字";
      analyzeStatus.className = "status-inline error";
      return;
    }

    btnAnalyze.disabled = true;
    btnSample.disabled = true;
    btnOptimize.disabled = true;
    analyzeStatus.textContent = "分析中，正在流式生成结果……";
    analyzeStatus.className = "status-inline";
    stepAnalysis.classList.remove("hidden");
    stepResult.classList.add("hidden");
    analysisSpinner.classList.remove("hidden");
    analysisMarkdown = "";
    analysisOutput.innerHTML = "";
    stepAnalysis.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      await streamPost("/api/analyze", { resume, jd }, (token) => {
        analysisMarkdown += token;
        analysisOutput.innerHTML = marked.parse(analysisMarkdown);
      });
      analyzeStatus.textContent = "✅ 分析完成，请审阅后点击下方按钮继续。";
      analyzeStatus.className = "status-inline success";
      btnOptimize.disabled = false;
    } catch (e) {
      analyzeStatus.textContent = `❌ 分析失败: ${e.message}`;
      analyzeStatus.className = "status-inline error";
    } finally {
      analysisSpinner.classList.add("hidden");
      btnAnalyze.disabled = false;
      btnSample.disabled = false;
    }
  });

  btnReanalyze.addEventListener("click", () => {
    stepAnalysis.classList.add("hidden");
    stepResult.classList.add("hidden");
    resumeEl.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ---------- optimize ----------
  btnOptimize.addEventListener("click", async () => {
    if (!analysisMarkdown.trim()) {
      optimizeStatus.textContent = "请先完成 Step 2 的分析";
      optimizeStatus.className = "status-inline error";
      return;
    }
    const resume = resumeEl.value.trim();
    const jd = jdEl.value.trim();

    btnOptimize.disabled = true;
    btnAnalyze.disabled = true;
    optimizeStatus.textContent = "正在生成优化后的简历……";
    optimizeStatus.className = "status-inline";

    stepResult.classList.remove("hidden");
    resultSpinner.classList.remove("hidden");
    resultMarkdown = "";
    resultPreview.innerHTML = "";
    resultSource.textContent = "";
    stepResult.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      await streamPost(
        "/api/optimize",
        { resume, jd, analysis: analysisMarkdown },
        (token) => {
          resultMarkdown += token;
          resultPreview.innerHTML = marked.parse(resultMarkdown);
          resultSource.textContent = resultMarkdown;
        },
      );
      optimizeStatus.textContent = "✅ 优化完成，你可以复制或下载 Markdown 文件。";
      optimizeStatus.className = "status-inline success";
    } catch (e) {
      optimizeStatus.textContent = `❌ 生成失败: ${e.message}`;
      optimizeStatus.className = "status-inline error";
    } finally {
      resultSpinner.classList.add("hidden");
      btnOptimize.disabled = false;
      btnAnalyze.disabled = false;
    }
  });

  // ---------- tabs ----------
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      const target = btn.dataset.tab === "preview" ? resultPreview : resultSource;
      target.classList.add("active");
    });
  });

  // ---------- copy / download ----------
  btnCopy.addEventListener("click", async () => {
    if (!resultMarkdown) return;
    try {
      await navigator.clipboard.writeText(resultMarkdown);
      copyStatus.textContent = "✅ 已复制到剪贴板";
      copyStatus.className = "status-inline success";
    } catch {
      copyStatus.textContent = "❌ 复制失败，请手动从源码区复制";
      copyStatus.className = "status-inline error";
    }
    setTimeout(() => {
      copyStatus.textContent = "";
    }, 2500);
  });

  btnDownload.addEventListener("click", () => {
    if (!resultMarkdown) return;
    const blob = new Blob([resultMarkdown], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const ts = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
    const a = document.createElement("a");
    a.href = url;
    a.download = `resume-optimized-${ts}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  });

  btnRestart.addEventListener("click", () => {
    stepAnalysis.classList.add("hidden");
    stepResult.classList.add("hidden");
    analysisMarkdown = "";
    resultMarkdown = "";
    analysisOutput.innerHTML = "";
    resultPreview.innerHTML = "";
    resultSource.textContent = "";
    analyzeStatus.textContent = "";
    optimizeStatus.textContent = "";
    resumeEl.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  // ---------- sample data ----------
  const SAMPLE_RESUME = `张三
手机：138-0000-0000 · 邮箱：zhangsan@example.com · 北京

# 概要
3 年后端开发经验，熟悉 Python/Go，有一定的微服务与云原生经验，希望进入 AI 基础设施方向。

# 工作经历
## 某互联网公司 - 后端工程师（2022.06 - 至今）
- 参与电商订单系统维护，基于 Django + MySQL + Redis
- 做过一次从 MySQL 到 TiDB 的迁移
- 日常写接口、修 bug、配合前端联调

## 某外包公司 - Python 开发（2021.07 - 2022.05）
- 为政府项目开发数据上报接口
- 使用 Flask + PostgreSQL

# 项目经历
## 订单风控规则引擎
- 基于规则编排实现风控策略动态下发
- 用 Redis 缓存规则

# 教育背景
某大学 计算机科学与技术 本科 2017-2021`;

  const SAMPLE_JD = `岗位：AI Infra 后端工程师
职责：
1. 负责公司大模型推理平台的服务端开发，支撑日均数十亿次调用
2. 设计高并发、低延迟的推理调度、限流、路由系统
3. 推进多租户资源管理与计费方案
4. 与算法团队协作优化 LLM 推理成本

要求：
1. 3 年以上后端经验，Go 或 Python 精通其一
2. 熟悉 Kubernetes、gRPC、消息队列
3. 有大规模分布式系统或高并发服务的实战经验
4. 了解 LLM 推理框架（vLLM / SGLang / TensorRT-LLM）优先
5. 有 AI 平台、推理服务、模型路由经验者加分`;
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

  function openRefine(mode) {
    const other = mode === "analysis" ? "resume" : "analysis";
    refineState[other].open = false;

    refineState[mode].open = true;
    drawer.classList.add("open");
    refineInput.focus();

    refineBody.innerHTML = "";
    for (const msg of refineState[mode].history) {
      const div = document.createElement("div");
      div.className = msg.role === "user" ? "bubble bubble-user" : "bubble bubble-assistant";
      div.textContent = msg.content;
      refineBody.appendChild(div);
    }
    refineBody.scrollTop = refineBody.scrollHeight;
  }

  function closeRefine() {
    const mode = getRefineMode();
    if (mode && refineState[mode].streaming && refineAbortController) {
      refineAbortController.abort();
      refineState[mode].streaming = false;
      const lastBubble = refineBody.querySelector(".bubble-assistant:last-child");
      if (lastBubble && !lastBubble.textContent.trim()) {
        lastBubble.remove();
      }
    }
    drawer.classList.remove("open");
    if (mode) refineState[mode].open = false;
  }

  function _addBubble(role, text, extraClass) {
    const div = document.createElement("div");
    div.className = `bubble bubble-${role}` + (extraClass ? ` ${extraClass}` : "");
    div.textContent = text || "";
    refineBody.appendChild(div);
    refineBody.scrollTop = refineBody.scrollHeight;
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

    _addBubble("user", instruction);
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
    let contentBuffer = "";
    refineAbortController = new AbortController();

    try {
      await streamPost("/api/refine", body, null, {
        typed: true,
        signal: refineAbortController.signal,
        onEvent: (event) => {
          if (event.type === "reply") {
            replyBuffer += event.token;
            assistantBubble.textContent = replyBuffer;
            refineBody.scrollTop = refineBody.scrollHeight;
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

      assistantBubble.classList.remove("bubble-cursor");

      if (!replyBuffer.trim()) {
        replyBuffer = "已更新内容。";
        assistantBubble.textContent = replyBuffer;
      }

      refineState[mode].history.push(
        { role: "user", content: instruction },
        { role: "assistant", content: replyBuffer },
      );
    } catch (e) {
      if (e.name === "AbortError") {
        // User closed drawer mid-stream
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

})();
