# 基线 v3 Prompt 评估指标记录

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

- 本文件是答案生成提示词调整后的 v3 基线，后续提示词、生成策略和引用策略优化默认应优先与本文件对比。
- 本次改动点体现在 report 的 `run.rag_config.generator.parameters.prompt_version = "answer_v4_corrective_mapping"`。
- 本次评估复用 v2 基线的 API index、模型、Top-k、chunk 和 `min_score` 配置，没有重建索引。
- v3 与 `baseline_v2_expectation_*` 同属 expectation 语义口径，可以做同口径对比；`baseline_82d8d25_*` 仍只作历史参考。
- 本次使用外部 chat/embedding API，模型输出存在非确定性；后续对比应重点看整体趋势和失败 case 迁移。

## 运行配置

- 记录时间：2026-07-10T17:10:55
- commit：`2112fa2`
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
- generator：`openai_generator`, source=`siliconflow`, model=`deepseek-ai/DeepSeek-V4-Pro`, min_score=`0.05`, prompt_version=`answer_v4_corrective_mapping`
- 索引状态：status=`ready`, documents=`2`, chunks=`117`, indexed_chunks=`0`
- Judge：enabled=`false`
- 原始 JSON report：`eval/experiments/baseline_v3_prompt_report.json`

## 汇总指标

| 指标 | v3 数值 | v3 计数 | v2 数值 | v2 计数 |
| --- | ---: | --- | ---: | --- |
| case_count | 13 | - | 13 | - |
| error_count | 0 | - | 0 | - |
| retrieval_hit_rate | 58.33% | 7/12 | 58.33% | 7/12 |
| answer_success_rate | 41.67% | 5/12 | 33.33% | 4/12 |
| citation_hit_rate | 66.67% | 8/12 | 66.67% | 8/12 |
| refusal_success_rate | 0.00% | 0/1 | 0.00% | 0/1 |
| answer_terms_hit_rate | 38.46% | 5/13 | 30.77% | 4/13 |

说明：v3 与 v2 使用同一 expectation 语义口径。v3 的主要收益是 `golden_009` 从 answer fail 变为 pass，使 `answer_success_rate` 从 33.33% 提升到 41.67%，`answer_terms_hit_rate` 从 30.77% 提升到 38.46%。检索和引用指标未变化。

## 重点观察

| case_id | v2 结果 | v3 结果 | 结论 |
| --- | --- | --- | --- |
| golden_005 | retrieval=`hit`, answer=`fail`, insufficient=`False` | retrieval=`hit`, answer=`fail`, insufficient=`False` | 语义上仍能说明论文未披露具体插帧算法，但 `answer_terms` 仍未覆盖“未披露”这类自然表达，指标仍 fail。 |
| golden_009 | retrieval=`hit`, answer=`fail`, insufficient=`False` | retrieval=`hit`, answer=`pass`, insufficient=`False` | 明显改善：v3 正确纠正 ScanNet 与 ScanNet++ 的处理方式，命中 `降采样/subsampling`，answer 从 fail 变为 pass。 |
| golden_011 | retrieval=`hit`, answer=`pass`, insufficient=`False` | retrieval=`hit`, answer=`pass`, insufficient=`False` | 保持通过：纠错题能先否定错误前提，再补充原文中的 CoT、Self-Consistency 和 ToT 设置。 |
| golden_012 | retrieval=`diagnostic`, answer=`fail`, insufficient=`True` | retrieval=`diagnostic`, answer=`fail`, insufficient=`False` | 仍未达标：该样本是 `out_of_scope_refusal`，v3 选择引用证据说明论文未细分 Top-3，而不是标准拒答，因此 refusal 仍为 0/1。 |
| golden_cross_001 | retrieval=`miss`, answer=`fail`, insufficient=`True` | retrieval=`miss`, answer=`fail`, insufficient=`False` | 仍未达标：跨文档检索未命中 SIBE-LM 目标页码，答案也缺少部分期望词，后续应优先优化跨文档检索或证据页码召回。 |

### golden_009 v3 答案

问题前提不成立：作者并未将ScanNet++的单帧画面合成为30fps的视频。根据证据，ScanNet++本身是视频数据，作者对其进行了下采样（subsampling）至30 FPS；而将单帧画面合成为连续视频的操作是针对ScanNet数据集，且帧率为24 FPS [think in space.pdf, p.13]。问题混淆了这两个数据集的处理方式：ScanNet是从单帧合成24fps视频，ScanNet++是从视频下采样到30fps。

失败原因：无

## 失败样本

- retrieval 失败：golden_001, golden_006, golden_008, golden_010, golden_cross_001
- answer 失败：golden_001, golden_005, golden_006, golden_007, golden_008, golden_010, golden_012, golden_cross_001

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
| golden_009 | corrective_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_010 | direct_answer | True | miss | fail | False | 3 | 3 | 3 |
| golden_011 | corrective_answer | True | hit | pass | False | 3 | 3 | 3 |
| golden_012 | out_of_scope_refusal | False | diagnostic | fail | False | 3 | 3 | 3 |
| golden_cross_001 | direct_answer | True | miss | fail | False | 3 | 3 | 3 |

## 逐样本失败原因

### golden_001

- retrieval：think_in_space pp.3-3: 未命中页码范围
- answer：缺少答案词 室内；think_in_space pp.3-3: citation 未命中页码范围

### golden_002

- retrieval：无
- answer：无

### golden_003

- retrieval：无
- answer：无

### golden_004

- retrieval：无
- answer：无

### golden_005

- retrieval：无
- answer：缺少答案词 未提及/没有说明/不足以回答/无相关信息/论文未涉及

### golden_006

- retrieval：think_in_space pp.15-16: 缺少证据词 JSON format, dictionary
- answer：缺少答案词 字典, JSON

### golden_007

- retrieval：无
- answer：缺少答案词 局部世界模型

### golden_008

- retrieval：think_in_space pp.6-6: 缺少证据词 Error Breakdown by Task
- answer：需要证据作答的问题被拒答或答案为空；缺少 citation；缺少答案词 图7/Figure 7；think_in_space pp.6-6: citation 未命中文档

### golden_009

- retrieval：无
- answer：无

### golden_010

- retrieval：think_in_space pp.3-4: 未命中页码范围
- answer：缺少答案词 数据收集与统一, 质量审查；think_in_space pp.3-4: citation 未命中页码范围

### golden_011

- retrieval：无
- answer：无

### golden_012

- retrieval：无
- answer：不可回答问题未拒答；不可回答问题不应返回 citation；缺少拒答词 object count, relative distance, appearance order

### golden_cross_001

- retrieval：SIBE-LM pp.6-7: 未命中页码范围
- answer：缺少答案词 configurational tasks, 属性, 状态, 颜色, 形状；SIBE-LM pp.6-7: citation 未命中页码范围

## 结论

- v3 可以作为新的提示词基线留档：在检索和引用不变的情况下，答案成功率提升 1 个 case。
- 当前最大稳定收益来自纠错题 `golden_009`，说明新 prompt 对“问题前提错误，需要映射数据集处理方式”的场景更有效。
- 后续若继续优化 prompt，应重点处理 `golden_005` 的细节缺失表达和 `golden_012` 的语料外拒答边界，避免把标准拒答样本转成带 citation 的边界说明。
- 检索失败样本未减少，`golden_001`、`golden_006`、`golden_008`、`golden_010`、`golden_cross_001` 仍需要从检索、切分或跨文档召回侧继续优化。