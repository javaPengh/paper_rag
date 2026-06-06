const state = {
  documents: [],
  selectedDocumentId: null,
};

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
  uploadLocalMode: document.querySelector("#upload-local-mode"),
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
  localMode: document.querySelector("#local-mode"),
  answerOutput: document.querySelector("#answer-output"),
  citationList: document.querySelector("#citation-list"),
  evidenceList: document.querySelector("#evidence-list"),
};

function workspaceParams() {
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
  const payload = {
    tenant_id: el.tenantId.value.trim() || "default",
    local: el.localMode.checked,
  };
  const indexDir = el.indexDir.value.trim();
  if (indexDir) {
    payload.index_dir = indexDir;
  }
  return payload;
}

async function requestJson(url, options = {}) {
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
  el.indexBadge.textContent = status || "unknown";
  el.indexBadge.className = `badge ${status || ""}`;
}

function setStatusGrid(status) {
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
  const node = document.createElement("div");
  node.className = "empty-state";
  node.textContent = text;
  return node;
}

function errorNode(message) {
  const node = document.createElement("div");
  node.className = "error-state";
  node.textContent = message;
  return node;
}

function loadingNode() {
  const node = document.createElement("div");
  node.className = "loading-state";
  node.textContent = "Loading...";
  return node;
}

function shortHash(value) {
  if (!value) {
    return "none";
  }
  return value.length > 12 ? `${value.slice(0, 12)}...` : value;
}

function renderDocuments(documents) {
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
  state.selectedDocumentId = documentId;
  renderDocuments(state.documents);
  const documentItem = state.documents.find((item) => item.id === documentId);
  el.selectedDocument.textContent = documentItem ? documentItem.file_name : documentId;
  el.reloadChunks.disabled = false;
  await loadChunks();
}

function renderChunks(chunks) {
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
  try {
    const health = await requestJson("/health");
    el.serviceStatus.textContent = `${health.status} | version ${health.version}`;
  } catch (error) {
    el.serviceStatus.textContent = error.message;
  }
}

async function loadWorkspace() {
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
  event.preventDefault();
  const file = el.uploadFile.files[0];
  if (!file) {
    el.uploadOutput.replaceChildren(errorNode("Choose a PDF file before uploading."));
    return;
  }

  const formData = new FormData();
  formData.append("file", file);
  formData.append("tenant_id", el.tenantId.value.trim() || "default");
  formData.append("local", el.uploadLocalMode.checked ? "true" : "false");
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
el.reloadChunks.addEventListener("click", loadChunks);
el.uploadForm.addEventListener("submit", uploadDocument);
el.askForm.addEventListener("submit", askQuestion);

loadHealth();
loadWorkspace();
