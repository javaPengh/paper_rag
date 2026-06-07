// 本地 Web Inspector 行为，用于从浏览器触发 MVP RAG 流程。

// 仅保存界面状态；持久化 RAG 数据由 FastAPI API 和本地索引存储负责。
const state = {
  documents: [],
  selectedDocumentId: null,
  config: null,
  components: null,
};

// 缓存 DOM 引用，让事件处理函数保持短小，并尽早暴露缺失的界面元素。
const el = {
  serviceStatus: document.querySelector("#service-status"),
  workspaceForm: document.querySelector("#workspace-form"),
  indexDir: document.querySelector("#index-dir"),
  tenantId: document.querySelector("#tenant-id"),
  indexBadge: document.querySelector("#index-badge"),
  statusGrid: document.querySelector("#status-grid"),
  uploadForm: document.querySelector("#upload-form"),
  uploadFile: document.querySelector("#upload-file"),
  uploadChunkSize: document.querySelector("#upload-chunk-size"),
  uploadChunkOverlap: document.querySelector("#upload-chunk-overlap"),
  uploadMode: document.querySelector("#upload-mode"),
  uploadButton: document.querySelector("#upload-button"),
  uploadOutput: document.querySelector("#upload-output"),
  documentCount: document.querySelector("#document-count"),
  documentList: document.querySelector("#document-list"),
  selectedDocument: document.querySelector("#selected-document"),
  reloadChunks: document.querySelector("#reload-chunks"),
  chunkList: document.querySelector("#chunk-list"),
  askForm: document.querySelector("#ask-form"),
  question: document.querySelector("#question"),
  topK: document.querySelector("#top-k"),
  askMode: document.querySelector("#ask-mode"),
  answerOutput: document.querySelector("#answer-output"),
  citationList: document.querySelector("#citation-list"),
  evidenceList: document.querySelector("#evidence-list"),
};

function workspaceParams() {
  // GET 检查接口使用的租户和索引工作区查询参数。
  const params = new URLSearchParams();
  const tenantId = el.tenantId.value.trim() || "default";
  const indexDir = el.indexDir.value.trim();
  params.set("tenant_id", tenantId);
  if (indexDir) {
    params.set("index_dir", indexDir);
  }
  return params;
}

function workspacePayload() {
  // 操作租户和索引工作区的 POST 接口共用的 JSON 请求基础载荷。
  const payload = {
    tenant_id: el.tenantId.value.trim() || "default",
    local: selectedMode(el.askMode) === "local",
  };
  const indexDir = el.indexDir.value.trim();
  if (indexDir) {
    payload.index_dir = indexDir;
  }
  return payload;
}

function selectedMode(selectNode) {
  // 模式下拉框使用稳定小枚举，显示文本再呈现当前配置的模型名。
  return selectNode.value === "api" ? "api" : "local";
}

function setSelectOptions(selectNode, options, selectedValue) {
  // `/api/config` 加载后重建选项，避免保留过期模型名。
  selectNode.replaceChildren();
  for (const option of options) {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    selectNode.append(node);
  }
  selectNode.value = selectedValue;
}

function componentDescriptor(kind, componentId) {
  // 从后端 catalog 中找到组件描述，找不到时让调用方使用兼容默认值。
  const catalog = state.components || {};
  const descriptors = catalog[kind] || [];
  return descriptors.find((descriptor) => descriptor.id === componentId) || null;
}

function componentModelLabel(kind, componentId, fallbackModel) {
  // 下拉框展示的模型名来自 registry 暴露的默认模型和模型列表。
  const descriptor = componentDescriptor(kind, componentId);
  const modelId = descriptor?.default_model || fallbackModel;
  const option = descriptor?.models?.find((item) => item.id === modelId);
  return option?.label || modelId;
}

function updateModeOptions() {
  // 显示 registry 返回的真实模型名，让用户明确每种模式会调用什么。
  const config = state.config || {};
  const localEmbedding = componentModelLabel(
    "embedder",
    "hash_embedder",
    config.local_embedding_model || "hash-embedding-v1",
  );
  const localAnswer = componentModelLabel(
    "generator",
    "extractive_generator",
    config.local_answer_model || "extractive-local-v1",
  );
  const apiEmbedding = componentModelLabel(
    "embedder",
    "openai_embedder",
    config.embedding_model || "text-embedding-3-small",
  );
  const apiLlm = componentModelLabel(
    "generator",
    "openai_generator",
    config.llm_model || "gpt-4.1-mini",
  );
  setSelectOptions(
    el.uploadMode,
    [
      { value: "local", label: `Local embedding (${localEmbedding})` },
      { value: "api", label: `API embedding (${apiEmbedding})` },
    ],
    selectedMode(el.uploadMode),
  );
  setSelectOptions(
    el.askMode,
    [
      { value: "local", label: `Local answer (${localEmbedding} + ${localAnswer})` },
      { value: "api", label: `API models (${apiEmbedding} + ${apiLlm})` },
    ],
    selectedMode(el.askMode),
  );
}

async function requestJson(url, options = {}) {
  // 集中封装 API 请求，让结构化后端错误在界面中稳定显示。
  const headers = options.body instanceof FormData ? {} : { "Content-Type": "application/json" };
  const response = await fetch(url, {
    headers,
    ...options,
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(apiErrorMessage(body.detail, response.status));
  }
  return body;
}

function apiErrorMessage(detail, status) {
  // FastAPI 在不同失败阶段可能返回字符串或结构化错误对象。
  if (typeof detail === "string") {
    return detail;
  }
  if (detail && typeof detail === "object") {
    const prefix = detail.stage ? `${detail.stage}: ` : "";
    return `${prefix}${detail.message || detail.error_type || `Request failed with ${status}`}`;
  }
  return `Request failed with ${status}`;
}

function setBadge(status) {
  // 状态同步到 class 名，方便 CSS 区分 ready/error 等状态。
  el.indexBadge.textContent = status || "unknown";
  el.indexBadge.className = `badge ${status || ""}`;
}

function setStatusGrid(status) {
  // 状态表格有意展示偏原始的运行元数据，便于验收和调试。
  const rows = [
    ["Tenant", status.tenant_id],
    ["Documents", status.document_count],
    ["Chunks", status.chunk_count],
    ["Model", status.embedding_model || "none"],
    ["Index dir", status.index_dir],
    ["Updated", status.updated_at || "none"],
  ];
  el.statusGrid.replaceChildren();
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = String(value);
    el.statusGrid.append(dt, dd);
  }
}

function emptyNode(text = "No data") {
  // 当前没有后端数据时使用的通用占位节点。
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}

function errorNode(message) {
  // 人工验收时用可见错误节点替代 alert 弹窗。
  const node = document.createElement("div");
  node.className = "error-state";
  node.textContent = message;
  return node;
}

function loadingNode() {
  // 同步 MVP 操作可能耗时数秒，使用通用加载节点展示状态。
  const node = document.createElement("div");
  node.className = "loading-state";
  node.textContent = "Loading...";
  return node;
}

function shortHash(value) {
  // 压缩长 ID，同时保留足够前缀方便人工关联。
  if (!value) {
    return "none";
  }
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

function renderDocuments(documents) {
  // 渲染文档列表，并把文档选择连接到 chunk 检查。
  el.documentList.replaceChildren();
  el.documentCount.textContent = String(documents.length);
  if (!documents.length) {
    el.documentList.append(emptyNode());
    return;
  }

  for (const documentItem of documents) {
    const button = document.createElement("button");
    button.type = "button";
    button.className =
      documentItem.id === state.selectedDocumentId ? "document-item active" : "document-item";
    button.dataset.documentId = documentItem.id;

    const title = document.createElement("div");
    title.className = "document-title";
    title.textContent = documentItem.file_name;

    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = [
      `pages=${documentItem.page_count}`,
      `chunks=${documentItem.chunk_count}`,
      `version=${shortHash(documentItem.current_version_id)}`,
      `hash=${shortHash(documentItem.content_hash)}`,
    ].join(" | ");

    button.append(title, meta);
    button.addEventListener("click", () => selectDocument(documentItem.id));
    el.documentList.append(button);
  }
}

function renderUploadResult(result) {
  // 同时展示存储和索引结果，便于区分上传失败和索引失败。
  const index = result.index;
  const upload = result.upload;
  el.uploadOutput.replaceChildren();

  const summary = document.createElement("div");
  summary.className = "upload-summary";
  summary.textContent = [
    `file=${upload.safe_file_name}`,
    `indexed=${index.indexed}`,
    `reused_source=${index.reused_source}`,
    `reused_content=${index.reused_content}`,
    `reindexed=${index.reindexed}`,
    `chunks=${index.indexed_chunks}`,
  ].join(" | ");
  el.uploadOutput.append(summary);

  const detail = document.createElement("div");
  detail.className = "upload-detail";
  detail.textContent = `source_uri=${upload.source_uri}`;
  el.uploadOutput.append(detail);

  renderUploadIssues("Warnings", index.warnings);
  renderUploadIssues("Errors", index.errors);
  renderUploadIssues("Skipped", index.skipped_files);
}

function renderUploadIssues(label, issues) {
  // 用同一视觉结构展示跳过文件、警告和错误。
  if (!issues || !issues.length) {
    return;
  }
  const heading = document.createElement("div");
  heading.className = "upload-issue-heading";
  heading.textContent = label;
  el.uploadOutput.append(heading);

  for (const issue of issues) {
    const item = document.createElement("div");
    item.className = "upload-issue";
    item.textContent = [
      issue.reason || issue.message || "unknown",
      issue.page_number ? `page=${issue.page_number}` : "",
      issue.source_path || "",
    ]
      .filter(Boolean)
      .join(" | ");
    el.uploadOutput.append(item);
  }
}

async function selectDocument(documentId) {
  // 在本地记录当前选择，刷新选中样式，再加载该文档的 chunk。
  state.selectedDocumentId = documentId;
  renderDocuments(state.documents);
  const documentItem = state.documents.find((item) => item.id === documentId);
  el.selectedDocument.textContent = documentItem ? documentItem.file_name : documentId;
  el.reloadChunks.disabled = false;
  await loadChunks();
}

function renderChunks(chunks) {
  // 渲染 chunk 文本和来源元数据，用于验证 citation 可追溯性。
  el.chunkList.replaceChildren();
  if (!chunks.length) {
    el.chunkList.append(emptyNode());
    return;
  }

  for (const chunk of chunks) {
    const item = document.createElement("article");
    item.className = "chunk-item";

    const meta = document.createElement("div");
    meta.className = "chunk-meta";
    meta.textContent = [
      `chunk=${chunk.chunk_index}`,
      `pages=${chunk.page_start}-${chunk.page_end}`,
      `tokens=${chunk.token_count ?? "unknown"}`,
      `id=${shortHash(chunk.id)}`,
    ].join(" | ");

    const text = document.createElement("div");
    text.className = "chunk-text";
    text.textContent = chunk.text;

    item.append(meta, text);
    el.chunkList.append(item);
  }
}

function renderAskResult(result) {
  // 渲染最终答案、citation 和全部检索证据，供验收检查。
  el.answerOutput.textContent = result.answer;
  el.citationList.replaceChildren();
  el.evidenceList.replaceChildren();

  for (const citation of result.citations) {
    const item = document.createElement("div");
    item.className = "citation-item";
    const label = document.createElement("div");
    label.className = "document-title";
    label.textContent = citation.label;
    const meta = document.createElement("div");
    meta.className = "citation-meta";
    meta.textContent = `chunk=${shortHash(citation.chunk_id)} | ${citation.snippet || ""}`;
    item.append(label, meta);
    el.citationList.append(item);
  }

  for (const evidence of result.evidence) {
    const item = document.createElement("article");
    item.className = evidence.used ? "evidence-item used" : "evidence-item";
    const meta = document.createElement("div");
    meta.className = "evidence-meta";
    meta.textContent = [
      `score=${evidence.score.toFixed(3)}`,
      `used=${evidence.used ? "yes" : "no"}`,
      `chunk=${shortHash(evidence.chunk.id)}`,
      `${evidence.chunk.file_name || evidence.chunk.document_id}`,
      `p.${evidence.chunk.page_start}`,
    ].join(" | ");
    const text = document.createElement("div");
    text.className = "evidence-text";
    text.textContent = evidence.chunk.text;
    item.append(meta, text);
    el.evidenceList.append(item);
  }

  if (!result.citations.length) {
    el.citationList.append(emptyNode("No citations"));
  }
  if (!result.evidence.length) {
    el.evidenceList.append(emptyNode("No evidence"));
  }
}

async function loadHealth() {
  // 在用户开始测试前，把服务状态填入页头。
  try {
    const health = await requestJson("/health");
    el.serviceStatus.textContent = `${health.status} | version ${health.version}`;
  } catch (error) {
    el.serviceStatus.textContent = error.message;
  }
}

async function loadRuntimeConfig() {
  // 加载模型 catalog 和推荐工作区路径，但不暴露密钥。
  try {
    const [config, components] = await Promise.all([
      requestJson("/api/config"),
      requestJson("/api/components"),
    ]);
    state.config = config;
    state.components = components;
    updateModeOptions();
    el.topK.value = String(config.top_k || 3);
    const keyState = config.api_key_configured ? "API key configured" : "API key missing";
    el.serviceStatus.textContent = `${el.serviceStatus.textContent} | ${keyState}`;
  } catch (error) {
    el.serviceStatus.textContent = `${el.serviceStatus.textContent} | ${error.message}`;
  }
}

async function loadWorkspace() {
  // 同步刷新状态和文档列表，让界面反映同一个工作区。
  el.documentList.replaceChildren(loadingNode());
  el.chunkList.replaceChildren(emptyNode("Select a document"));
  el.reloadChunks.disabled = true;
  state.selectedDocumentId = null;

  const params = workspaceParams();
  try {
    const [status, documents] = await Promise.all([
      requestJson(`/api/index/status?${params}`),
      requestJson(`/api/documents?${params}`),
    ]);
    setBadge(status.status);
    setStatusGrid(status);
    state.documents = documents;
    renderDocuments(documents);
    el.selectedDocument.textContent = "Select a document";
  } catch (error) {
    setBadge("error");
    el.documentList.replaceChildren(errorNode(error.message));
  }
}

async function uploadDocument(event) {
  // 提交单个 PDF 上传，并通过后端 API 同步触发索引。
  event.preventDefault();
  const file = el.uploadFile.files[0];
  if (!file) {
    el.uploadOutput.replaceChildren(errorNode("Choose a PDF file before uploading."));
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("tenant_id", el.tenantId.value.trim() || "default");
  formData.append("local", selectedMode(el.uploadMode) === "local" ? "true" : "false");
  formData.append("chunk_size", String(Number(el.uploadChunkSize.value || 800)));
  formData.append("chunk_overlap", String(Number(el.uploadChunkOverlap.value || 120)));
  const indexDir = el.indexDir.value.trim();
  if (indexDir) {
    formData.append("index_dir", indexDir);
  }

  el.uploadButton.disabled = true;
  el.uploadOutput.replaceChildren(loadingNode());
  try {
    const result = await requestJson("/api/documents/upload", {
      method: "POST",
      body: formData,
    });
    renderUploadResult(result);
    await loadWorkspace();
    const uploadedDocument = state.documents.find(
      (item) => item.source_uri === result.upload.source_uri,
    );
    if (uploadedDocument) {
      await selectDocument(uploadedDocument.id);
    }
  } catch (error) {
    el.uploadOutput.replaceChildren(errorNode(error.message));
  } finally {
    el.uploadButton.disabled = false;
  }
}

async function loadChunks() {
  // 加载当前选中文档的 chunk；未选择文档时不执行。
  if (!state.selectedDocumentId) {
    return;
  }
  el.chunkList.replaceChildren(loadingNode());
  const params = workspaceParams();
  params.set("limit", "100");
  try {
    const chunks = await requestJson(
      `/api/documents/${encodeURIComponent(state.selectedDocumentId)}/chunks?${params}`,
    );
    renderChunks(chunks);
  } catch (error) {
    el.chunkList.replaceChildren(errorNode(error.message));
  }
}

async function askQuestion(event) {
  // 提交问题，并渲染答案以及用于诊断的检索证据。
  event.preventDefault();
  const question = el.question.value.trim();
  if (!question) {
    el.answerOutput.textContent = "Question cannot be empty.";
    return;
  }

  el.answerOutput.textContent = "Loading...";
  el.citationList.replaceChildren();
  el.evidenceList.replaceChildren();
  const payload = {
    ...workspacePayload(),
    question,
    top_k: Number(el.topK.value || 3),
  };

  try {
    const result = await requestJson("/api/ask", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    renderAskResult(result);
  } catch (error) {
    el.answerOutput.textContent = error.message;
  }
}

el.workspaceForm.addEventListener("submit", (event) => {
  event.preventDefault();
  loadWorkspace();
});
el.indexDir.addEventListener("change", loadWorkspace);
el.tenantId.addEventListener("change", loadWorkspace);
el.reloadChunks.addEventListener("click", loadChunks);
el.uploadForm.addEventListener("submit", uploadDocument);
el.askForm.addEventListener("submit", askQuestion);

loadHealth()
  .then(loadRuntimeConfig)
  .then(loadWorkspace);
