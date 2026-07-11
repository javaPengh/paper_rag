# 英文查询翻译检索 v1 评估指标记录

## 实验目的

验证将原始问题翻译为英文后，仅将英文结果传给向量检索器，是否能改善英文论文语料的
证据召回、答案和引用指标。答案生成、答案对象和评测记录仍使用原始问题。

## 对比基线与运行配置

- 对比基线：`baseline_v3_prompt_report.json` / `baseline_v3_prompt_metrics.md`。
- 当前 commit：`a40accb`；v3 基线 commit：`2112fa2`。
- dataset：`eval/datasets/golden.jsonl`；documents：`eval/datasets/golden.documents.json`。
- source_dir：`eval/papers`；index_dir：`.paper_rag/api_index`；tenant_id：`eval`。
- reader：`pdf_reader`；chunker：`token_window_chunker`，chunk_size=`800`，chunk_overlap=`120`。
- embedder：`openai_embedder`，source=`siliconflow`，model=`Qwen/Qwen3-Embedding-4B`。
- retriever：`vector_retriever`，top_k=`3`。
- generator：`openai_generator`，source=`siliconflow`，model=`deepseek-ai/DeepSeek-V4-Pro`，min_score=`0.05`，prompt_version=`answer_v4_corrective_mapping`。
- 查询翻译：enabled=`true`，复用 generator 的 source=`siliconflow`、model=`deepseek-ai/DeepSeek-V4-Pro`，prompt_version=`query_translation_v1_english_retrieval`。
- 索引状态：status=`ready`，documents=`2`，chunks=`117`，indexed_chunks=`0`；未重建索引。
- Judge：enabled=`false`。
- 原始 JSON report：`eval/experiments/retrieval_query_translation_en_v1_report.json`。

翻译调用失败、空翻译或答案生成器不是外部聊天模型时会明确报错；本实验没有中文检索回退。

## 汇总指标

| 指标 | v3 基线 | 英文翻译检索 v1 | 变化 |
| --- | ---: | ---: | ---: |
| case_count | 13 | 13 | 0 |
| error_count | 0 | 0 | 0 |
| retrieval_hit_rate | 58.33% (7/12) | 50.00% (6/12) | -8.33pp，-1 case |
| answer_success_rate | 41.67% (5/12) | 41.67% (5/12) | 0 |
| citation_hit_rate | 66.67% (8/12) | 58.33% (7/12) | -8.33pp，-1 case |
| refusal_success_rate | 0.00% (0/1) | 0.00% (0/1) | 0 |
| answer_terms_hit_rate | 38.46% (5/13) | 38.46% (5/13) | 0 |

## 检索与答案变化

- 没有新增 retrieval hit。
- `golden_004` 从 retrieval=`hit`、answer=`pass` 退化为 retrieval=`miss`、answer=`fail`，是检索和引用指标下降的直接来源。
- `golden_007` 的 retrieval 仍为 `hit`，但 answer 从 `fail` 变为 `pass`；这抵消了 `golden_004` 的答案成功率退化，因此整体 answer_success_rate 持平。
- `golden_001`、`golden_006`、`golden_008`、`golden_010`、`golden_cross_001` 仍未命中；翻译没有改善既有检索失败。

## 重点样本观察

| case_id | v3 | 英文翻译检索 v1 | 观察 |
| --- | --- | --- | --- |
| golden_005 | retrieval=`hit`，answer=`fail` | retrieval=`hit`，answer=`fail` | 翻译后的检索词仍没有解决“论文未披露具体插帧算法”的答案表达问题。 |
| golden_009 | retrieval=`hit`，answer=`pass` | retrieval=`hit`，answer=`pass` | 保持通过；翻译没有带来额外收益。 |
| golden_011 | retrieval=`hit`，answer=`pass` | retrieval=`hit`，answer=`pass` | 保持通过。 |
| golden_012 | retrieval=`diagnostic`，answer=`fail` | retrieval=`diagnostic`，answer=`fail` | 仍未正确标准拒答；翻译不是该问题的有效方向。 |
| golden_cross_001 | retrieval=`miss`，answer=`fail` | retrieval=`miss`，answer=`fail` | 跨文档目标页仍未召回。 |
| golden_004 | retrieval=`hit`，answer=`pass` | retrieval=`miss`，answer=`fail` | 翻译将具体模型、数值与比较约束概括成泛化的性能比较，丢失了 evidence 需要的关键实体与数字。 |

`golden_004` 的英文检索词为：

> Comparison of spatial understanding performance on VSI-Bench between top open-source multimodal large models and closed-source commercial large models

该查询没有保留人工证据要求中的 `LLaVA-Video-72B`、`LLaVA-OneVision-72B`、`4%`、`5%` 等具体锚点，符合此次退化现象。

## 成本与时延

- 本次全量运行约耗时 423 秒，包含 13 次查询翻译、13 次 query embedding 和 13 次答案生成外部调用。
- 当前运行报告不持久化供应商 token 用量或账单金额，因此无法从现有产物给出可信成本数值。

## 失败样本

- retrieval 失败：golden_001, golden_004, golden_006, golden_008, golden_010, golden_cross_001。
- answer 失败：golden_001, golden_004, golden_005, golden_006, golden_008, golden_010, golden_012, golden_cross_001。

## 结论

英文查询翻译 v1 **不应合并为默认检索策略**。在同一 v3 口径和同一索引下，它没有新增任何证据命中，反而使 retrieval_hit_rate 与 citation_hit_rate 各下降 1 个 case；答案成功率只是因 `golden_007` 的随机或证据排序变化抵消了 `golden_004` 的退化，并非稳定收益。

若后续继续研究查询改写，应将“保留 evidence 关键实体、数字、模型名和页内锚点”的约束作为独立提示词实验，并与本次 v1 和 v3 基线分别进行全量配对比较；不能把它与其他检索或答案策略同时修改。
