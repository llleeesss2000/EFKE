const UI_VERSION = "review-tabs-20260604-0105";

let state = {
  token: localStorage.getItem("ef_token") || "",
  user: localStorage.getItem("ef_user") || "admin",
  projects: [],
  projectSummaries: {},
  expandedProjects: new Set(),
  expandedJobs: new Set(),
  files: [],
  mode: "answer",
  folderFiles: [],
  reviewProjectId: "",
  reader: { fileId: "", meta: null, page: 1, pageData: null, mode: "overlay", filter: "all" },
};

const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const stageLabels = {
  upload: "上傳",
  metadata: "Metadata 建立",
  layout_analysis: "版面分析 / 文字抽取",
  ocr: "OCR 文字辨識",
  image_extract: "圖片擷取",
  image_caption: "圖片說明",
  image_embedding: "圖片向量化",
  table_extract: "表格抽取",
  formula_extract: "公式抽取",
  chunk: "文字切塊",
  text_embedding: "文字索引 / 向量化",
  rerank_ready: "重排準備",
  index: "建立搜尋索引",
  ai_suggestion: "AI 自動整理",
  done: "完成",
  failed: "失敗",
};
const statusLabels = {
  queued: "排隊中",
  processing: "處理中",
  completed: "完成",
  done: "完成",
  failed: "失敗",
  not_implemented: "尚未接入",
};
const configMeta = {
  server_api_url: ["Server API 位址", "User 端會把登入、專案、上傳、查詢都送到這個 Server。請在 .env 的 SERVER_API_URL 修改。"],
  quantized_data_location: ["量化資料位置", "server 表示衍生資料保存在 Server；user 表示可攜式資料保存在這台 User。"],
  user_data_dir: ["User 本地資料夾", "QUANTIZED_DATA_LOCATION=user 時使用，用於 metadata cache 或可攜式資料。"],
};

const llmPresets = {
  ollama: { url: "http://127.0.0.1:11434", key: "", placeholder: "Ollama 不需要 API Key" },
  openai: { url: "https://api.openai.com/v1", key: "", placeholder: "sk-..." },
  anthropic: { url: "https://api.anthropic.com", key: "", placeholder: "sk-ant-..." },
  google: { url: "https://generativelanguage.googleapis.com/v1beta", key: "", placeholder: "AIza..." },
  deepseek: { url: "https://api.deepseek.com/v1", key: "", placeholder: "sk-..." },
  "openai-compat": { url: "", key: "", placeholder: "輸入你的 API Key" },
};

function normalizeUrl(input) {
  if (!input) return input;
  input = input.trim();
  if (/^https?:\/\//i.test(input)) return input;
  return "http://" + input;
}

const api = async (path, options = {}) => {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  if (state.token) headers["Authorization"] = `Bearer ${state.token}`;
  const res = await fetch(path, { headers, ...options });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

function formatDuration(seconds = 0) {
  const value = Number(seconds) || 0;
  if (value < 1) return "不到 1 秒";
  if (value < 60) return `${Math.round(value)} 秒`;
  const minutes = Math.floor(value / 60);
  const rest = Math.round(value % 60);
  if (minutes < 60) return `${minutes} 分 ${rest} 秒`;
  const hours = Math.floor(minutes / 60);
  return `${hours} 小時 ${minutes % 60} 分`;
}

function countLabel(value, unit = "") {
  return `${Number(value || 0).toLocaleString()}${unit}`;
}

async function switchView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.add("hidden"));
  document.querySelectorAll(".rail button").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  $("#" + name).classList.remove("hidden");
  $("#viewTitle").textContent = { query: "查詢", wiki: "知識維基", projects: "專案管理", review: "書籍校閱", reader: "書籍閱讀器", upload: "檔案上傳", files: "檔案 / 書籍管理", jobs: "工作進度", settings: "系統設定", accounts: "帳號管理" }[name];
  if (name === "wiki") {
    await loadWikiProjects();
    await loadWiki();
    return;
  }
  if (name === "review") {
    await ensureReviewData();
    renderReview();
    return;
  }
  if (name !== "reader") await refresh();
}

function renderProjects() {
  const rows = state.projects.map((p) => {
    const summary = state.projectSummaries[p.id];
    const totals = summary?.totals || {};
    const expanded = state.expandedProjects.has(p.id);
    return `
    <article class="project-card ${expanded ? "expanded" : ""}" data-toggle-project="${escapeHtml(p.id)}">
      <div class="project-head action-row">
        <div>
          <strong>${escapeHtml(p.name)}</strong>
          <span>${escapeHtml(p.template)} / ${escapeHtml(p.source_rank)} 級 / ${escapeHtml(p.id)}</span>
          <div class="metric-line">
            <span>書籍 ${countLabel(totals.files)}</span>
            <span>文字 ${countLabel(totals.text_blocks)}</span>
            <span>圖片 ${countLabel(totals.images)}</span>
            <span>圖片向量 ${countLabel(totals.image_embeddings)}</span>
            <span>AI 整理 ${countLabel(totals.ai_summaries)}</span>
          </div>
        </div>
        <div class="row-actions">
          <button class="ghost small-btn" type="button">${expanded ? "收合" : "檢查內容"}</button>
          <button class="danger small-btn" data-delete-project="${escapeHtml(p.id)}" data-project-name="${escapeHtml(p.name)}">刪除</button>
        </div>
      </div>
      ${expanded ? renderProjectSummary(summary) : ""}
    </article>`;
  }).join("");
  $("#projectList").innerHTML = rows || "尚未建立專案。";
  renderProjectChips();
  const opts = state.projects.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
  $("#uploadProject").innerHTML = opts;
  const current = $("#fileProjectFilter").value;
  $("#fileProjectFilter").innerHTML = state.projects.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
  if (current && state.projects.some((p) => p.id === current)) $("#fileProjectFilter").value = current;
}

state.selectedProjects = new Set();

function renderProjectChips() {
  const container = $("#projectChips");
  if (!state.projects.length) {
    container.innerHTML = '<span class="chip-hint">建立專案後可選擇搜尋範圍</span>';
    return;
  }
  container.innerHTML = state.projects.map((p) => {
    const active = state.selectedProjects.has(p.id);
    return `<button type="button" class="chip ${active ? "active" : ""}" data-project-id="${escapeHtml(p.id)}">
      <span class="chip-check">${active ? "✓" : ""}</span> ${escapeHtml(p.name)}
    </button>`;
  }).join("") + '<button type="button" class="chip" id="selectAllChip">全部</button>';
}

$("#projectChips").addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (!chip) return;
  if (chip.id === "selectAllChip") {
    if (state.selectedProjects.size === state.projects.length) {
      state.selectedProjects.clear();
    } else {
      state.projects.forEach((p) => state.selectedProjects.add(p.id));
    }
  } else {
    const id = chip.dataset.projectId;
    if (state.selectedProjects.has(id)) state.selectedProjects.delete(id);
    else state.selectedProjects.add(id);
  }
  renderProjectChips();
});

async function refresh() {
  try {
    const config = await api("/api/config");
    $("#serverState").textContent = `Server: ${config.server_api_url}`;
    $("#configList").innerHTML = Object.entries(config).map(([k, v]) => {
      const meta = configMeta[k] || [k, "請參考 .env 設定。"];
      return `<dt><code>${k}</code><span>${meta[0]}</span></dt><dd><strong>${v || "未設定"}</strong><small>${meta[1]}</small></dd>`;
    }).join("");
    state.projects = await api("/api/projects");
    const summaries = await Promise.all(state.projects.map(async (p) => {
      try {
        return [p.id, await api(`/api/projects/${p.id}/summary`)];
      } catch {
        return [p.id, null];
      }
    }));
    state.projectSummaries = Object.fromEntries(summaries);
    renderProjects();
    const jobs = await api("/api/jobs");
    if (jobs.length) {
      $("#jobList").innerHTML = jobs.map(renderJob).join("");
      $("#jobEmpty").classList.add("hidden");
    } else {
      $("#jobList").innerHTML = "";
      $("#jobEmpty").classList.remove("hidden");
    }
    state.files = await api("/api/files");
    renderFiles();
    renderReview();
    const users = await api("/api/users");
    $("#userTable").innerHTML = users.map((u) => `
      <div class="user-row">
        <span class="user-row-name">${escapeHtml(u.username)}</span>
        <span class="user-row-role ${escapeHtml(u.role)}">${escapeHtml(u.role)}</span>
        <span style="font-size:12px;color:var(--muted)">${u.must_change_password ? "需改密碼" : ""}</span>
        <div class="user-row-actions">
          <button class="ghost small-btn" data-edit-user="${escapeHtml(u.id)}" data-username="${escapeHtml(u.username)}" data-role="${escapeHtml(u.role)}" type="button">編輯</button>
        </div>
      </div>`).join("") || '<p style="color:var(--muted)">尚無使用者</p>';
  } catch (err) {
    $("#serverState").textContent = "Server 無法連線";
  }
}

async function ensureReviewData() {
  try {
    const config = await api("/api/config");
    $("#serverState").textContent = `Server: ${config.server_api_url}`;
    state.projects = await api("/api/projects");
    state.files = await api("/api/files");
    const summaries = await Promise.all(state.projects.map(async (p) => {
      try {
        return [p.id, await api(`/api/projects/${p.id}/summary`)];
      } catch {
        return [p.id, null];
      }
    }));
    state.projectSummaries = Object.fromEntries(summaries);
  } catch (err) {
    $("#serverState").textContent = "Server 無法連線";
    $("#reviewProjectTabs").innerHTML = `<button class="review-project-tab" type="button" data-review-reload="1">重新載入校閱資料</button>`;
    $("#reviewBookList").innerHTML = `<p class="warn">校閱資料載入失敗：${escapeHtml(err.message)}</p>`;
  }
}

function renderReview() {
  if ($("#clientVersion")) $("#clientVersion").textContent = `UI 版本：${UI_VERSION}`;
  if (!state.reviewProjectId || !state.projects.some((p) => p.id === state.reviewProjectId)) {
    state.reviewProjectId = (state.projects[0] && state.projects[0].id) || "";
  }
  $("#reviewProjectTabs").innerHTML = state.projects.map((project) => {
    const summary = state.projectSummaries[project.id];
    const total = summary?.totals?.files ?? state.files.filter((file) => file.project_id === project.id).length;
    const active = project.id === state.reviewProjectId;
    return `<button class="review-project-tab ${active ? "active" : ""}" type="button" data-review-project="${escapeHtml(project.id)}">
      <strong>${escapeHtml(project.name)}</strong>
      <span>${countLabel(total)} 本</span>
    </button>`;
  }).join("") || "尚未建立專案。";
  const selectedProject = state.reviewProjectId;
  const keyword = ($("#reviewSearchInput").value || "").trim().toLowerCase();
  const files = state.files.filter((file) => {
    const projectMatch = selectedProject ? file.project_id === selectedProject : true;
    const keywordMatch = keyword ? file.filename.toLowerCase().includes(keyword) : true;
    return projectMatch && keywordMatch;
  });
  if (!selectedProject) {
    $("#reviewBookList").innerHTML = "請先建立專案。";
    return;
  }
  $("#reviewBookList").innerHTML = files.map((file) => {
    const project = state.projects.find((p) => p.id === file.project_id);
    const type = /\.pdf$/i.test(file.filename) ? "PDF 疊圖校閱" : (/\.epub$/i.test(file.filename) ? "EPUB 全文閱讀" : "文字檔閱讀");
    return `<article class="review-book">
      <div>
        <strong>${escapeHtml(file.filename)}</strong>
        <div class="meta"><span>專案：${escapeHtml(project?.name || file.project_id)}</span><span>狀態：${statusLabels[file.status] || file.status}</span><span>${type}</span></div>
        <small>${escapeHtml(file.id)}</small>
      </div>
      <button class="small-btn" type="button" data-open-reader="${escapeHtml(file.id)}">開始校閱</button>
    </article>`;
  }).join("") || "此專案目前沒有書籍。";
}

function renderProjectSummary(summary) {
  if (!summary) return `<div class="project-detail warn">無法讀取此專案內容摘要。</div>`;
  const files = summary.files || [];
  if (!files.length) return `<div class="project-detail">此專案尚未匯入書籍或圖片。</div>`;
  return `<div class="project-detail">
    ${files.map((file) => {
      const counts = file.counts || {};
      const images = (file.samples?.images || []).map((img) => `
        <figure>
          <img src="/api/assets/${escapeHtml(img.id)}" alt="${escapeHtml(img.caption || "擷取圖片")}" loading="lazy" />
          <figcaption>頁 ${escapeHtml(img.page_number || "-")} / ${escapeHtml(img.caption || "尚無圖片說明")} / ${statusLabels[img.embedding_status] || img.embedding_status || "未向量化"}</figcaption>
        </figure>`).join("");
      const text = (file.samples?.text || []).map((item) => `<p><strong>頁 ${escapeHtml(item.page_number || "-")} ${escapeHtml(item.block_type || "")}</strong>${escapeHtml(item.content || "").slice(0, 360)}</p>`).join("");
      return `<section class="project-file">
        <header>
          <strong>${escapeHtml(file.filename)}</strong>
          <span>狀態：${statusLabels[file.status] || escapeHtml(file.status)} / 上傳：${escapeHtml(file.uploaded_at || "")}</span>
        </header>
        <div class="metric-line">
          <span>文字 ${countLabel(counts.text_blocks)}</span>
          <span>切塊 ${countLabel(counts.chunks)}</span>
          <span>表格 ${countLabel(counts.tables)}</span>
          <span>公式 ${countLabel(counts.formulas)}</span>
          <span>圖片 ${countLabel(counts.images)}</span>
          <span>圖片向量 ${countLabel(counts.image_embeddings)}</span>
        </div>
        ${file.ai_summary ? `<div class="ai-summary"><strong>AI 自動整理</strong><p>${escapeHtml(file.ai_summary)}</p></div>` : `<p class="warn">尚無 AI 自動整理。</p>`}
        <div class="content-samples">
          <div><h4>內容抽樣</h4>${text || "<p>尚無可檢查文字。</p>"}</div>
          <div><h4>圖片抽樣</h4><div class="image-grid">${images || "<p>尚無擷取圖片。</p>"}</div></div>
        </div>
        <div class="row-actions reader-open-line"><button class="small-btn" type="button" data-open-reader="${escapeHtml(file.id)}">閱讀 / 校對</button></div>
      </section>`;
    }).join("")}
  </div>`;
}

function renderFile(file) {
  const project = state.projects.find((p) => p.id === file.project_id);
  return `<div class="row action-row">
    <div>
      <strong>${file.filename}</strong>
      <span>專案：${project ? project.name : file.project_id} / 狀態：${statusLabels[file.status] || file.status} / 上傳：${file.uploaded_at}</span>
      <small>${file.id}</small>
    </div>
    <div class="row-actions">
      <button class="small-btn" data-open-reader="${escapeHtml(file.id)}" type="button">閱讀 / 校對</button>
      <button class="danger small-btn" data-delete-file="${file.id}" data-file-name="${file.filename}">刪除</button>
    </div>
  </div>`;
}

function renderFiles() {
  const selectedProject = $("#fileProjectFilter").value || (state.projects[0] && state.projects[0].id) || "";
  if (selectedProject && $("#fileProjectFilter").value !== selectedProject) $("#fileProjectFilter").value = selectedProject;
  const keyword = ($("#fileSearchInput").value || "").trim().toLowerCase();
  const filtered = state.files.filter((file) => {
    const sameProject = selectedProject ? file.project_id === selectedProject : false;
    const matchKeyword = keyword ? file.filename.toLowerCase().includes(keyword) : true;
    return sameProject && matchKeyword;
  });
  $("#fileResultCount").textContent = `${filtered.length} 本`;
  if (!selectedProject) {
    $("#fileList").innerHTML = "請先建立或選擇專案。";
    return;
  }
  $("#fileList").innerHTML = filtered.map(renderFile).join("") || "此專案沒有符合條件的書籍。";
}

function renderJob(job) {
  const stagesList = job.stages || [];
  const completed = stagesList.filter((s) => ["completed", "not_implemented", "failed"].includes(s.status)).length;
  const failed = stagesList.filter((s) => s.status === "failed").length;
  const total = Math.max(stagesList.length, 1);
  const percent = Number(job.percent ?? (failed ? 100 : Math.round((completed / total) * 100)));
  const expanded = state.expandedJobs.has(job.id);
  const statusClass = job.status === "done" ? "done" : job.status === "failed" ? "failed" : job.status === "processing" ? "processing" : "queued";
  const statusText = { done: "完成", failed: "失敗", processing: "處理中", queued: "排隊中" }[job.status] || job.status;
  const currentStage = stageLabels[job.current_stage] || job.current_stage;
  const stages = stagesList.map((s) => {
    const stageName = stageLabels[s.stage] || s.stage;
    const dotClass = s.status;
    return `<div class="job-stage">
      <span class="job-stage-dot ${escapeHtml(dotClass)}"></span>
      <span class="job-stage-name">${escapeHtml(stageName)}</span>
      <span class="job-stage-info">${formatDuration(s.elapsed_seconds)}</span>
    </div>`;
  }).join("");
  return `<div class="job-card">
    <div class="job-card-header">
      <div class="job-card-title">
        <span>${escapeHtml(job.filename)}</span>
      </div>
      <div style="display:flex;gap:6px;align-items:center;">
        <span class="job-status-badge ${statusClass}">${statusText}</span>
        <button class="ghost small-btn" data-toggle-job="${escapeHtml(job.id)}" type="button">${expanded ? "收合" : "展開"}</button>
        <button class="danger small-btn" data-delete-job="${escapeHtml(job.id)}" type="button">移除</button>
      </div>
    </div>
    <div class="job-card-progress"><span style="width:${percent}%"></span></div>
    <div class="job-card-meta">
      <span>專案：${escapeHtml(job.project_name)}</span>
      <span>階段：${completed}/${total}</span>
      <span>耗時：${formatDuration(job.elapsed_seconds)}</span>
    </div>
    ${expanded ? `<div class="job-card-stages">${stages || "尚無階段紀錄"}</div>` : ""}
  </div>`;
}

function renderEvidence(items) {
  $("#evidenceList").innerHTML = items.map((ev, i) => `
    <article class="evidence">
      <strong>#${i + 1} ${ev.source_file}</strong>
      <div class="meta"><span>頁 ${ev.page_number}</span><span>區塊 ${ev.block_id}</span><span>rerank ${ev.rerank_score}</span><span>${ev.project}</span><span>${ev.source_rank} 級</span></div>
      <p>${ev.evidence_text}</p>
    </article>`).join("") || "資料庫中未找到足夠證據。";
}

function pageStatusLabel(status) {
  return { ok: "正常", low_text: "低字數", missing: "缺文字" }[status] || status;
}

function blockClass(type) {
  if (type === "table") return "table";
  if (type === "formula") return "formula";
  if (type === "ocr_text") return "ocr";
  return "text";
}

async function openReader(fileId, page = 1) {
  state.reader.fileId = fileId;
  state.reader.page = page;
  state.reader.meta = await api(`/api/files/${fileId}/reader`);
  state.reader.mode = /\.pdf$/i.test(state.reader.meta.file.filename || "") ? "overlay" : "text";
  switchView("reader");
  syncReaderControls();
  renderReaderShell();
  await loadReaderPage(page);
}

function syncReaderControls() {
  document.querySelectorAll("[data-reader-mode]").forEach((item) => {
    const active = item.dataset.readerMode === state.reader.mode;
    item.classList.toggle("active", active);
    item.classList.toggle("ghost", !active);
  });
  document.querySelectorAll("[data-page-filter]").forEach((item) => {
    const active = item.dataset.pageFilter === state.reader.filter;
    item.classList.toggle("active", active);
    item.classList.toggle("ghost", !active);
  });
}

function renderReaderShell() {
  const meta = state.reader.meta;
  if (!meta) return;
  $("#readerTitle").textContent = meta.file.filename;
  $("#readerMeta").innerHTML = `
    <span>專案：${escapeHtml(meta.project?.name || "")}</span>
    <span>頁數：${countLabel(meta.totals.pages)}</span>
    <span>文字：${countLabel(meta.totals.chars)}</span>
    <span>缺文字頁：${countLabel(meta.totals.missing_pages)}</span>
    <span>低字數頁：${countLabel(meta.totals.low_text_pages)}</span>
    <span>圖片：${countLabel(meta.totals.assets)}</span>`;
  $("#readerIssueSummary").innerHTML = `
    <span>缺文字 ${countLabel(meta.totals.missing_pages)}</span>
    <span>低字數 ${countLabel(meta.totals.low_text_pages)}</span>
    <span>總頁 ${countLabel(meta.totals.pages)}</span>
    <span>區塊 ${countLabel(meta.totals.blocks)}</span>`;
  $("#readerPageTotal").textContent = `/ ${meta.totals.pages}`;
  renderReaderPageList();
}

function renderReaderPageList() {
  const meta = state.reader.meta;
  if (!meta) return;
  const pages = state.reader.filter === "issues" ? meta.pages.filter((p) => p.status !== "ok") : meta.pages;
  $("#readerPageList").innerHTML = pages.map((page) => `
    <button class="reader-page-btn ${page.page_number === state.reader.page ? "active" : ""} ${page.status}" data-reader-page="${page.page_number}" type="button">
      <strong>${page.page_number}</strong>
      <span>${countLabel(page.chars)} 字 / ${pageStatusLabel(page.status)}</span>
    </button>`).join("") || "沒有符合條件的頁面。";
}

async function loadReaderPage(page) {
  const meta = state.reader.meta;
  if (!meta) return;
  const maxPage = meta.totals.pages || 1;
  const nextPage = Math.max(1, Math.min(maxPage, Number(page) || 1));
  state.reader.page = nextPage;
  $("#readerPageInput").value = nextPage;
  state.reader.pageData = await api(`/api/files/${state.reader.fileId}/pages/${nextPage}`);
  renderReaderPageList();
  renderReaderPage();
}

function renderReaderPage() {
  const data = state.reader.pageData;
  if (!data) return;
  const page = data.page;
  const blocks = data.blocks || [];
  const assets = data.assets || [];
  const mode = state.reader.mode;
  const isPdf = /\.pdf$/i.test(data.file.filename || "");
  const image = isPdf && mode !== "rebuild" && mode !== "text"
    ? `<img class="reader-page-image" src="/api/files/${escapeHtml(data.file.id)}/pages/${page.page_number}/image?t=${Date.now()}" alt="PDF page ${page.page_number}" />`
    : "";
  const boxes = mode !== "original" && mode !== "text" ? blocks.filter((b) => b.bbox_values).map((block) => {
    const [x1, y1, x2, y2] = block.bbox_values;
    const left = (x1 / page.width) * 100;
    const top = (y1 / page.height) * 100;
    const width = ((x2 - x1) / page.width) * 100;
    const height = ((y2 - y1) / page.height) * 100;
    return `<div class="ocr-box ${blockClass(block.block_type)}" style="left:${left}%;top:${top}%;width:${width}%;height:${height}%;" title="${escapeHtml(block.block_type)} / ${escapeHtml(block.content).slice(0, 120)}"></div>`;
  }).join("") : "";
  const textBlocks = blocks.filter((b) => (b.content || "").trim());
  if (mode === "text") {
    $("#readerCanvasWrap").innerHTML = `<article class="reader-fulltext">${textBlocks.map((b) => `<p><span>頁 ${page.page_number} / ${escapeHtml(b.block_type)}</span>${escapeHtml(b.content)}</p>`).join("") || "此頁沒有 OCR 文字。"}</article>`;
  } else {
    $("#readerCanvasWrap").innerHTML = `
      <div class="reader-page-canvas ${mode}" style="aspect-ratio:${page.width}/${page.height};">
        ${image}
        ${boxes}
      </div>`;
  }
  $("#readerPageStats").innerHTML = `
    <span>頁 ${page.page_number}</span>
    <span>區塊 ${countLabel(blocks.length)}</span>
    <span>文字 ${countLabel(textBlocks.reduce((sum, b) => sum + (b.content || "").length, 0))}</span>
    <span>圖片 ${countLabel(assets.length)}</span>`;
  $("#readerPageText").innerHTML = textBlocks.map((b) => `<p><strong>${escapeHtml(b.block_type)} · ${escapeHtml(b.block_id)}</strong>${escapeHtml(b.content)}</p>`).join("") || "此頁沒有 OCR 文字。";
  $("#readerBlocks").innerHTML = blocks.map((b) => `<div class="reader-block-item ${blockClass(b.block_type)}"><strong>${escapeHtml(b.block_type)}</strong><span>${escapeHtml(b.block_id)}</span><p>${escapeHtml(b.content || "").slice(0, 260)}</p></div>`).join("") || "此頁沒有區塊。";
  $("#readerAssets").innerHTML = assets.map((asset) => `<figure><img src="/api/assets/${escapeHtml(asset.id)}" loading="lazy" /><figcaption>${escapeHtml(asset.caption || "無說明")}</figcaption></figure>`).join("") || "此頁沒有圖片資產。";
}

if ($("#clientVersion")) $("#clientVersion").textContent = `UI 版本：${UI_VERSION}`;

async function checkSetup() {
  try {
    const res = await fetch("/api/setup/status");
    const data = await res.json();
    if (!data.configured) {
      $("#login").classList.add("hidden");
      $("#setup").classList.remove("hidden");
      return true;
    }
  } catch (_) {}
  return false;
}

$("#testServerBtn").addEventListener("click", async () => {
  const url = normalizeUrl(document.querySelector("#setupForm input[name='server_url']").value);
  if (!url) { $("#setupMsg").textContent = "請輸入 Server 位址"; return; }
  $("#setupMsg").textContent = "正在測試連線...";
  try {
    const res = await fetch("/api/setup/test-server", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ server_url: url }) });
    const data = await res.json();
    if (data.ok) {
      $("#setupMsg").textContent = "✓ 連線成功！Server 狀態正常。";
    } else {
      $("#setupMsg").textContent = "✗ 連線失敗：" + (data.error || "無法連線");
    }
  } catch (err) {
    $("#setupMsg").textContent = "✗ 測試失敗：" + err.message;
  }
});

$("#setupLlmProvider").addEventListener("change", () => {
  const preset = llmPresets[$("#setupLlmProvider").value] || {};
  if (preset.url) $("#setupLlmUrl").value = preset.url;
  if (preset.key !== undefined) $("#setupLlmKey").placeholder = preset.placeholder || "";
});

$("#setupLlmTestBtn").addEventListener("click", async () => {
  const body = {
    provider: $("#setupLlmProvider").value,
    base_url: normalizeUrl($("#setupLlmUrl").value),
    api_key: $("#setupLlmKey").value,
    model: "",
  };
  if (!body.base_url) { $("#setupLlmMsg").textContent = "請輸入 LLM API 位址"; return; }
  $("#setupLlmMsg").textContent = "正在測試連線...";
  try {
    const res = await fetch("/api/llm/test", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (data.ok) {
      const select = $("#setupLlmModelSelect");
      select.innerHTML = "";
      if (data.models && data.models.length > 0) {
        data.models.forEach((m) => { const opt = document.createElement("option"); opt.value = m; opt.textContent = m; select.appendChild(opt); });
        $("#setupLlmMsg").textContent = `✓ 連線成功！找到 ${data.models.length} 個模型，請選擇一個。`;
      } else {
        select.innerHTML = '<option value="">未找到模型</option>';
        $("#setupLlmMsg").textContent = "✓ 連線成功，但未找到可用模型。";
      }
    } else {
      $("#setupLlmMsg").textContent = "✗ " + (data.error || data.detail || "連線失敗，請確認位址正確");
    }
  } catch (err) {
    $("#setupLlmMsg").textContent = "✗ 測試失敗：" + (err.message || "無法連線到 Server");
  }
});

$("#setupLlmQueryBtn").addEventListener("click", async () => {
  const model = $("#setupLlmModelManual").value || $("#setupLlmModelSelect").value;
  if (!model) { $("#setupLlmMsg").textContent = "請先選擇或輸入模型名稱"; return; }
  const body = {
    provider: $("#setupLlmProvider").value,
    base_url: normalizeUrl($("#setupLlmUrl").value),
    api_key: $("#setupLlmKey").value,
    model: model,
  };
  $("#setupLlmMsg").textContent = "正在測試問答...";
  try {
    const res = await fetch("/api/llm/test-query", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json();
    if (data.ok) {
      $("#setupLlmMsg").textContent = `✓ 模型回答：${data.answer}`;
    } else {
      $("#setupLlmMsg").textContent = "✗ " + data.error;
    }
  } catch (err) {
    $("#setupLlmMsg").textContent = "✗ 問答失敗：" + err.message;
  }
});

$("#setupForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const serverUrl = normalizeUrl(document.querySelector("#setupForm input[name='server_url']").value);
  const llmModel = $("#setupLlmModelManual").value || $("#setupLlmModelSelect").value;
  const body = {
    server_url: serverUrl,
    llm_url: normalizeUrl($("#setupLlmUrl").value),
    llm_model: llmModel,
  };
  try {
    await fetch("/api/setup/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("#setupFinalMsg").textContent = "✓ 設定已保存！請重新啟動 User 服務後再登入。";
  } catch (err) {
    $("#setupFinalMsg").textContent = "儲存失敗：" + err.message;
  }
});

const skipSetup = false;
checkSetup().then((v) => { if (v) throw "setup"; }).catch(() => {});

$("#loginForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    const result = await api("/api/auth/login", { method: "POST", body: JSON.stringify(data) });
    state.token = result.token;
    state.user = result.user.username;
    localStorage.setItem("ef_token", result.token);
    localStorage.setItem("ef_user", result.user.username);
    $("#login").classList.add("hidden");
    $("#app").classList.remove("hidden");
    if (result.user.must_change_password) {
      $("#serverState").textContent = "⚠ 首次登入，請在帳號管理中修改預設密碼";
      switchView("accounts");
    }
    refresh();
  } catch (err) {
    $("#loginMsg").textContent = "登入失敗：" + err.message;
  }
});

document.querySelectorAll(".rail button").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
$("#refreshBtn").addEventListener("click", refresh);
$("#logoutBtn").addEventListener("click", async () => {
  try { await api("/api/auth/logout", { method: "POST", body: "{}" }); } catch (_) {}
  state.token = "";
  localStorage.removeItem("ef_token");
  localStorage.removeItem("ef_user");
  $("#app").classList.add("hidden");
  $("#login").classList.remove("hidden");
});

document.querySelectorAll(".pill[data-mode]").forEach((btn) => {
  btn.addEventListener("click", () => {
    state.mode = btn.dataset.mode;
    document.querySelectorAll(".pill[data-mode]").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  });
});

$("#projectForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  await api("/api/projects", { method: "POST", body: JSON.stringify(data) });
  event.target.reset();
  refresh();
});

$("#projectList").addEventListener("click", async (event) => {
  const readerButton = event.target.closest("[data-open-reader]");
  if (readerButton) {
    event.stopPropagation();
    await openReader(readerButton.dataset.openReader);
    return;
  }
  const button = event.target.closest("[data-delete-project]");
  if (!button) {
    const card = event.target.closest("[data-toggle-project]");
    if (!card) return;
    const id = card.dataset.toggleProject;
    if (state.expandedProjects.has(id)) state.expandedProjects.delete(id);
    else state.expandedProjects.add(id);
    renderProjects();
    return;
  }
  const id = button.dataset.deleteProject;
  const name = button.dataset.projectName;
  if (!confirm(`確定要刪除專案「${name}」？\n這會移除該專案的工作、metadata、索引與專案原始檔目錄。`)) return;
  const typed = prompt("請輸入「刪除」確認。");
  if (typed !== "刪除") return;
  try {
    const result = await api(`/api/projects/${id}`, { method: "DELETE" });
    $("#projectMsg").textContent = result.message;
    refresh();
  } catch (err) {
    alert("刪除失敗：" + err.message);
  }
});

$("#jobList").addEventListener("click", async (event) => {
  const button = event.target.closest("[data-delete-job]");
  if (!button) {
    const card = event.target.closest("[data-toggle-job]");
    if (!card) return;
    const id = card.dataset.toggleJob;
    if (state.expandedJobs.has(id)) state.expandedJobs.delete(id);
    else state.expandedJobs.add(id);
    refresh();
    return;
  }
  const id = button.dataset.deleteJob;
  if (!confirm("確定要移除此工作進度紀錄？\n原始檔、metadata 與索引不會被刪除。")) return;
  try {
    await api(`/api/jobs/${id}`, { method: "DELETE" });
    refresh();
  } catch (err) {
    alert("移除工作失敗：" + err.message);
  }
});

$("#fileList").addEventListener("click", async (event) => {
  const readerButton = event.target.closest("[data-open-reader]");
  if (readerButton) {
    await openReader(readerButton.dataset.openReader);
    return;
  }
  const button = event.target.closest("[data-delete-file]");
  if (!button) return;
  const id = button.dataset.deleteFile;
  const name = button.dataset.fileName;
  if (!confirm(`確定要刪除檔案/書籍「${name}」？\n這會移除原始檔、metadata、工作紀錄、區塊、chunk、assets 與衍生資料。`)) return;
  const typed = prompt("請輸入「刪除」確認。");
  if (typed !== "刪除") return;
  try {
    const result = await api(`/api/files/${id}`, { method: "DELETE" });
    alert(result.message);
    refresh();
  } catch (err) {
    alert("刪除檔案失敗：" + err.message);
  }
});
$("#fileProjectFilter").addEventListener("change", renderFiles);
$("#fileSearchInput").addEventListener("input", renderFiles);
$("#reviewSearchInput").addEventListener("input", renderReview);
$("#reviewProjectTabs").addEventListener("click", (event) => {
  const reloadButton = event.target.closest("[data-review-reload]");
  if (reloadButton) {
    ensureReviewData().then(renderReview);
    return;
  }
  const button = event.target.closest("[data-review-project]");
  if (!button) return;
  state.reviewProjectId = button.dataset.reviewProject;
  renderReview();
});
$("#reviewBookList").addEventListener("click", async (event) => {
  const readerButton = event.target.closest("[data-open-reader]");
  if (!readerButton) return;
  await openReader(readerButton.dataset.openReader);
});

$("#readerBackBtn").addEventListener("click", () => switchView("review"));
$("#readerPrevBtn").addEventListener("click", () => loadReaderPage(state.reader.page - 1));
$("#readerNextBtn").addEventListener("click", () => loadReaderPage(state.reader.page + 1));
$("#readerPageInput").addEventListener("change", (event) => loadReaderPage(event.target.value));
$("#readerPageList").addEventListener("click", (event) => {
  const button = event.target.closest("[data-reader-page]");
  if (!button) return;
  loadReaderPage(button.dataset.readerPage);
});
document.querySelectorAll("[data-reader-mode]").forEach((button) => button.addEventListener("click", () => {
  state.reader.mode = button.dataset.readerMode;
  document.querySelectorAll("[data-reader-mode]").forEach((item) => {
    item.classList.toggle("active", item === button);
    item.classList.toggle("ghost", item !== button);
  });
  renderReaderPage();
}));
document.querySelectorAll("[data-page-filter]").forEach((button) => button.addEventListener("click", () => {
  state.reader.filter = button.dataset.pageFilter;
  document.querySelectorAll("[data-page-filter]").forEach((item) => {
    item.classList.toggle("active", item === button);
    item.classList.toggle("ghost", item !== button);
  });
  renderReaderPageList();
}));

const allowedUpload = (file) => /\.(pdf|txt|jpe?g|png|epub)$/i.test(file.name);

function renderUploadProgress({ text, detail = "", done = 0, total = state.folderFiles.length, percent = 0 }) {
  $("#folderProgressText").textContent = text;
  $("#folderProgressCount").textContent = `${done} / ${total}`;
  $("#folderProgressDetail").textContent = detail;
  $("#folderProgressBar").style.width = `${Math.max(0, Math.min(100, percent))}%`;
}

function setFolderFiles(files) {
  state.folderFiles = Array.from(files).filter(allowedUpload);
  const skipped = Array.from(files).length - state.folderFiles.length;
  if (state.folderFiles.length) {
    $("#filePreview").classList.remove("hidden");
    $("#filePreviewCount").textContent = `${state.folderFiles.length} 個檔案${skipped ? `（略過 ${skipped} 個）` : ""}`;
    $("#filePreviewList").innerHTML = state.folderFiles.slice(0, 20).map((f) => {
      const ext = f.name.split(".").pop().toUpperCase();
      const icons = { PDF: "📄", TXT: "📝", JPG: "🖼️", JPEG: "🖼️", PNG: "🖼️", EPUB: "📚" };
      const size = f.size > 1024 * 1024 ? `${(f.size / 1024 / 1024).toFixed(1)} MB` : `${(f.size / 1024).toFixed(0)} KB`;
      return `<div class="file-preview-item">
        <span class="file-preview-icon">${icons[ext] || "📎"}</span>
        <span class="file-preview-name">${escapeHtml(f.name)}</span>
        <span class="file-preview-size">${size}</span>
      </div>`;
    }).join("") + (state.folderFiles.length > 20 ? `<div class="file-preview-item"><span class="file-preview-icon">...</span><span>還有 ${state.folderFiles.length - 20} 個檔案</span></div>` : "");
    renderUploadProgress({ text: "準備上傳", detail: "", done: 0, total: state.folderFiles.length, percent: 0 });
    $("#folderProgress").classList.remove("hidden");
  } else {
    $("#filePreview").classList.add("hidden");
    $("#folderProgress").classList.add("hidden");
  }
}

$("#singleFileInput").addEventListener("change", (event) => {
  if (event.target.files.length) setFolderFiles(event.target.files);
});
$("#folderInput").addEventListener("change", (event) => setFolderFiles(event.target.files));
$("#batchFileInput").addEventListener("change", (event) => setFolderFiles(event.target.files));
$("#chooseFolderBtn").addEventListener("click", () => $("#folderInput").click());
$("#chooseFilesBtn").addEventListener("click", () => $("#batchFileInput").click());
$("#clearFilesBtn")?.addEventListener("click", () => {
  state.folderFiles = [];
  $("#filePreview").classList.add("hidden");
  $("#folderProgress").classList.add("hidden");
  $("#singleFileInput").value = "";
  $("#batchFileInput").value = "";
  $("#folderInput").value = "";
});

async function readEntryFiles(entry) {
  if (entry.isFile) {
    return new Promise((resolve) => entry.file((file) => resolve([file]), () => resolve([])));
  }
  if (!entry.isDirectory) return [];
  const reader = entry.createReader();
  const entries = [];
  while (true) {
    const batch = await new Promise((resolve) => reader.readEntries(resolve));
    if (!batch.length) break;
    entries.push(...batch);
  }
  const nested = await Promise.all(entries.map(readEntryFiles));
  return nested.flat();
}

$("#dropZone").addEventListener("dragover", (event) => {
  event.preventDefault();
  $("#dropZone").classList.add("dragover");
});
$("#dropZone").addEventListener("dragleave", () => $("#dropZone").classList.remove("dragover"));
$("#dropZone").addEventListener("drop", async (event) => {
  event.preventDefault();
  $("#dropZone").classList.remove("dragover");
  const items = Array.from(event.dataTransfer.items || []);
  const entries = items.map((item) => item.webkitGetAsEntry && item.webkitGetAsEntry()).filter(Boolean);
  if (entries.length) {
    const nested = await Promise.all(entries.map(readEntryFiles));
    setFolderFiles(nested.flat());
  } else {
    setFolderFiles(event.dataTransfer.files || []);
  }
});

$("#uploadSubmitBtn")?.addEventListener("click", async () => {
  if (!state.folderFiles.length) { $("#uploadMsg").textContent = "請先選擇檔案"; return; }
  const projectId = $("#uploadProject").value;
  if (!projectId) { $("#uploadMsg").textContent = "請先選擇專案"; return; }
  const strategy = document.querySelector('[name="duplicate_strategy"]')?.value || "skip";
  const files = state.folderFiles;
  let done = 0;
  const total = files.length;
  renderUploadProgress({ text: "上傳中...", detail: "", done: 0, total, percent: 0 });
  for (const file of files) {
    try {
      const form = new FormData();
      form.append("project_id", projectId);
      form.append("duplicate_strategy", strategy);
      form.append("file", file);
      await fetch("/api/upload", { method: "POST", body: form });
    } catch (_) {}
    done++;
    renderUploadProgress({
      text: done === total ? "上傳完成" : "上傳中...",
      detail: file.name,
      done,
      total,
      percent: Math.round((done / total) * 100),
    });
  }
  state.folderFiles = [];
  $("#filePreview").classList.add("hidden");
  refresh();
});
    form.append("file", file, displayName);
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload");
    xhr.upload.onprogress = (event) => {
      const filePercent = event.lengthComputable ? (event.loaded / event.total) * 100 : 0;
      const overallPercent = ((index + filePercent / 100) / total) * 100;
      renderUploadProgress({
        text: `上傳中：${displayName}`,
        detail: `目前檔案 ${Math.round(filePercent)}%，整體 ${Math.round(overallPercent)}%。`,
        done: index,
        total,
        percent: overallPercent,
      });
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve({});
        }
      } else {
        reject(new Error(xhr.responseText || `HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error("網路錯誤，檔案未完成上傳。"));
    xhr.send(form);
  });
}


$("#queryForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const query = new FormData(event.target).get("query");
  if (!query.trim()) return;
  const selected = state.selectedProjects.size > 0 ? Array.from(state.selectedProjects) : null;
  const body = { query, mode: state.mode, project_ids: selected, top_k: 10, user: state.user };
  const modeLabel = state.mode === "research" ? "研究模式" : "回答模式";
  $("#answerModeTag").textContent = modeLabel;
  $("#answerText").textContent = "查詢中...";
  $("#queryResult").classList.remove("hidden");
  try {
    const result = await api("/api/rag/query", { method: "POST", body: JSON.stringify(body) });
    $("#answerText").textContent = result.answer;
    renderEvidence(result.evidence);
    $("#evidenceCount").textContent = `(${result.evidence.length} 則)`;
  } catch (err) {
    $("#answerText").textContent = "查詢失敗：" + err.message;
  }
});


$("#userForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = Object.fromEntries(new FormData(event.target));
  try {
    await api("/api/users", { method: "POST", body: JSON.stringify(data) });
    $("#userMsg").textContent = `已新增帳號：${data.username}`;
    event.target.reset();
    refresh();
  } catch (err) {
    $("#userMsg").textContent = "新增帳號失敗：" + err.message;
  }
});

document.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-edit-user]");
  if (btn) {
    $("#editUserId").value = btn.dataset.editUser;
    $("#editUsername").textContent = btn.dataset.username;
    $("#editUserRole").value = btn.dataset.role;
    $("#editUserPassword").value = "";
    $("#editUserMsg").textContent = "";
    $("#editUserModal").classList.remove("hidden");
  }
});

$("#closeModalBtn").addEventListener("click", () => $("#editUserModal").classList.add("hidden"));
$("#editUserModal").addEventListener("click", (e) => { if (e.target === $("#editUserModal")) $("#editUserModal").classList.add("hidden"); });

$("#editUserForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const userId = $("#editUserId").value;
  const body = { role: $("#editUserRole").value };
  const pw = $("#editUserPassword").value;
  if (pw) body.password = pw;
  try {
    await api(`/api/users/${userId}`, { method: "PUT", body: JSON.stringify(body) });
    $("#editUserMsg").textContent = "✓ 已更新";
    refresh();
    setTimeout(() => $("#editUserModal").classList.add("hidden"), 800);
  } catch (err) {
    $("#editUserMsg").textContent = "更新失敗：" + err.message;
  }
});

$("#deleteUserBtn").addEventListener("click", async () => {
  if (!confirm("確定要刪除這個帳號嗎？")) return;
  const userId = $("#editUserId").value;
  try {
    await api(`/api/users/${userId}`, { method: "DELETE" });
    $("#editUserModal").classList.add("hidden");
    refresh();
  } catch (err) {
    $("#editUserMsg").textContent = "刪除失敗：" + err.message;
  }
});

$("#llmProvider").addEventListener("change", () => {
  const preset = llmPresets[$("#llmProvider").value] || {};
  if (preset.url) $("#llmBaseUrl").value = preset.url;
  if (preset.key !== undefined) $("#llmApiKey").placeholder = preset.placeholder || "";
});

$("#llmTestBtn").addEventListener("click", async () => {
  const body = {
    provider: $("#llmProvider").value,
    base_url: normalizeUrl($("#llmBaseUrl").value),
    api_key: $("#llmApiKey").value,
    model: "",
  };
  if (!body.base_url) { $("#llmTestMsg").textContent = "請輸入 API 位址"; return; }
  $("#llmTestMsg").textContent = "正在測試連線...";
  try {
    const data = await api("/api/llm/test", { method: "POST", body: JSON.stringify(body) });
    if (data.ok) {
      const select = $("#llmModelSelect");
      select.innerHTML = "";
      if (data.models && data.models.length > 0) {
        data.models.forEach((m) => { const opt = document.createElement("option"); opt.value = m; opt.textContent = m; select.appendChild(opt); });
        $("#llmTestMsg").textContent = `✓ 連線成功！找到 ${data.models.length} 個模型，請選擇一個。`;
      } else {
        select.innerHTML = '<option value="">未找到模型</option>';
        $("#llmTestMsg").textContent = "✓ 連線成功，但未找到可用模型。";
      }
    } else {
      $("#llmTestMsg").textContent = "✗ " + (data.error || data.detail || "連線失敗");
    }
  } catch (err) {
    $("#llmTestMsg").textContent = "✗ 測試失敗：" + (err.message || "無法連線");
  }
});

$("#llmQueryTestBtn").addEventListener("click", async () => {
  const model = $("#llmModelManual").value || $("#llmModelSelect").value;
  if (!model) { $("#llmTestMsg").textContent = "請先選擇或輸入模型名稱"; return; }
  const body = {
    provider: $("#llmProvider").value,
    base_url: normalizeUrl($("#llmBaseUrl").value),
    api_key: $("#llmApiKey").value,
    model: model,
  };
  $("#llmTestMsg").textContent = "正在測試問答...";
  try {
    const res = await api("/api/llm/test-query", { method: "POST", body: JSON.stringify(body) });
    if (res.ok) {
      $("#llmTestMsg").textContent = `✓ 模型回答：${res.answer}`;
    } else {
      $("#llmTestMsg").textContent = "✗ " + (res.error || res.detail || "問答失敗");
    }
  } catch (err) {
    $("#llmTestMsg").textContent = "✗ 問答失敗：" + err.message;
  }
});

$("#llmForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const model = $("#llmModelManual").value || $("#llmModelSelect").value;
  if (!model) { $("#llmSaveMsg").textContent = "請選擇或輸入模型名稱"; return; }
  try {
    await api("/api/settings", { method: "POST", body: JSON.stringify({ key: "llm_provider", value: $("#llmProvider").value }) });
    await api("/api/settings", { method: "POST", body: JSON.stringify({ key: "llm_base_url", value: normalizeUrl($("#llmBaseUrl").value) }) });
    await api("/api/settings", { method: "POST", body: JSON.stringify({ key: "llm_api_key", value: $("#llmApiKey").value }) });
    await api("/api/settings", { method: "POST", body: JSON.stringify({ key: "llm_model", value: model }) });
    $("#llmSaveMsg").textContent = "✓ LLM 設定已保存";
  } catch (err) {
    $("#llmSaveMsg").textContent = "儲存失敗：" + err.message;
  }
});

async function loadWikiProjects() {
  try {
    state.projects = await api("/api/projects");
    const opts = state.projects.map((p) => `<option value="${escapeHtml(p.id)}">${escapeHtml(p.name)}</option>`).join("");
    $("#wikiProjectSelect").innerHTML = opts || '<option value="">尚未建立專案</option>';
  } catch (_) {}
}

async function loadWiki() {
  const projectId = $("#wikiProjectSelect").value;
  if (!projectId) return;
  try {
    const data = await api(`/api/wiki/${projectId}`);
    if (data.pages && data.pages.length) {
      $("#wikiContent").innerHTML = data.pages.map((page) => {
        let images = "";
        try { images = JSON.parse(page.images_json || "[]"); } catch (_) { images = []; }
        let sources = "";
        try { sources = JSON.parse(page.sources_json || "[]"); } catch (_) { sources = []; }
        const imagesHtml = images.length ? `<div class="wiki-page-images">${images.map((img) => `<img src="/api/assets/${escapeHtml(img.id)}" alt="${escapeHtml(img.caption)}" loading="lazy" />`).join("")}</div>` : "";
        const sourcesHtml = sources.length ? `<div class="wiki-page-sources">${sources.map((s) => `<span>📄 ${escapeHtml(s.file)} 頁 ${s.page}</span>`).join("")}</div>` : "";
        return `<div class="wiki-page">
          <h2>${escapeHtml(page.title)}</h2>
          <div class="wiki-page-body">${escapeHtml(page.content).replace(/^## .+$/m, "").trim()}</div>
          ${imagesHtml}
          ${sourcesHtml}
        </div>`;
      }).join("");
    } else {
      $("#wikiContent").innerHTML = '<div class="wiki-empty"><div class="job-empty-icon">📖</div><p>尚未產生維基</p><p class="job-empty-sub">按「產生/更新維基」開始</p></div>';
    }
  } catch (err) {
    $("#wikiContent").innerHTML = `<div class="wiki-empty"><p>載入失敗：${escapeHtml(err.message)}</p></div>`;
  }
}

$("#wikiRefreshBtn").addEventListener("click", () => { loadWikiProjects(); loadWiki(); });

$("#wikiGenerateBtn").addEventListener("click", async () => {
  const projectId = $("#wikiProjectSelect").value;
  if (!projectId) { $("#wikiMsg").textContent = "請先選擇專案"; return; }
  $("#wikiMsg").textContent = "正在產生維基，請稍候（可能需要數分鐘）...";
  $("#wikiGenerateBtn").disabled = true;
  try {
    const data = await api(`/api/wiki/generate/${projectId}`, { method: "POST", body: "{}" });
    $("#wikiMsg").textContent = `✓ ${data.message}`;
    loadWiki();
  } catch (err) {
    $("#wikiMsg").textContent = "✗ 產生失敗：" + err.message;
  }
  $("#wikiGenerateBtn").disabled = false;
});

$("#backupBtn").addEventListener("click", async () => {
  const data = await api("/api/admin/backup", { method: "POST", body: "{}" });
  $("#adminMsg").textContent = `備份完成：${data.backup_path}`;
});
$("#rebuildBtn").addEventListener("click", async () => {
  const data = await api("/api/admin/rebuild", { method: "POST", body: "{}" });
  $("#adminMsg").textContent = data.message;
});

setInterval(() => {
  const appVisible = !$("#app").classList.contains("hidden");
  const jobsVisible = !$("#jobs").classList.contains("hidden");
  if (appVisible && jobsVisible) refresh();
}, 5000);

if (state.token) {
  api("/api/config").then(() => {
    $("#login").classList.add("hidden");
    $("#app").classList.remove("hidden");
    refresh();
  }).catch(() => {
    state.token = "";
    localStorage.removeItem("ef_token");
  });
}
