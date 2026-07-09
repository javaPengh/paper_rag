# 基线评估指标记录

## 指标含义

- `case_count`：本次评估覆盖的样本总数。
- `error_count`：评估运行中发生检索或答案生成异常的样本数，非模型答错。
- `retrieval_hit_rate`：可回答样本中，Top-k 检索结果是否命中全部人工标注 evidence 的比例。该指标主要衡量检索和切分是否把证据找回来。
- `answer_success_rate`：可回答样本中，最终答案同时满足非拒答、答案词、citation 命中等规则的比例。该指标衡量答案生成和引用综合效果。
- `citation_hit_rate`：可回答样本中，答案 citation 是否覆盖人工标注 evidence 文档和页码的比例。该指标衡量引用是否指向正确证据。
- `refusal_success_rate`：不可回答样本中，系统是否正确拒答且不返回 citation 的比例。该指标衡量拒答边界。
- `answer_terms_hit_rate`：所有样本中，答案文本是否覆盖 `answer_terms` 的比例。可回答题对应关键答案词，不可回答题对应拒答或预期词。
- `failed_case_ids.retrieval`：检索指标未通过的可回答样本 ID。
- `failed_case_ids.answer`：答案、引用或拒答指标未通过的样本 ID。
- `retrieval_state`：单样本检索状态，`hit` 表示命中 evidence，`miss` 表示未命中，`diagnostic` 表示不可回答样本仅作诊断。
- `answer_state`：单样本答案状态，`pass` 表示通过当前 answer/citation/refusal 规则，`fail` 表示未通过。
- `insufficient_evidence`：答案生成器是否认为证据不足并返回标准拒答。
- `used_chunk_ids`：答案生成阶段实际进入上下文并被用作证据的 chunk ID。

## 本次基线说明

- 本基线用于记录移除“问题与 chunk 必须有词项交集”硬过滤后的当前评估表现。
- 后续方案评估应优先和本文件对比；如果改动涉及 PDF 解析、chunk 切分、embedding 或索引构建，应重建索引后再记录新基线或实验结果。
- 本次使用外部 chat/embedding API，模型输出可能存在轻微非确定性；对比时应重点看整体趋势和失败 case 迁移。

## 运行配置

- 记录时间：2026-07-09T19:34:04
- commit:`82d8d25`
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
- 原始 JSON report：`eval/experiments/baseline_82d8d25_report.json`

## 汇总指标

| 指标 | 数值 | 计数 |
| --- | ---: | --- |
| case_count | 13 | - |
| error_count | 0 | - |
| retrieval_hit_rate | 54.55% | 6/11 |
| answer_success_rate | 36.36% | 4/11 |
| citation_hit_rate | 36.36% | 4/11 |
| refusal_success_rate | 50.00% | 1/2 |
| answer_terms_hit_rate | 38.46% | 5/13 |

## 失败样本

- retrieval 失败：golden_001, golden_006, golden_008, golden_010, golden_cross_001
- answer 失败：golden_001, golden_006, golden_008, golden_009, golden_010, golden_011, golden_012, golden_cross_001

## 逐样本结果

| case_id | answerable | retrieval_state | answer_state | insufficient_evidence | retrieved | used | citations |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| golden_001 | True | miss | fail | True | 3 | 0 | 0 |
| golden_002 | True | hit | pass | False | 3 | 3 | 3 |
| golden_003 | True | hit | pass | False | 3 | 3 | 3 |
| golden_004 | True | hit | pass | False | 3 | 3 | 3 |
| golden_005 | False | diagnostic | pass | True | 3 | 0 | 0 |
| golden_006 | True | miss | fail | True | 3 | 0 | 0 |
| golden_007 | True | hit | pass | False | 3 | 3 | 3 |
| golden_008 | True | miss | fail | True | 3 | 0 | 0 |
| golden_009 | True | hit | fail | True | 3 | 0 | 0 |
| golden_010 | True | miss | fail | False | 3 | 3 | 3 |
| golden_011 | True | hit | fail | True | 3 | 0 | 0 |
| golden_012 | False | diagnostic | fail | True | 3 | 0 | 0 |
| golden_cross_001 | True | miss | fail | True | 3 | 0 | 0 |

## 逐样本失败原因

### golden_001

- retrieval：think_in_space pp.3-3: 未命中页码范围
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 问答对, 室内, ScanNet, ScanNet++, ARKitScenes；think_in_space pp.3-3: citation 未命中文档

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
- answer：无

### golden_006

- retrieval：think_in_space pp.15-16: 缺少证据词 JSON format, dictionary
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 10x10, 网格, 字典, JSON；think_in_space pp.15-16: citation 未命中文档

### golden_007

- retrieval：无
- answer：无

### golden_008

- retrieval：think_in_space pp.6-6: 缺少证据词 Error Breakdown by Task
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 图7/Figure 7；think_in_space pp.6-6: citation 未命中文档

### golden_009

- retrieval：无
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 ScanNet, 24 FPS, 降采样/subsampling；think_in_space pp.13-13: citation 未命中文档

### golden_010

- retrieval：think_in_space pp.3-4: 未命中页码范围
- answer：缺少答案词 数据收集与统一, 质量审查；think_in_space pp.3-4: citation 未命中页码范围

### golden_011

- retrieval：无
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 下降/没有提升/有害/decrease；think_in_space pp.7-7: citation 未命中文档

### golden_012

- retrieval：无
- answer：缺少拒答词 object count, relative distance, appearance order

### golden_cross_001

- retrieval：SIBE-LM pp.6-7: 未命中页码范围
- answer：可回答问题被拒答或答案为空；缺少 citation；缺少答案词 configurational tasks, 物体计数, 属性, 状态, 颜色, 形状；think_in_space pp.3-4: citation 未命中文档；SIBE-LM pp.6-7: citation 未命中文档
