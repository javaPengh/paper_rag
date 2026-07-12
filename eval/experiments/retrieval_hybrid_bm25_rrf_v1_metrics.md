# Hybrid 检索（英文稀疏查询 + BM25 + RRF）评估指标记录

## 实验结论

本实验**不建议将 Hybrid Retriever 设为默认检索策略**。在 `candidate_top_k=10`、
`rrf_k=60`、最终 `top_k=3` 的配置下，完整证据检索命中数与 v3 可比口径完全相同
（均为 `7/12`）。重点样本 `golden_010` 的目标证据虽被 BM25 召回，却在 RRF 排序后
位列第 6，未进入最终 Top-3，因此没有解决该题的证据缺失问题。

本次答案与引用指标的表面上升不能归因于 Hybrid 检索：检索命中状态没有变化，且答案
生成使用外部模型，单次输出存在非确定性。本报告将其记录为一次观察，不作为策略收益。

## 运行配置

- 记录时间：2026-07-11
- dataset：`eval/datasets/golden.jsonl`
- documents：`eval/datasets/golden.documents.json`
- source_dir：`eval/papers`
- index_dir：`.paper_rag/api_index`
- tenant_id：`eval`
- 最终返回数量：`top_k=3`
- 向量候选池：`candidate_top_k=10`
- BM25 候选池：`candidate_top_k=10`
- 融合方式：按 chunk ID 去重后执行等权 Reciprocal Rank Fusion（`rrf_k=60`）
- BM25 索引：运行时基于已有的 117 个持久化 chunk 构建；不重新解析 PDF，不改变 chunk ID
- BM25 参数：`k1=1.5`，`b=0.75`
- 稠密查询：原始中文问题，`Qwen/Qwen3-Embedding-4B`
- 稀疏查询：复用答案生成模型，将原始问题转换为英文关键词检索词；
  `siliconflow / deepseek-ai/DeepSeek-V4-Pro`，提示词版本
  `sparse_query_v1_english_keywords`
- 答案生成：`siliconflow / deepseek-ai/DeepSeek-V4-Pro`，`min_score=0.05`，
  提示词版本 `answer_v4_corrective_mapping`
- Judge：未启用
- 运行耗时：约 448.7 秒（包含 13 次英文稀疏查询、向量查询、答案生成及评测；未单独采集
  BM25 建索引与检索耗时）
- 原始 JSON report：`retrieval_hybrid_bm25_rrf_v1_report.json`

## 与 v3 的可比性说明

执行本实验前，`golden_012` 被改为 `direct_answer` 且 `answerable=true`；而 v3 中该题为
`out_of_scope_refusal` 且 `answerable=false`。因此两个原始汇总分母不同，不能将原始汇总
直接视作严格的 v3 对照。

下表使用两次运行都可比的 12 个可回答样本（排除 `golden_012`）计算。该处理只用于分析
可比性，**不修改当前数据集，也不掩盖 Hybrid 原始报告的全量结果**。

| 指标 | v3（12 题） | Hybrid（排除 golden_012，12 题） | 变化 |
| --- | ---: | ---: | ---: |
| retrieval_hit_rate | 58.33%（7/12） | 58.33%（7/12） | 0 |
| answer_success_rate | 41.67%（5/12） | 58.33%（7/12） | +2 |
| citation_hit_rate | 66.67%（8/12） | 91.67%（11/12） | +3 |
| answer_terms_hit_rate | 41.67%（5/12） | 58.33%（7/12） | +2 |
| error_count | 0 | 0 | 0 |

`answer_terms_hit_rate` 的 v3 原始文档按 13 题（含当时的拒答题）统计为 `5/13`；为避免
分母混用，此表改为对可回答的 12 题重新计算。

## Hybrid 原始全量结果

当前数据集的 13 题全部属于可回答题，原始报告如下：

| 指标 | Hybrid 数值 | 计数 |
| --- | ---: | ---: |
| case_count | 13 | - |
| error_count | 0 | - |
| retrieval_hit_rate | 61.54% | 8/13 |
| answer_success_rate | 53.85% | 7/13 |
| citation_hit_rate | 92.31% | 12/13 |
| refusal_success_rate | 0.00% | 0/0 |
| answer_terms_hit_rate | 53.85% | 7/13 |

检索失败：`golden_001`、`golden_006`、`golden_008`、`golden_010`、
`golden_cross_001`。

答案失败：`golden_001`、`golden_005`、`golden_006`、`golden_010`、
`golden_012`、`golden_cross_001`。

## 重点样本与候选池分析

### golden_010：候选池召回不等于最终证据召回

问题为“构建 VSI-Bench，作者具体做了哪些工作？”，目标页为 `think in space.pdf` p.3–p.4。
自动生成的英文 BM25 查询为 `VSI-Bench construction`。

| 阶段 | 目标 chunk `7d0bda05c310e1f1755e6dc6` 的位置 | 是否进入答案上下文 |
| --- | ---: | --- |
| 向量 Top-10 | 未命中 | 否 |
| BM25 Top-10 | 第 2 | 否 |
| RRF 融合候选 | 第 6 | 否 |
| 最终 Top-3 | 未进入 | 否 |

最终前三个 chunk 都同时或多次被两路检索召回：`e5e5b4...`、`472e0b...`、
`fd518e...`。目标 chunk 只在 BM25 一路排名第 2，RRF 得分为 `1 / (60 + 2)`；
相比之下，双路重复命中的 chunk 获得两项 RRF 得分之和，因而挤出了目标 chunk。

这说明当前失败的具体位置不是“BM25 没有找到词面相关证据”，而是“等权 RRF 偏好双路
重复命中，最终截断丢失单路高质量候选”。该实验没有引入 reranker，且不应在本结果上
直接宣称 Hybrid 已改善 `golden_010`。

### 其他关注样本

- `golden_001`、`golden_006`、`golden_008`、`golden_cross_001`：最终检索仍未覆盖完整
  标注证据，Hybrid 没有减少检索失败样本。
- `golden_007`、`golden_008`：本次答案从 v3 的 fail 变为 pass，但其检索命中状态没有改变。
  由于外部模型生成并非确定性，不能将其视作 Hybrid 的因果收益。
- `golden_012`：检索到文本证据但答案仍失败，符合该题依赖图表柱状信息、当前链路没有
  图像理解能力的预期。Hybrid 仅改变文本检索，不能覆盖此类证据。

## 追溯信息

每个 case 在 JSON report 的 `retrieval_trace` 字段中保存：

- 原始中文问题和生成的英文稀疏查询；
- 向量 Top-10、BM25 Top-10 的 chunk ID、排名和各自分数；
- 去重后的 RRF 融合候选、排名及 RRF 分数；
- 实际进入答案生成器上下文的最终 Top-3。

CLI、API 和评测 runner 均通过同一个 `hybrid_retriever` 实现该行为。默认仍为
`vector_retriever`，只有显式传入 `--retriever hybrid_retriever` 才会启用 Hybrid。

## 最终判断

- 本次实验验证了英文稀疏查询 + BM25 能把 `golden_010` 的目标文本送入候选池；
  但现有等权 RRF + Top-3 截断没有把它送入答案上下文。
- 因此，当前参数下 Hybrid 不应合并为默认策略，也不能作为解决文本证据漏召回的有效改进。
- 图表题 `golden_012` 的失败与 Hybrid 无关；它需要后续独立的论文图像解析、图文关联与
  多模态检索任务，不能用调整文本检索参数替代。
- 若继续探索文本 Hybrid，应将候选池大小、融合权重或精排策略作为**独立的单变量实验**；
  不应在本次结果上静默改变 RRF 参数或加入 reranker。
