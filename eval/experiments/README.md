# 评测实验结果产出规范

本文件说明 `eval/experiments/` 中实验结果的基线选择、命名规则、运行配置记录和人工摘要要求。它用于让新会话或新协作者在继续优化 RAG 链路时，能按同一把尺子产出可复现、可对比、可审核的实验结果。

## 当前主基线

当前默认对比基线是 v3 prompt 口径：

- JSON report：`eval/experiments/baseline_v3_prompt_report.json`
- 人工摘要：`eval/experiments/baseline_v3_prompt_metrics.md`


`.paper_rag/reports/api_index.json` 是早期 API 索引运行记录，指标口径和当前 v3 基线不同。它可用于排查历史问题，但不作为当前优化的默认对照基线。

## v3 基线配置

复现实验或产出新实验时，除非实验目标本身就是改变某项配置，否则应保持以下配置不变：

- dataset：`eval/datasets/golden.jsonl`
- documents：`eval/datasets/golden.documents.json`
- source_dir：`eval/papers`
- index_dir：`.paper_rag/api_index`
- tenant_id：`eval`
- top_k：`3`
- reader：`pdf_reader`
- chunker：`token_window_chunker`，`chunk_size=800`，`chunk_overlap=120`
- embedder：`openai_embedder`，source=`siliconflow`，model=`Qwen/Qwen3-Embedding-4B`
- retriever：`vector_retriever`
- generator：`openai_generator`，source=`siliconflow`，model=`deepseek-ai/DeepSeek-V4-Pro`，`min_score=0.05`，`prompt_version=answer_v4_corrective_mapping`

v3 评测语义以 `expectation` 为准：

- `direct_answer`：需要直接回答并引用证据。
- `corrective_answer`：问题前提有误，需要纠正前提并引用证据。
- `insufficient_detail`：证据能说明论文没有提供某个细节，需要给出有证据支撑的边界说明。
- `out_of_scope_refusal`：固定语料没有相关证据，才按标准拒答评估。

因此，`direct_answer`、`corrective_answer` 和 `insufficient_detail` 都进入 retrieval、answer 和 citation 分母；只有 `out_of_scope_refusal` 进入 refusal 分母。

## 产出文件规则

每次值得留档的实验必须同时产出两类文件：

- `*_report.json`：机器可读的完整评测报告，是后续脚本对比和人工追溯的事实源。
- `*_metrics.md`：人工可读的实验摘要，用于记录实验目的、配置变化、关键指标、失败样本和结论。

文件名应表达实验意图，而不是只写日期或临时编号：

- `prompt_v4_golden_009_report.json`
- `prompt_v4_golden_009_metrics.md`
- `retrieval_bm25_v1_report.json`
- `retrieval_bm25_v1_metrics.md`
- `chunk_structural_v1_report.json`
- `chunk_structural_v1_metrics.md`

单题或少量样本实验可以留档，但文件名必须体现 case 范围，例如 `prompt_v4_golden_005_009_*`。全量回归实验不应复用单题实验文件名。

## metrics 摘要必须包含的内容

`*_metrics.md` 至少包含以下部分：

- 实验目的：本次改动验证什么假设，影响检索、证据命中、答案生成、引用还是拒答。
- 对比基线：默认写 `baseline_3_expectation_*`；如果不是同口径对比，必须说明原因。
- 运行配置：dataset、documents、source_dir、index_dir、tenant_id、top_k、reader、chunker、embedder、retriever、generator、模型来源、模型名、`min_score`、索引状态。
- 汇总指标：`case_count`、`error_count`、`retrieval_hit_rate`、`answer_success_rate`、`citation_hit_rate`、`refusal_success_rate`、`answer_terms_hit_rate`。
- 失败样本：分别列出 retrieval 失败和 answer 失败的 case id。
- 重点样本观察：说明关键 case 是否改善、退化或只是指标口径变化，尤其关注 `golden_005`、`golden_009`、`golden_011`、`golden_012` 和 `golden_cross_001`。
- 结论：写清是否值得继续推进、是否需要调整 dataset、answer_terms、prompt、retrieval 或 citation 策略。

如果启用了 `--judge`，还必须说明 judge 只是并行语义指标，不替代确定性 `answer_success_rate`。如果使用 `eval-judge`，必须说明它没有重新生成答案，只是在历史 report 上补充 judge 结果。

## 运行与复现规则

全量 v3 口径实验示例：

```powershell
paper-rag eval eval\datasets\golden.jsonl `
  --source-dir eval\papers `
  --index-dir .paper_rag\api_index `
  --tenant-id eval `
  --embedding-source siliconflow `
  --embedding-model Qwen/Qwen3-Embedding-4B `
  --chat-source siliconflow `
  --chat-model deepseek-ai/DeepSeek-V4-Pro `
  --top-k 3 `
  --chunk-size 800 `
  --chunk-overlap 120 `
  --min-score 0.05 `
  --report-json eval\experiments\<experiment_name>_report.json
```

单题或少量样本快速验证可以使用 `--case-id`，但不能用单题结果代替全量回归结论：

```powershell
paper-rag eval eval\datasets\golden.jsonl `
  --case-id golden_005 `
  --case-id golden_009 `
  --source-dir eval\papers `
  --index-dir .paper_rag\api_index `
  --tenant-id eval `
  --embedding-source siliconflow `
  --embedding-model Qwen/Qwen3-Embedding-4B `
  --chat-source siliconflow `
  --chat-model deepseek-ai/DeepSeek-V4-Pro `
  --top-k 3 `
  --chunk-size 800 `
  --chunk-overlap 120 `
  --min-score 0.05 `
  --report-json eval\experiments\<experiment_name>_report.json
```

如果实验改动涉及 PDF 解析、chunk 切分、embedding 模型、embedding source、索引 schema 或索引构建逻辑，必须重建索引后再产出 report，并在 metrics 中记录新索引状态。只改答案 prompt、`answer_terms`、judge 或答案后处理时，可以复用 `.paper_rag/api_index`，但必须在 metrics 中写明复用索引。

## 判断实验收益的规则

判断收益时优先看同口径全量结果，不要只看单题表现：

- retrieval 优化优先看 `retrieval_hit_rate` 和 retrieval 失败 case 是否减少。
- answer prompt 或生成策略优化优先看 `answer_success_rate`、`answer_terms_hit_rate` 和 answer 失败原因是否迁移。
- 引用策略优化优先看 `citation_hit_rate`，同时检查 citation 是否真实覆盖人工 evidence 页码。
- 拒答策略优化优先看 `refusal_success_rate`，同时确认没有把 `insufficient_detail` 或 `corrective_answer` 错误变成标准拒答。

外部 chat/embedding API 存在非确定性。小幅波动不能直接视为稳定收益；结论应结合整体趋势、失败样本迁移和关键样本答案文本一起判断。

