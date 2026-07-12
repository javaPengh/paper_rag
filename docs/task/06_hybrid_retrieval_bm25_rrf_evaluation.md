# Task 6：BM25 与向量 Hybrid 检索评测

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除或取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，只勾选对应任务，不批量勾选。

## 目标

在当前向量检索基线之上加入 BM25 稀疏检索，并使用 Reciprocal Rank Fusion（RRF）融合
两路候选，验证是否能改善“证据文本已入库但未进入最终 Top-3”的问题。

重点观察 `golden_010`：其目标证据在 `think in space.pdf` p.3–p.4，包含
`Benchmark Construction`、`Data Collection and Unification`、`Question-Answer Generation`
和 `Human-in-the-loop Quality Review`，但 v3 向量检索未召回目标页。

## 实验边界

- 最终返回给答案生成器的结果仍为 Top-3；不改变现有 `top_k=3`。
- 向量检索和 BM25 检索各自仅扩大内部候选池，初始 `candidate_top_k=10`。
- 两路候选去重后以 RRF 融合排序，再截取最终 Top-3。
- 本任务不引入 Cross-encoder、LLM reranker 或其他模型精排。
- 不修改 PDF 解析、chunk 规则、embedding 模型、答案生成模型、答案提示词或 Judge 提示词。
- 评测前用户已将 `golden_012` 改为 `direct_answer` 和 `answerable=true`；该变更不属于
  Hybrid 实现，导致全量结果与 v3 的原始分母不可直接对比，详见实验摘要。
- 不处理图表、表格和页面图像证据；这些能力属于后续独立任务。

```text
原始问题
  ├─ 向量检索 Top-10
  └─ BM25 检索 Top-10
          ↓
  去重 + RRF 融合排序
          ↓
       最终 Top-3
          ↓
       答案生成
```

## 必须先确认的跨语言约束

当前评测问题主要为中文，论文 chunk 主要为英文。原始中文问题直接进入英文 BM25 不会产生
可信的词面匹配，因此不能静默实现为“中文 BM25”。

- [x] 确认 BM25 分支使用复用答案生成模型自动生成的英文检索词。

推荐方案是：向量分支保持原始中文问题；BM25 分支使用单独生成的英文关键词检索词，并记录
其模型、提示词版本和最终文本。该方案的评测结论必须称为“英文稀疏查询 + 向量 Hybrid”，
不能误称为纯 BM25 Hybrid。若采用其他方案，例如为 chunk 建立中文关键词索引，必须另行记录
索引内容变化并重建相应词法索引。

无论选择哪种方案，缺少必要模型或词法索引时必须明确报错；禁止回退为只运行向量检索并仍
标记为 Hybrid。

## 设计要求

### BM25 索引与 Retriever

- [x] 基于已持久化的相同 chunk 构建 BM25 词法索引，不重新解析 PDF、不改变 chunk ID。
- [x] BM25 索引按 tenant 隔离，并与 chunk ID、文档、页码保持一一对应。
- [x] 新增 `bm25_retriever`，返回与现有 Retriever 一致的 `SearchResult`，并记录词法分数。
- [x] 新增 `hybrid_retriever`，组合向量与 BM25 候选、按 chunk ID 去重并执行确定性 RRF。
- [x] RRF 常量初始设为 `60`；候选池大小和 RRF 常量必须写入运行配置与实验报告。
- [x] RRF 对两路都未命中的 chunk 不产生结果；任一路命中的 chunk 都可进入融合候选池。

### 运行配置与追溯

- [x] `run.rag_config.retriever` 记录 `hybrid_retriever`、最终 `top_k=3`、每路 `candidate_top_k=10`、RRF 常量和 BM25 索引状态。
- [x] 每个 case 记录向量候选、BM25 候选、融合后 Top-3、各自排名和融合分数，便于定位 `golden_010` 的收益或退化原因。
- [x] CLI、API 与 eval 复用同一 Hybrid Retriever，不得各自实现融合逻辑。
- [x] 默认 Retriever 保持 `vector_retriever`；只有显式选择 Hybrid 时才启用该策略。

## 测试与评测

### 自动化测试

- [x] 测试 BM25 以 chunk ID 返回正确文档、页码和 tenant 隔离结果。
- [x] 测试 RRF 对候选去重、同路 / 双路命中、排名并列和空候选的确定性行为。
- [x] 测试 Hybrid 最终只返回调用方要求的 Top-3，内部 `candidate_top_k` 不改变生成器上下文数量。
- [x] 测试中文问题与英文 BM25 检索词的对齐策略、缺失配置和失败场景均明确报错。
- [x] 测试报告完整记录两路候选和融合结果。
- [x] 运行全量测试，确认默认向量检索行为不变。

### 全量评测

- [x] 使用与 `baseline_v3_prompt_*` 相同的 documents、source_dir、index_dir、tenant_id、reader、chunker、embedder、generator、top_k 和 `min_score`；dataset 因用户调整 `golden_012` 而存在分母差异。
- [x] 运行 `eval/datasets/golden.jsonl` 全量评测，重点检查 `golden_010`、`golden_cross_001`、`golden_001`、`golden_006`、`golden_008`。
- [x] 输出 `eval/experiments/retrieval_hybrid_bm25_rrf_v1_report.json`。
- [x] 输出 `eval/experiments/retrieval_hybrid_bm25_rrf_v1_metrics.md`。

## 结果摘要要求

实验摘要除遵守 `eval/experiments/README.md` 的通用要求外，还必须包含：

- BM25 检索词的语言策略、模型与提示词版本，或索引文本扩展方式。
- 向量 / BM25 各自 Top-10 的候选命中情况，以及 RRF 后的最终 Top-3。
- `golden_010` 的 p.3–p.4 是否分别进入 BM25 候选、融合候选和最终 Top-3。
- retrieval_hit_rate、answer_success_rate、citation_hit_rate、refusal_success_rate、answer_terms_hit_rate、error_count 与 v3 的变化。
- 新增命中、由命中变为未命中以及仅候选池命中但未进入最终 Top-3 的 case。
- 检索时延与 BM25 索引构建成本；不将模型 rerank 成本混入本实验。
- 结论：Hybrid 是否值得保留；若目标页进入候选池但未进 Top-3，后续才考虑独立的 reranker 实验。

## 验收标准

- [x] Hybrid 不改变最终 Top-3 数量，也不引入额外 reranker。
- [x] Hybrid 的所有新增参数、BM25 查询策略和逐 case 融合依据可追溯。
- [x] 默认向量检索和 v3 基线保持可复现。
- [x] 全量实验报告与人工摘要均已产出，并说明是否真正改善了完整证据召回。
