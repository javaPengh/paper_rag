# Paper RAG 评测集与评测报告说明

本目录用于维护 RAG 优化所需的固定评测语料、人工 golden dataset 和评测报告说明。
评测目标不是自动生成问题，而是用一组人工审核过的问题稳定衡量后续改动是否真的提升
检索、回答、引用和拒答能力。

## 目录结构

- `papers/`：固定评测 PDF 语料。评测集中的 `source_path` 应指向这里的文件。
- `datasets/golden.documents.json`：文档短键映射表，用短键连接 eval case 和真实 PDF。
- `datasets/golden.jsonl`：人工维护的 golden dataset，每行是一条 eval case。
- `.paper_rag/eval_index/`：运行评测时生成或复用的本地索引目录，不纳入版本管理。
- `.paper_rag/reports/`：建议保存 JSON report 的运行目录，不纳入版本管理。

## Golden Dataset 人工审核

人工维护评测集时，重点审核 `datasets/golden.jsonl` 和
`datasets/golden.documents.json`。

`golden.documents.json` 中每个 key 是稳定文档短键：

```json
{
  "think_in_space": {
    "source_path": "eval/papers/think in space.pdf",
    "notes": "固定评测论文"
  }
}
```

`golden.jsonl` 中每行是一条评测问题：

```json
{
  "id": "golden_001",
  "question": "问题文本",
  "answerable": true,
  "evidence": [
    {
      "doc_key": "think_in_space",
      "page_start": 3,
      "page_end": 3,
      "terms": ["原文锚点词"]
    }
  ],
  "answer_terms": ["答案应覆盖的关键词"],
  "reference_answer": "可选的人工参考答案",
  "notes": "人工审核备注"
}
```

字段含义：

- `id`：单条 case 的稳定 ID。后续报告和回归对比依赖它，不应随意改名。
- `question`：提交给 RAG 系统的自然语言问题。
- `answerable`：固定评测语料是否足以回答该问题。
- `evidence`：可回答问题应命中的人工证据。不可回答问题可以为空。
- `evidence[].doc_key`：证据所在文档短键，必须存在于 `golden.documents.json`。
- `evidence[].page_start` / `page_end`：证据页码范围，使用从 1 开始的闭区间。
- `evidence[].terms`：期望出现在检索证据文本里的原文锚点词，用于判断是否真正命中证据。
- `answer_terms`：期望出现在最终答案或拒答文本里的关键词。
- `reference_answer`：人工参考答案，当前主要用于人工复核，后续可扩展 answer quality 指标。
- `notes`：人工标注备注，不参与自动评分。

审核原则：

- 可回答问题必须能从固定 PDF 中找到明确证据。
- 不可回答问题必须确认固定语料没有足够证据回答。
- `evidence[].terms` 应选择能定位原文的短词或短语，不要填过长段落。
- `answer_terms` 应选择判断答案是否覆盖核心信息所需的关键词，不要要求完整复述。
- 跨文档问题应在 `evidence` 中写多组证据，每组证据分别填写自己的 `doc_key` 和页码。

## 运行评测

本地离线烟测使用 hash embedding 和抽取式答案生成，不调用外部 API。它适合验证评测流程
和报告结构是否稳定，不代表真实模型质量。

```powershell
conda activate paper_rag

paper-rag eval eval\datasets\golden.jsonl `
  --source-dir eval\papers `
  --index-dir .paper_rag\eval_index `
  --tenant-id eval `
  --local `
  --top-k 3 `
  --chunk-size 800 `
  --chunk-overlap 120 `
  --report-json .paper_rag\reports\eval_report.json
```

如果要使用 API embedding 和 LLM，将 `--local` 改成 `--api`，并先复制
`.env.example` 为 `.env` 填写 API key：

```powershell
Copy-Item .env.example .env
```

真实模型评测建议使用独立索引目录，避免和本地 hash embedding 索引混用：

```powershell
paper-rag eval eval\datasets\golden.jsonl `
  --source-dir eval\papers `
  --index-dir .paper_rag\eval_index_api `
  --tenant-id eval `
  --api `
  --embedding-source siliconflow `
  --embedding-model Qwen/Qwen3-Embedding-4B `
  --chat-source siliconflow `
  --chat-model deepseek-ai/DeepSeek-V4-Pro `
  --top-k 3 `
  --chunk-size 800 `
  --chunk-overlap 120 `
  --report-json .paper_rag\reports\eval_report_api.json
```

`EMBEDDING_SOURCE` / `CHAT_SOURCE` 决定当前选中的供应商，`EMBEDDING_MODEL` / `CHAT_MODEL`
决定当前选中的模型。它们不是兜底默认值，评测使用外部 API 时缺少任一项都会直接报错。前端和 CLI 可选模型来自 `SILICONFLOW_*_MODELS`、`OPENAI_*_MODELS`
这类列表变量；新增同一供应商下的模型时追加到列表即可，原模型仍会保留。
如果某个来源的某类模型列表为空，且没有为该类别配置当前选中模型，该来源不会出现在对应下拉框中。
不同 embedding 来源或模型应使用不同 `--index-dir`，否则向量空间会混在一起，评测结果不可比。

## JSON Report 字段说明

JSON report 是每次评测后最适合留档和对比的指标文件。控制台输出用于快速查看，JSON
report 用于后续回归对比、人工审核和脚本分析。

顶层字段：

- `schema_version`：报告结构版本。后续字段结构发生不兼容变化时递增。
- `dataset`：本次评测使用的数据集路径、文档映射路径和样本数。
- `run`：本次运行的索引目录、语料目录、租户、Top-k、RAG 组件配置和索引状态。
- `summary`：整体指标汇总，是每次优化后最先看的区域。
- `cases`：逐 case 明细，用来解释某个指标为什么通过或失败。

`summary` 字段：

- `summary.case_count`：本次评测样本总数。
- `summary.error_count`：检索或答案生成流程发生错误的样本数。
- `summary.retrieval`：检索指标，判断 Top-k 是否命中人工 evidence。
- `summary.answer`：可回答问题的答案成功指标，以及 `answer_terms` 覆盖情况。
- `summary.citation`：可回答问题的 citation 是否命中人工 evidence 文档和页码。
- `summary.refusal`：不可回答问题是否正确拒答。
- `summary.failed_case_ids.retrieval`：检索未命中的可回答 case ID。
- `summary.failed_case_ids.answer`：answer、citation 或 refusal 未通过的 case ID。

`summary.retrieval` 常用字段：

- `top_k`：本次检索使用的 Top-k。
- `answerable_case_count`：纳入 retrieval hit@k 分母的可回答样本数。
- `answerable_hit_count`：Top-k 命中全部 expected evidence 的可回答样本数。
- `retrieval_hit_rate`：`answerable_hit_count / answerable_case_count`。
- `missed_case_ids`：检索未命中的可回答样本 ID。
- `unanswerable_case_count`：不可回答样本数，只做诊断，不计入 hit@k。

`summary.answer` 常用字段：

- `case_count`：应当成功回答的可回答样本数。
- `success_count`：通过 answer/citation/answer_terms 综合判断的可回答样本数。
- `success_rate`：`success_count / case_count`。
- `answer_terms_case_count`：检查 `answer_terms` 的样本数。
- `answer_terms_hit_count`：答案文本覆盖全部 `answer_terms` 的样本数。
- `answer_terms_hit_rate`：`answer_terms_hit_count / answer_terms_case_count`。

`summary.citation` 常用字段：

- `case_count`：需要 citation 命中证据的可回答样本数。
- `hit_count`：citation 命中全部 expected evidence 的样本数。
- `hit_rate`：`hit_count / case_count`。

`summary.refusal` 常用字段：

- `case_count`：应当拒答的不可回答样本数。
- `success_count`：正确拒答且没有 citation 的样本数。
- `success_rate`：`success_count / case_count`。

`run.rag_config` 常用字段：

- `reader.id`：本次解析源文档使用的 Reader 组件。
- `chunker.id`：本次切分页面文本使用的 Chunker 组件。
- `chunker.parameters.chunk_size`：构建索引时使用的 chunk token 窗口大小。
- `chunker.parameters.chunk_overlap`：相邻 chunk 之间重复的 token 数。
- `embedder.id` / `embedder.source` / `embedder.model`：文档和问题 embedding 使用的组件、来源与模型。
- `retriever.id` / `retriever.parameters.top_k`：证据召回使用的组件与 Top-k。
- `generator.id` / `generator.source` / `generator.model`：答案生成使用的组件、来源与模型。
- `generator.parameters.min_score`：证据进入答案生成前的最低检索分数。

`cases[]` 常用字段：

- `id`：case ID。
- `question`：评测问题。
- `answerable`：人工标注是否可回答。
- `status`：运行状态，`ok` 表示流程完成，`error` 表示流程出错。
- `retrieval_state`：`hit`、`miss`、`diagnostic` 或 `unknown`。
- `answer_state`：`pass`、`fail` 或 `unknown`。
- `retrieved_chunk_ids`：检索返回的 chunk ID。
- `used_chunk_ids`：答案生成实际使用的 chunk ID。
- `citation_labels`：答案返回的 citation 标签。
- `insufficient_evidence`：答案生成器是否认为证据不足。
- `answer_text`：生成答案文本。
- `retrieval_metrics`：检索命中明细。
- `answer_metrics`：答案、引用和拒答明细。
- `failures.retrieval`：检索失败原因，是人工排查检索问题时最重要的字段。
- `failures.answer`：答案、引用或拒答失败原因，是人工排查生成问题时最重要的字段。

## 可复现验收命令

评测功能完成后，可以用以下命令复现当前基线：

```powershell
conda activate paper_rag

paper-rag eval eval\datasets\golden.jsonl `
  --source-dir eval\papers `
  --index-dir .paper_rag\eval_index `
  --tenant-id eval `
  --local `
  --top-k 3 `
  --chunk-size 800 `
  --chunk-overlap 120 `
  --report-json .paper_rag\reports\eval_report.json

pytest
ruff check src tests scripts
```
