# 03 评测基础：为后续 RAG 优化建立可重复评估基线

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除/取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，只勾选对应任务，不批量勾选。
- 标注为“用户审核”的任务需要用户确认后再勾选。

## 阶段目标

建立一个轻量、确定性、可扩展的 RAG 评测基础，用于评估当前系统在本地 PDF 知识库上的检索、回答、引用和拒答能力。

当前阶段先不强依赖 RAGAs，优先实现项目自有的 golden dataset 和确定性指标。后续如需 LLM-as-judge、自动生成评测问题或合成测试集，再通过 adapter 接入 RAGAs 或其他评测框架。

核心原则：

```text
先有可信评测集
再做检索、chunk、rerank、RCS 等优化
每次优化后用同一套评测集判断是否真的变好
```

## 1. 评测数据格式设计

- [x] 设计 eval case 数据结构
- [x] 支持 `id`
- [x] 支持 `question`
- [x] 支持 `answerable`
- [x] 支持 `evidence`
- [x] 支持 `evidence[].doc_key`
- [x] 支持 `evidence[].page_start`
- [x] 支持 `evidence[].page_end`
- [x] 支持 `evidence[].terms`
- [x] 支持 `answer_terms`
- [x] 支持 `notes`
- [x] 使用 JSONL 作为第一版评测集格式
- [x] 为不可回答问题定义清晰字段约定
- [x] 为多证据问题预留扩展空间

## 2. 第一版人工 golden dataset

- [x] Agent 创建 `eval/datasets/golden.jsonl` 模板
- [x] 用户基于 `eval/papers/` 中固定评测语料人工创建 eval cases
- [x] 用户完成 8-15 个候选问题
- [x] 用户覆盖可回答问题
- [x] 用户覆盖不可回答问题
- [x] 用户覆盖事实型问题
- [x] 用户覆盖方法/流程型问题
- [x] 用户覆盖 citation/page 可验证问题
- [x] 用户审核可回答问题是否真的能从 PDF 回答
- [x] 用户审核不可回答问题是否合理
- [x] 用户确认 `evidence[].terms`
- [x] 用户确认 `answer_terms`
- [x] 用户确认 `evidence[].doc_key` 与 page range
- [x] 用户完成 golden dataset 更新
- [x] 用户确认第一版 golden dataset 可以作为后续优化基线

## 3. Evaluation dataset parser

- [x] 增加 `src/paper_rag/evaluation/` 模块
- [x] 定义 `EvalCase` 数据模型
- [x] 定义 `EvalDataset` 或等价集合模型
- [x] 实现 JSONL parser
- [x] 校验重复 case id
- [x] 校验 answerable 与 golden 字段的一致性
- [x] 对格式错误给出清晰错误信息
- [x] 增加 parser 单元测试

## 4. Evaluation runner

- [ ] 增加 `paper-rag eval` CLI 命令
- [ ] 支持指定 dataset path
- [ ] 支持指定 source directory
- [ ] 支持指定 index directory
- [ ] 支持 `--tenant-id`
- [ ] 支持 `--local`
- [ ] 支持 `--top-k`
- [ ] 支持 `--chunk-size`
- [ ] 支持 `--chunk-overlap`
- [ ] 自动构建或复用本地 eval index
- [ ] 对每个 eval case 执行 retrieval
- [ ] 对每个 eval case 执行 answer generation
- [ ] MVP 阶段优先支持 local/offline 评测

## 5. Retrieval 指标

- [ ] 计算 retrieval hit@k
- [ ] 判断 top-k 是否命中 `evidence[].doc_key`
- [ ] 判断 top-k 是否命中 `evidence[]` page range
- [ ] 判断 evidence 是否包含 `evidence[].terms`
- [ ] 区分 answerable 与 unanswerable case 的 retrieval 期望
- [ ] 输出 missed retrieval cases
- [ ] 增加 retrieval metric 单元测试

## 6. Answer / Citation / Refusal 指标

- [ ] 判断 answerable 问题是否成功回答
- [ ] 判断 unanswerable 问题是否正确拒答
- [ ] 判断答案是否包含 citation
- [ ] 判断 citation 是否命中 `evidence[].doc_key`
- [ ] 判断 citation 是否命中 `evidence[]` page range
- [ ] 判断答案是否包含 `answer_terms`
- [ ] 判断 unanswerable 问题是否没有 citation
- [ ] 输出 failed answer cases
- [ ] 增加 answer/citation/refusal metric 单元测试

## 7. 报告输出

- [ ] 控制台输出 summary
- [ ] 输出 case-level 明细
- [ ] 支持保存 JSON report
- [ ] 报告包含 retrieval 指标
- [ ] 报告包含 answer 指标
- [ ] 报告包含 citation 指标
- [ ] 报告包含 refusal 指标
- [ ] 报告包含失败样本 ID
- [ ] 报告包含失败原因

## 8. 文档与验收

- [ ] 新增 `eval/README.md`
- [ ] 说明如何人工审核 golden dataset
- [ ] 说明如何运行 `paper-rag eval`
- [ ] README 增加评测入口说明
- [ ] 手动跑通 sample eval dataset
- [ ] 记录一组可复现评测命令
- [ ] 运行 `pytest`
- [ ] 运行 `ruff check src tests scripts`

## 9. 当前阶段暂不实现

- [ ] ~~强依赖 RAGAs~~
- [ ] ~~LLM-as-judge 自动评分~~
- [ ] ~~自动生成评测问题并直接入库~~
- [ ] ~~大规模 benchmark~~
- [ ] ~~多模型横向对比平台~~
- [ ] ~~可视化评测 dashboard~~
- [ ] ~~生产日志自动采样成评测集~~
