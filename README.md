# paper_rag

一个从 0 复现 PaperQA2 核心思路的学习项目。第一阶段目标是做出 CLI MVP：从本地 PDF 目录导入论文，建立本地索引，然后用自然语言提问并返回带引用的答案。

## 当前阶段

正在实现 `docs/task/01_cli_mvp.md` 中的第一阶段：CLI MVP。

已确定的第一批技术选择：

- Python：使用 conda 环境 `paper_rag`，Python 3.11
- CLI：Typer
- 数据模型：Pydantic v2
- PDF 解析：PyMuPDF
- token/chunk：tiktoken
- LLM/Embedding：OpenAI API 兼容接口
- 向量存储：Chroma
- 元数据存储：SQLite

## 文档身份、版本与去重

当前索引不再把本地文件路径当作论文身份。本地路径只作为 `source_uri` 保存，系统内部使用独立的 `document_id` 表示逻辑文档，并用 `document_version_id` 表示一次具体内容版本。

MVP 默认使用单租户 `tenant_id = "default"`；CLI 可通过 `--tenant-id` 指定不同工作区。导入 PDF 时会基于解析后的规范化页面文本计算 SHA-256 `content_hash`。同一 tenant 内如果发现相同 `content_hash`，会复用已有内容索引，不重复生成 embedding；同一路径内容变化时，会创建新的文档版本并重建旧版本的 chunk/vector。

职责划分：

- SQLite：保存完整 `Document`、`DocumentVersion`、`Chunk`、索引状态和引用回溯信息。
- Chroma：保存向量和轻量 metadata，用于相似度检索；检索命中后再回到 SQLite 读取完整 chunk 文本。

## 本地运行草稿

激活已创建的 conda 环境：

```powershell
conda activate paper_rag
```

安装项目依赖：

```powershell
pip install -e ".[dev]"
```

查看 CLI：

```powershell
paper-rag --help
```

或直接使用模块方式运行：

```powershell
python -m paper_rag --help
```

## CLI MVP 验收命令

使用仓库中的真实论文目录作为本地知识库：

```powershell
Get-ChildItem eval/papers
```

使用本地离线模式建立索引：

```powershell
paper-rag index eval/papers --index-dir .paper_rag/manual_index --tenant-id default --local --chunk-size 800 --chunk-overlap 120
```

查看文档和 chunk：

```powershell
paper-rag list-docs --index-dir .paper_rag/manual_index --tenant-id default
paper-rag show-chunks "think in space.pdf" --index-dir .paper_rag/manual_index --tenant-id default --limit 3
```

提问并查看带引用答案：

```powershell
paper-rag ask "论文中提出的 VSI-Bench 基准测试集包含了多少个问答对？" --index-dir .paper_rag/manual_index --tenant-id default --local --top-k 3
```

验证证据不足场景：

```powershell
paper-rag ask "What is the capital of France?" --index-dir .paper_rag/manual_index --tenant-id default --local --top-k 3
```

## 评测基线

项目已经建立第一版人工 golden dataset，用来衡量后续 RAG 改动是否真的提升检索、
回答、引用和拒答能力。评测语料位于 `eval/papers/`，评测集位于
`eval/datasets/golden.jsonl`，文档短键映射位于
`eval/datasets/golden.documents.json`。

本地离线评测命令：

```powershell
paper-rag eval eval/datasets/golden.jsonl --source-dir eval/papers --index-dir .paper_rag/eval_index --tenant-id eval --local --top-k 3 --chunk-size 800 --chunk-overlap 120 --report-json .paper_rag/reports/eval_report.json
```

控制台输出适合快速查看；JSON report 才是每次优化后建议留档和对比的指标文件。
字段说明、人工审核规则和可复现命令见 `eval/README.md`。

## Web Inspector 本地检验台

Web Inspector 是当前阶段的开发/验收界面，用来查看本地索引状态、文档、chunk、问答结果和 citation 追溯。它通过 FastAPI 暴露薄 API 边界，不让前端直接依赖 CLI 输出格式。

启动服务：

```powershell
paper-rag serve --host 127.0.0.1 --port 8000
```

打开浏览器访问：

```text
http://127.0.0.1:8000
```

常用 API：

```text
GET  /health
GET  /api/index/status?tenant_id=default&index_dir=.paper_rag/manual_index
GET  /api/documents?tenant_id=default&index_dir=.paper_rag/manual_index
GET  /api/documents/{document_id}/chunks?tenant_id=default&index_dir=.paper_rag/manual_index
POST /api/documents/upload
POST /api/ask
```

当前 Web Inspector 上传约束：

- 仅支持单个 PDF 上传，暂不支持多文件批量上传。
- 上传后同步索引，暂不支持后台异步索引任务。
- 上传文件默认保存到 `.paper_rag/uploads/{tenant_id}/`。
- 默认上传大小限制为 50MB，可通过 `PAPER_RAG_UPLOAD_MAX_BYTES` 调整。

## 环境变量

后续实现 LLM 和 embedding 时会读取：

```powershell
$env:OPENAI_API_KEY="your-api-key"
```

可选配置：

```powershell
$env:PAPER_RAG_INDEX_DIR=".paper_rag/index"
$env:PAPER_RAG_UPLOAD_DIR=".paper_rag/uploads"
$env:PAPER_RAG_UPLOAD_MAX_BYTES="52428800"
$env:PAPER_RAG_LLM_MODEL="gpt-4.1-mini"
$env:PAPER_RAG_EMBEDDING_MODEL="text-embedding-3-small"
```

## 任务跟踪

任务清单见：

- `docs/task/01_cli_mvp.md`
- `docs/task/01_cli_mvp_addendum_01_document_identity.md`
- `docs/task/02_web_inspector_mvp.md`
- `docs/task/03_evaluation_foundation.md`
