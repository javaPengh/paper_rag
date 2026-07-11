# Task 6：英文查询翻译检索与 v3 基线评测

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除或取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，只勾选对应任务，不批量勾选。

## 目标

验证“将原始问题翻译为英文后，仅用英文问题进行向量检索”是否能改善当前英文论文语料上的检索、答案和引用指标。

本任务是独立的单变量实验：实现、评测和留档都必须能将结果与
`baseline_v3_prompt_*` 严格对比。

## 实验边界

- 原始中文问题传给翻译模型，翻译结果只传给 Retriever。
- 答案生成仍使用原始问题和检索到的证据，不能改为使用英文问题。
- 不修改 golden dataset、文档映射、PDF 语料、索引内容、embedding 模型、chunk 配置、top-k、答案提示词、Judge 提示词或答案生成模型。
- 翻译提示词、翻译模型和查询转换逻辑是本实验唯一允许改变的运行变量。
- 本实验不引入翻译失败后改用原始中文问题检索的回退策略；翻译失败必须产生明确错误并记录到报告。

## 翻译模型决策

翻译默认复用本次答案生成器已经选择的聊天模型、来源、API 密钥和端点，不增加独立的
翻译模型配置。启用翻译时，如果答案生成器不是可调用聊天模型，则必须报出明确错误，
不得静默跳过翻译或回退为中文检索。

## 设计要求

### 提示词与翻译组件

- [x] 在 `src/paper_rag/prompts/translation.py` 集中维护翻译提示词和稳定版本标识。
- [x] 翻译提示词要求保留论文名称、方法名、指标、缩写、数字、否定条件和专有名词；不得补充原问题未表达的事实或检索词。
- [x] 新增明确的查询翻译边界，负责接收原始问题并返回英文检索问题；CLI、API 和评测不能各自实现翻译调用。
- [x] 翻译结果必须与原问题、翻译模型来源、模型名、提示词版本一起记录，便于逐 case 审核。

### 配置与可追溯性

- [x] 翻译模型默认复用答案生成器实际使用的来源和模型，并在报告中显式记录该事实。
- [x] 评测报告记录查询翻译是否启用、翻译模型来源、模型名、提示词版本和逐 case 英文检索问题。
- [x] 保持现有五类 RAG 组件配置记录不变；查询翻译作为检索前运行配置单独记录，避免误称为已有 Retriever 的参数。
- [x] 缺失翻译模型配置、模型调用失败或返回空翻译时，抛出包含缺失项或失败原因的明确错误。

### 运行链路

```text
原始问题（中文）
  -> 英文查询翻译
  -> 英文问题 embedding
  -> 向量 Retriever
  -> 原始问题 + 检索证据
  -> 答案生成与引用
```

- [x] 确保只有检索问题发生变化，答案对象中的 `question` 仍保存原始问题。
- [x] 因为本任务不改变语料、切分或 embedding 模型，复用 `.paper_rag/api_index`，不得重建索引。

## 测试与评测

### 自动化测试

- [x] 测试翻译提示词位于 `paper_rag.prompts`，且具有版本标识。
- [x] 测试翻译调用接收原始问题，并将英文结果传给 Retriever。
- [x] 测试答案生成仍接收原始问题。
- [x] 测试答案生成器缺少聊天模型、空翻译和翻译调用失败均产生明确错误，不发生中文检索回退。
- [x] 测试评测报告包含翻译运行配置和逐 case 翻译结果。
- [x] 运行全量测试，确认未启用翻译时的既有 CLI、API 和评测行为不变。

### 全量评测

- [x] 使用与 v3 基线完全相同的 dataset、documents、source_dir、index_dir、tenant_id、top-k、reader、chunker、embedder、retriever、generator、答案提示词和 `min_score`。
- [x] 在启用查询翻译后运行 `eval/datasets/golden.jsonl` 全量评测。
- [x] 输出 `eval/experiments/retrieval_query_translation_en_v1_report.json`。
- [x] 输出 `eval/experiments/retrieval_query_translation_en_v1_metrics.md`。

评测命令中的 embedding 与答案生成配置应与
`eval/experiments/README.md` 的 v3 基线配置一致；翻译模型复用同一次运行的答案生成模型。

## 结果摘要要求

`retrieval_query_translation_en_v1_metrics.md` 除遵守 `eval/experiments/README.md` 的通用要求外，还必须包含：

- 实验假设：英文查询翻译改善英文论文语料的向量检索。
- 对比对象：`baseline_v3_prompt_report.json` 与 `baseline_v3_prompt_metrics.md`。
- 翻译模型来源、模型名、提示词版本和失败策略。
- 全量汇总指标：`retrieval_hit_rate`、`answer_success_rate`、`citation_hit_rate`、`refusal_success_rate`、`answer_terms_hit_rate`、`error_count`。
- 逐 case 检索变化：新增命中、由命中变为未命中、命中未变化；重点检查 `golden_005`、`golden_009`、`golden_011`、`golden_012` 和 `golden_cross_001`。
- 关键 case 的原始问题、英文检索问题、检索证据变化和答案变化。
- 成本与时延观察，以及翻译调用错误数。
- 结论：是否值得保留该策略；若保留，是否需要继续比较翻译模型或提示词；若不保留，说明主要退化样本和原因。

## 验收标准

- [x] 所有翻译、答案和 Judge 提示词均只由 `src/paper_rag/prompts/` 管理。
- [x] 翻译策略启用时，报告能完整追溯模型、提示词版本和每个 case 的英文检索问题。
- [x] 翻译策略仅改变 Retriever 的输入，不改变原始问题、索引或答案生成配置。
- [x] 全量实验报告和人工摘要均已产出，且与 v3 基线使用同一评测口径。
- [x] 结论基于汇总指标、逐 case 变化和关键答案文本，而非单个样本或单一百分比。
