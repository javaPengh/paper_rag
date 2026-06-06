# 任务历史记录

用于记录项目实际开发过程中的关键变更、设计取舍和偏离计划的原因。
本文件不记录普通实现细节、测试过程和临时调试信息。

## 记录原则

1. 每次完成一个开发任务后追加一条记录。
2. 只记录关键变更，不写流水账。
3. 默认不对照原计划。
4. 只有当实际实现与计划安排存在明显差异时，才增加“计划差异与原因”。
5. 如果差异原因不明确，必须先询问用户，不得自行编造。
6. 不记录验证结果；验证失败产生的新修改，作为后续任务记录。
7. 不记录普通遗留问题；确实影响后续方向的事项，应进入计划文档或待办文档。

## 2026-05-02 - CLI RAG MVP 建立

### 变更内容
建立本地 PDF 论文目录导入、文本解析、chunk 切分、embedding、向量检索、问答生成和引用输出的 CLI MVP。核心命令包括 `index`、`ask`、`list-docs` 和 `show-chunks`。

### 关键原因
项目需要先跑通最小 RAG 闭环，确认 PDF 解析、索引、检索、答案生成和 citation 追溯这些基础能力可以组合工作，再进入 Web、评测和后续检索质量优化。

## 2026-05-04 - 文档身份、版本与去重策略调整

### 变更内容
将文档身份从本地路径派生调整为系统内部稳定 `document_id`，并引入 `DocumentVersion`、`tenant_id`、`source_uri` 和 `content_hash`。同一 tenant 内以内容 hash 识别重复内容，`source_uri` 仅作为来源位置记录。

### 关键原因
RAG 知识库中的文档身份应由内容和业务归属决定，而不是由本地导入路径决定。相同内容来自不同路径时，不应重复切分、向量化和入库；同一路径内容变化时，应作为新版本处理。

### 计划差异与原因
CLI MVP 初始阶段更接近“本地路径即文档”的简单模型。实际调整为“稳定文档身份 + 内容版本 + 来源 URI”，原因是该方案更符合企业知识库和后续 connector 接入的文档语义。

## 2026-05-09 - Web Inspector 验收入口建立

### 变更内容
新增 FastAPI 服务边界和静态 Web Inspector 页面，支持查看索引状态、文档、chunk、citation 与 evidence，并支持从浏览器上传 PDF 后触发本地索引和问答。

### 关键原因
CLI 已能验证核心链路，但继续优化 RAG 质量和引用追溯时，需要一个更直观的开发验收入口。Web Inspector 作为调试和验收工具，通过结构化 API 访问后端能力，避免前端依赖 CLI 文本输出。

### 计划差异与原因
CLI MVP 阶段原本暂不实现 Web UI 和 FastAPI。实际新增 Web Inspector，是因为项目进入前端验收和调试阶段后，需要从浏览器完整触发上传、索引、检索、回答和 citation 追溯流程。该页面定位为开发检验台，不是正式产品级 Web App。

## 2026-06-06 - Web Inspector 上传与前端闭环完善

### 变更内容
将 `docs/task/02_web_inspector_mvp.md` 从只读检验台重新定义为“从前端完整触发本地 RAG 流程”的阶段任务，并补齐上传、受控存储、Web 触发索引、前端上传闭环、端到端验收路径和错误约束。实现了 tenant 隔离的本地上传存储、`POST /api/documents/upload`、结构化 indexing summary、前端上传表单、上传后自动刷新 documents/chunks，以及相关 API 和手动验收覆盖。

### 关键原因
当前阶段需要让浏览器能够完整触发“上传 PDF -> 保存 source -> 索引 -> 查看 chunk -> 提问 -> 查看 evidence/citation”的验收链路，而不是只能检查 CLI 已经建好的索引。上传文件也需要受控保存和清晰的 source URI 约定，为后续删除、重建、版本追溯和企业 connector 接入保留边界。

### 计划差异与原因
最初的 Web Inspector 任务定义偏窄，只覆盖状态、文档、chunk 和 ask 的只读检验能力。实际推进时发现前端验收入口必须覆盖上传和索引触发，否则无法从浏览器完整验证 RAG MVP，因此扩展了 task2 的范围。该页面仍定位为开发检验台，不升级为正式产品级 Web App。

## 2026-06-06 - Web Inspector 错误处理与 MVP 约束收敛

### 变更内容
为上传与索引流程补充结构化错误处理和 MVP 约束：上传错误统一返回 `stage`、`error_type`、`message`，支持非 PDF、空文件、超大小、不可解析 PDF 和索引参数错误的清晰反馈；新增 `PAPER_RAG_UPLOAD_MAX_BYTES`，默认 50MB；README 和手动验收文档明确单文件上传、同步索引、暂不支持批量上传和后台异步任务。

### 关键原因
前端可触发完整流程后，错误不再只是开发者日志问题，而会直接影响验收体验和后续系统边界。将上传错误、解析失败和索引失败区分清楚，可以让前端稳定展示问题，也便于后续引入异步任务、权限和生产级文件策略。

## 2026-06-06 - Evaluation Foundation 任务规划建立

### 变更内容
新增 `docs/task/03_evaluation_foundation.md`，规划轻量、确定性、可扩展的 RAG 评测基础。任务拆分为评测数据格式、人工 golden dataset、dataset parser、evaluation runner、retrieval 指标、answer/citation/refusal 指标、报告输出和文档验收，并明确区分 Agent 可实现的工程任务与需要用户审核的 golden dataset 内容。

### 关键原因
在继续做结构感知切分、BM25、rerank 或 RCS 之前，需要先建立稳定评测基线，避免后续优化只能依赖主观感觉。第一版评测优先采用人工 golden dataset 和确定性指标，不强依赖 RAGAs 或 LLM-as-judge，以保证评测结果可重复、可解释、成本可控。

### 计划差异与原因
原本下一步倾向直接进入检索质量增强，但在继续优化前先建立评测基线更符合企业 RAG 迭代方式：先有可信“尺子”，再改 chunk、retrieval 和 answer 策略。RAGAs 被暂定为后续可插拔评测后端，而不是第一版强依赖。

## 2026-06-06 - Golden Dataset 评测基础设计

### 变更内容
建立第一版人工 golden dataset 结构，新增 `eval/datasets/golden.jsonl`、`eval/datasets/golden.documents.json`、`eval/schemas/eval_case.schema.json` 和 `docs/evaluation_dataset_format.md`。评测 case 统一使用 `evidence` 数组表达应命中的文档、页码和原文锚点词，使用 `answer_terms` 表达最终答案或拒答文本中的关键锚点。

### 关键原因
后续 chunk、retrieval、rerank、RCS 和回答策略优化都需要一个可重复的基线。人工 golden dataset 比自动合成问题更适合作为第一版基准，因为它可以明确标注证据页码、原文锚点、答案锚点和不可回答问题。

### 计划差异与原因
原任务规划中包含“Agent 复用早期样例 PDF 起草候选 eval cases”，并使用 `expected_files`、`expected_page_start` 等字段。实际调整为基于固定评测语料目录 `eval/papers/` 和文档短键映射表维护 golden dataset；后续也移除了样例 PDF 生成脚本，避免生产代码继续维护演示数据。这样做的原因有三点：第一，没有目标 PDF 时无法可信起草问题；第二，Web 上传后的文件名会被重写，不适合作为评测集稳定标识；第三，统一的 `evidence` 数组比顶层 `expected_*` 字段更适合人工维护，也能自然支持跨文档和多证据问题。

## 2026-06-06 - 第一版人工 Golden Dataset 完成

### 变更内容
用户在 `eval/datasets/` 下完成第一版人工 golden dataset，包含 `golden.jsonl` 与 `golden.documents.json`。数据集覆盖可回答、不可回答、事实型、方法/流程型、citation/page 可验证和跨文档问题，并确认 `evidence[].doc_key`、页码范围、`evidence[].terms`、`answer_terms` 和参考答案。

### 关键原因
golden dataset 的可信度依赖人工阅读论文后确认问题、证据页码、证据锚点和答案锚点。由用户人工完成可以避免 Agent 在未掌握完整论文内容时生成不可靠问题或错误证据标注。

### 计划差异与原因
原第二阶段任务包含 Agent 起草候选 eval cases，再由用户审核。实际改为用户直接人工完成并确认第一版基线，原因是评测集属于后续优化的基准资产，问题和证据标注必须优先保证可信度，而不是追求自动起草速度。
