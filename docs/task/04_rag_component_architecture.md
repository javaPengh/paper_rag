# 04 RAG 组件边界与类型边界架构改造

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除/取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，只勾选对应任务，不批量勾选。

## 阶段目标

参考 Verba 的清晰命名和组件分层，但不引入完整插件平台。本任务只建立后续解析、
切分、embedding、检索和生成优化不会推倒重来的架构边界：

- 核心业务模型统一进入 `paper_rag.domain`。
- `paper_rag.schemas` 保留为旧导入路径兼容层。
- Reader / Chunker / Embedder / Retriever / Generator 五类组件拥有明确接口和轻量 registry。
- CLI、API、Web Inspector 和 evaluation runner 从 registry 创建组件。
- 评测 JSON report 记录本次运行实际使用的组件配置。

## 设计边界

- `paper_rag/domain/models.py` 只放文档、版本、页面、chunk、引用、答案、检索结果和索引状态等稳定业务模型。
- `paper_rag/api/schemas.py` 继续只放 API 请求/响应 DTO。
- `paper_rag/evaluation/*` 继续维护评测数据和指标类型，不并入领域模型。
- `paper_rag/components/types.py` 只放组件 catalog 和运行配置类型。
- `paper_rag/components/interfaces.py` 只放五类能力协议。
- `paper_rag/components/registry.py` 只负责组件注册、查询、默认配置和实例创建。
- provider 文件使用能力目录和 snake_case 文件名，例如 `embedding/hash_embedder.py`。

## 完成清单

- [x] 新增 `docs/task/04_rag_component_architecture.md`
- [x] 新增 `domain/models.py` 和 `domain/__init__.py`
- [x] 将核心领域模型从 `schemas.py` 迁移到 `domain/models.py`
- [x] 保留 `schemas.py` 兼容 re-export
- [x] 新增 `components/types.py`
- [x] 新增 `components/interfaces.py`
- [x] 新增 `components/registry.py`
- [x] 新增 reading / chunking / embedding / retrieval / generation 组件目录
- [x] 将当前 PDF parser 包装为 `PdfReader`
- [x] 将当前 token window chunking 包装为 `TokenWindowChunker`
- [x] 将当前 hash/openai embedding 包装为 Embedder 组件
- [x] 将当前 vector search 包装为 `VectorRetriever`
- [x] 将当前 extractive/openai answering 包装为 Generator 组件
- [x] CLI 从 registry 创建组件
- [x] API 从 registry 创建组件
- [x] Evaluation runner 从 registry 创建组件
- [x] 新增 `GET /api/components`
- [x] Web Inspector 模型下拉框改为消费 `/api/components`
- [x] JSON report 记录 `rag_config`
- [x] README 和 `eval/README.md` 更新组件配置说明
- [x] task 完成后追加一条 `docs/task_history.md` 记录

## 验收重点

- registry 能列出 Reader、Chunker、Embedder、Retriever、Generator 五类组件。
- 旧导入路径 `paper_rag.schemas`、`paper_rag.retrieval.Retriever` 和现有 CLI 命令保持兼容。
- `/api/components` 只返回组件和模型元数据，不暴露 API key、base URL 明文或其他密钥。
- `paper-rag eval --report-json` 的 `run.rag_config` 能记录五类组件的 ID、模型和关键参数。
- 本任务不改变 PDF 解析、chunk 切分、embedding、检索和答案生成的当前行为。
