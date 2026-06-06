# 评测数据集格式

本文定义 `paper_rag` 第一版人工 golden dataset 格式。目标是让评测集容易阅读、
容易 diff，并且足够严格，后续可以直接支撑确定性的 parser 和 metric 实现。

## 文件格式

评测数据集使用 JSONL：

- 每行一个 eval case。
- reader 应忽略空行。
- reader 可忽略以 `#` 开头的人工注释行。
- 文件编码必须是 UTF-8。
- 第一版数据集建议放在 `eval/datasets/golden.jsonl`。
- 文档短键映射表建议放在 `eval/datasets/golden.documents.json`。

示例：

```json
{"id":"golden_001","question":"论文中提出的 VSI-Bench 基准测试集包含了多少个问答对？","answerable":true,"evidence":[{"doc_key":"think_in_space","page_start":3,"page_end":3,"terms":["VSI-Bench","5,000 question-answer pairs"]}],"answer_terms":["问答对","5,000"],"reference_answer":"","notes":"[A1 可回答][B1 事实型][C1 词面接近] 示例。"}
```

## 必填字段

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `id` | string | 是 | 单个数据集内稳定唯一的 case id。 |
| `question` | string | 是 | 面向用户的自然语言问题。 |
| `answerable` | boolean | 是 | 当前本地 PDF 知识库是否有足够证据回答该问题。 |
| `evidence` | object array | 是 | 检索和 citation 应命中的证据组；完全无关的不可回答题可以为空数组。 |
| `answer_terms` | string array | 是 | 期望出现在最终答案或拒答文本中的关键词或短语。 |
| `notes` | string | 是 | 人工审核备注、题型、假设或注意事项。 |
| `reference_answer` | string | 否 | 人工撰写的参考答案，供后续 answer quality、judge 或人工复核使用。 |

## Evidence Group

`evidence` 数组中的每个对象表示一个独立证据组：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `doc_key` | string | 是 | 评测集文档短键，对应 `golden.documents.json` 中的 key。 |
| `page_start` | integer | 是 | 该证据组的起始页，闭区间。 |
| `page_end` | integer | 是 | 该证据组的结束页，闭区间。 |
| `terms` | string array | 是 | 期望出现在该证据组检索文本中的关键词或短语。 |

`evidence` 数组中的每个 group 都默认必须命中。第一版不区分必需证据和辅助证据，
避免增加人工标注负担。

## 可回答问题约定

当 `answerable: true` 时：

- `evidence` 必须至少包含一个 evidence group。
- 每个 group 的 `doc_key` 必须存在于文档短键映射表。
- 每个 group 的 `page_end` 必须大于或等于 `page_start`。
- 每个 group 的 `terms` 应至少包含一个确实出现在支持证据中的 term。
- `answer_terms` 必须至少包含一个正确答案应包含的 term。
- `reference_answer` 建议填写，但 MVP 阶段不强制。事实型、方法型、结果型、
  综合型问题尤其值得填写。

单文档、单页码范围问题只需要一个 evidence group。跨页、跨论文或多个独立证据范围
的问题，继续追加多个 evidence group 即可。

跨文档示例：

```json
{"id":"golden_cross_001","question":"论文 A 和论文 B 对 rerank 的处理有什么不同？","answerable":true,"evidence":[{"doc_key":"paper_a","page_start":2,"page_end":3,"terms":["rerank","cross-encoder"]},{"doc_key":"paper_b","page_start":5,"page_end":5,"terms":["LLM rerank"]}],"answer_terms":["paper_a","paper_b","rerank"],"reference_answer":"","notes":"[A1 可回答][B6 跨论文对比][C1 词面接近] 示例。"}
```

## 不可回答问题约定

当 `answerable: false` 时：

- 如果问题完全无关或语料中没有可定位上下文，`evidence` 填空数组 `[]`。
- 如果问题与某篇论文相关，但原文没有给出所问细节，`evidence` 可以填写最能证明
  “未提及或信息不足”的相关证据组。
- `answer_terms` 应包含一个或多个期望拒答标记，例如 `["不足以回答"]`、
  `["证据不足"]`、`["未提及"]` 或 `["没有统计"]`。
- `reference_answer` 可留空；如需填写，建议使用一句明确拒答文本。
- 正确结果应被标记为证据不足，并且不应包含无依据的 citation。

## 文档短键映射表

为了避免在每条 eval case 中反复填写很长的 PDF 文件名，第一版数据集采用 dataset
级文档映射表：

```text
eval/datasets/golden.documents.json
```

示例：

```json
{
  "think_in_space": {
    "source_path": "eval/papers/think in space.pdf",
    "notes": "真实评测论文，已固化为评测语料。"
  }
}
```

约定：

- JSON 对象的 key 就是 evidence group 中填写的 `doc_key`。
- `source_path` 必填，表示从项目根目录出发到原始评测 PDF 的相对路径。
- `notes` 可选，用于记录论文简称、版本或人工备注。
- 每个 `doc_key` 都必须能在映射表中找到。
- 评测 runner 应从 `source_path` 所在目录构建或复用评测索引，不依赖 Web 上传后的
  运行时文件名。

## 指标含义

第一版指标实现建议：

- 文档匹配：runner 先把 `evidence[].doc_key` 解析成 `source_path`，再按
  `source_path` 或其 basename 判断 retrieval / citation 是否命中。
- 页码匹配：按每个 evidence group 的闭区间 overlap 判断。
- 证据 term 匹配：按每个 evidence group 的 `terms` 判断检索文本是否覆盖关键锚点。
- 答案 term 匹配：按顶层 `answer_terms` 判断最终答案或拒答文本是否覆盖关键锚点。
- term 匹配默认做大小写不敏感匹配，并先归一化连续空白字符。

## JSON Schema

机器可读 schema 位于：

```text
eval/schemas/eval_case.schema.json
```

后续 dataset parser 应使用同一套规则校验每个 JSONL 对象，并额外做跨行校验，例如
重复 `id` 检查。
