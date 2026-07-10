# 基线 v2 评估指标记录

## 指标含义

- `case_count`：本次评估覆盖的样本总数。
- `error_count`：评估运行中发生检索或答案生成异常的样本数，非模型答错。
- `retrieval_hit_rate`：需要证据作答的样本中，Top-k 检索结果是否命中全部人工标注 evidence 的比例。
- `answer_success_rate`：需要证据作答的样本中，最终答案同时满足非错误拒答、答案词、citation 命中等规则的比例。
- `citation_hit_rate`：需要证据作答的样本中，答案 citation 是否覆盖人工标注 evidence 文档和页码的比例。
- `refusal_success_rate`：`out_of_scope_refusal` 样本中，系统是否正确标准拒答且不返回 citation 的比例。
- `answer_terms_hit_rate`：所有样本中，答案文本是否覆盖 `answer_terms` 的比例。
- `expectation`：评测期望类型，区分直接回答、纠错回答、细节缺失说明和语料外拒答。
- `insufficient_evidence`：答案生成器是否认为证据不足并返回标准拒答。
- `used_chunk_ids`：答案生成阶段实际进入上下文并被用作证据的 chunk ID。

## 本次基线说明

- 本文件是评测语义修复后的 v2 基线，不与旧基线直接做优化收益比较。
- v2 将 `corrective_answer` 和 `insufficient_detail` 纳入需要引用证据作答的样本，只把 `out_of_scope_refusal` 作为标准拒答。
- 本次评估复用上一版 API 基线的 index、模型、Top-k、chunk 和 `min_score` 配置。
- 本次使用外部 chat/embedding API，模型输出存在非确定性；后续对比应重点看整体趋势和失败 case 迁移。

## 运行配置

- 记录时间：2026-07-09T20:40:40
- commit：`a3977b5`
- dataset：`D:\ProgramData\PythonProject\paper_rag\eval\datasets\golden.jsonl`
- documents：`D:\ProgramData\PythonProject\paper_rag\eval\datasets\golden.documents.json`
- source_dir：`D:\ProgramData\PythonProject\paper_rag\eval\papers`
- index_dir：`D:\ProgramData\PythonProject\paper_rag\.paper_rag\api_index`
- tenant_id：`eval`
- top_k：`3`
- reader：`pdf_reader`
- chunker：`token_window_chunker`, chunk_size=`800`, chunk_overlap=`120`
- embedder：`openai_embedder`, source=`siliconflow`, model=`Qwen/Qwen3-Embedding-4B`
- retriever：`vector_retriever`
- generator：`openai_generator`, source=`siliconflow`, model=`deepseek-ai/DeepSeek-V4-Pro`, min_score=`0.05`
- 索引状态：status=`ready`, documents=`2`, chunks=`117`, indexed_chunks=`0`
- 原始 JSON report：`eval/experiments/baseline_v2_expectation_report.json`

## 汇总指标

| 指标 | v2 数值 | v2 计数 | 旧基线参考 |
| --- | ---: | --- | ---: |
| case_count | 13 | - | 13 |
| error_count | 0 | - | 0 |
| retrieval_hit_rate | 58.33% | 7/12 | 54.55% |
| answer_success_rate | 33.33% | 4/12 | 36.36% |
| citation_hit_rate | 66.67% | 8/12 | 36.36% |
| refusal_success_rate | 0.00% | 0/1 | 50.00% |
| answer_terms_hit_rate | 30.77% | 4/13 | 38.46% |

说明：旧基线的分母仍使用旧 `answerable` 二分类，v2 分母使用 `expectation` 语义，因此旧基线只作为历史参考，不作为严格同口径对比。

## 5 和 9 的重点观察

| case_id | 旧结果 | v2 结果 | 结论 |
| --- | --- | --- | --- |
| golden_005 | expectation=`None`, answer_state=`pass`, insufficient=`True` | expectation=`insufficient_detail`, answer_state=`fail`, insufficient=`False` | 有改善：模型不再标准拒答，能引用证据说明论文没有具体说明插帧算法；但 `answer_terms` 仍未命中，因为答案写的是“没有具体说明”，当前 OR 词条没有覆盖这个自然表达。 |
| golden_009 | expectation=`None`, answer_state=`fail`, insufficient=`True` | expectation=`corrective_answer`, answer_state=`fail`, insufficient=`False` | 未根本改善：检索和 citation 已命中，但答案仍以标准拒答开头，没有清晰纠正问题前提；后续应优化纠错题 prompt 或重写该题的期望答案词。 |

### golden_005 v2 答案

论文没有具体说明使用了哪种视频插帧算法。在数据收集与统一阶段，论文仅提到“将 ScanNet 的单独帧转换为 24 FPS 的连续视频”，但未披露所采用的具体插帧技术 [think in space.pdf, p.13]。

失败原因：

- 缺少答案词 未提及/没有说明/不足以回答/无相关信息/论文未涉及

### golden_009 v2 答案

不足以回答：当前检索到的证据不足以支持可靠答案。证据中仅提及了处理方式，即“将 ScanNet 的独立帧转换为 24 FPS 的连续视频，同时将 ScanNet++ 和 ARKitScenes 视频下采样至 30 FPS”[think in space.pdf, p.13]，但并未说明作者为何选择 30 FPS 这一具体帧率，也未解释将 ScanNet++ 单帧画面合成为视频的原因。

失败原因：

- 缺少答案词 降采样/subsampling

## 失败样本

- retrieval 失败：golden_001, golden_006, golden_008, golden_010, golden_cross_001
- answer 失败：golden_001, golden_005, golden_006, golden_007, golden_008, golden_009, golden_010, golden_012, golden_cross_001

## 逐样本结果

| case_id | expectation | answerable | retrieval_state | answer_state | insufficient_evidence | retrieved | used | citations |
| --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| golden_001 | direct_answer | True | miss | fail | False | 3 | 3 | 3 |
| golden_002 | direct_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_003 | direct_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_004 | direct_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_005 | insufficient_detail | True | hit | fail | False | 3 | 3 | 3 |
| golden_006 | direct_answer | True | miss | fail | False | 3 | 3 | 3 |
| golden_007 | direct_answer | True | hit | fail | False | 3 | 3 | 3 |
| golden_008 | direct_answer | True | miss | fail | True | 3 | 0 | 0 |
| golden_009 | corrective_answer | True | hit | fail | False | 3 | 3 | 3 |
| golden_010 | direct_answer | True | miss | fail | False | 3 | 3 | 3 |
| golden_011 | corrective_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_012 | out_of_scope_refusal | False | diagnostic | fail | True | 3 | 0 | 0 |
| golden_cross_001 | direct_answer | True | miss | fail | True | 3 | 0 | 0 |
