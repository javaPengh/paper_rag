# Prompt v3 单题验证记录

## 目的

本次只评估 `golden_009`，用于验证 `answer_v3_corrective_boundary` 是否改善纠错题回答。该实验不是全量基线，只用于快速判断 prompt 变更是否值得进入下一轮全量评估。

## 运行配置

- case_id：`golden_009`
- prompt_version：`answer_v3_corrective_boundary`
- index_dir：`.paper_rag/api_index`
- tenant_id：`eval`
- top_k：`3`
- chunk_size：`800`
- chunk_overlap：`120`
- min_score：`0.05`
- embedding：`siliconflow / Qwen/Qwen3-Embedding-4B`
- chat：`siliconflow / deepseek-ai/DeepSeek-V4-Pro`
- JSON report：`eval/experiments/prompt_v3_golden_009_report.json`

## 结果

| case_id | expectation | retrieval_state | answer_state | insufficient_evidence | 结论 |
| --- | --- | --- | --- | --- | --- |
| golden_009 | corrective_answer | hit | pass | False | 已改善：答案以“问题前提不成立”开头，纠正 ScanNet++ 与 ScanNet 的帧率处理前提，并命中 citation 与答案词。 |

## v3 答案

问题前提不成立：根据论文，ScanNet++ 原本就是视频，作者是对其进行**下采样（subsampling）** 到 30 FPS，而非将单帧画面合成为视频。将单帧画面合成为连续视频的操作是针对 ScanNet 数据集，且帧率为 24 FPS。论文未明确说明进行这些帧率处理的具体原因，但提到所有视频均被标准化为 640×480 分辨率，帧率调整可能属于统一预处理的一部分 [think in space.pdf, p.13]。
