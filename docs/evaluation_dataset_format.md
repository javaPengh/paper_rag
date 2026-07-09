# 评测数据集格式

本文定义 `paper_rag` 当前人工 golden dataset 的 JSONL 格式。它用于稳定评估 RAG 系统的检索、回答、引用和拒答表现，并支持单论文、多论文、多证据组以及“问题前提错误但语料可纠正”的评测样本。

## 文件格式

评测数据集使用 JSONL：

- 每行一个 eval case。
- reader 会忽略空行。
- reader 会忽略以 `#` 开头的人工注释行。
- 文件编码必须是 UTF-8。
- 默认数据集路径为 `eval/datasets/golden.jsonl`。
- 文档短键映射表路径为 `eval/datasets/golden.documents.json`。

示例：

```json
{"id":"golden_001","question":"论文中提出的 VSI-Bench 基准测试集包含了多少个问答对？","answerable":true,"expectation":"direct_answer","evidence":[{"doc_key":"think_in_space","page_start":3,"page_end":3,"terms":["VSI-Bench","5,000 question-answer pairs"]}],"answer_terms":["问答对","5,000"],"reference_answer":"","notes":"[A1 可回答][B1 事实型][C1 词面接近] 示例。"}
```

## Eval Case 字段

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `id` | string | 是 | 单个数据集内稳定唯一的 case ID，用于报告输出和回归对比。 |
| `question` | string | 是 | 提交给 RAG 系统的自然语言问题。问题可以是中文、英文或中英混杂。 |
| `answerable` | boolean | 是 | 兼容字段，表示该样本是否要求生成带 citation 的答案；它必须与 `expectation` 保持一致。 |
| `expectation` | string | 否 | 评测期望类型。旧数据缺失该字段时，会根据 `answerable` 自动推导。 |
| `evidence` | object array | 是 | 检索和 citation 应命中的证据组。它是多证据字段，天然支持跨页、跨论文和多个独立证据范围。 |
| `answer_terms` | string array | 是 | 期望出现在最终答案或拒答文本中的关键词或短语。多个顶层词条是 AND 关系。 |
| `reference_answer` | string | 否 | 人工撰写的参考答案，供人工复核或后续 answer quality 指标使用。 |
| `notes` | string | 是 | 人工审核备注、题型、假设或注意事项，不参与自动评分。 |

`answerable` 不再单独决定题目业务语义。当前评测应优先查看 `expectation`：

- `expectation` 属于 `direct_answer`、`corrective_answer`、`insufficient_detail` 时，`answerable` 必须为 `true`，系统应生成带 citation 的答案。
- `expectation` 为 `out_of_scope_refusal` 时，`answerable` 必须为 `false`，系统应标准拒答且不应给 citation。

## Expectation 取值

| 取值 | `answerable` | 期望行为 | 典型用途 |
| --- | --- | --- | --- |
| `direct_answer` | `true` | 直接依据证据回答，并给出 citation。 | 普通事实型、方法型、结果型、跨论文比较题。 |
| `corrective_answer` | `true` | 问题前提与证据相矛盾时，不拒答；应引用证据指出前提错误并给出纠正后的结论。 | 陷阱题、错误前提题。 |
| `insufficient_detail` | `true` | 证据与问题相关，但论文没有提供所问细节时，不编造；应说明未提供该细节，并引用相关证据。 | “论文是否说明了具体算法/参数/步骤”的细节缺失题。 |
| `out_of_scope_refusal` | `false` | 固定语料没有足够相关证据时，输出标准拒答，不给 citation。 | 完全超出语料范围、需要看图但系统没有图像理解能力等题。 |

旧数据集如果没有 `expectation`：

- `answerable: true` 会被解析为 `direct_answer`。
- `answerable: false` 会被解析为 `out_of_scope_refusal`。

这只是兼容旧数据的行为。新标注应显式填写 `expectation`，避免把“证据缺失”和“证据能反驳问题前提”混为同一种拒答。

## Evidence Group

`evidence` 数组中的每个对象表示一组期望证据：

| 字段 | 类型 | 必填 | 含义 |
| --- | --- | --- | --- |
| `doc_key` | string | 是 | 证据所在文档短键，必须存在于 `golden.documents.json`。 |
| `page_start` | integer | 是 | 证据页码范围起点，使用从 1 开始的闭区间。 |
| `page_end` | integer | 是 | 证据页码范围终点，使用从 1 开始的闭区间，必须大于或等于 `page_start`。 |
| `terms` | string array | 是 | 期望出现在检索证据文本中的原文锚点词或短语。 |

`evidence` 是多论文证据字段，不是单个“证据词”字段：

- 单文档、单页码范围问题只需要一个 evidence group。
- 跨页问题可以用一个覆盖多页的 evidence group，也可以按独立证据拆成多个 group。
- 跨论文问题应在 `evidence` 中写多组证据，每组证据填写自己的 `doc_key`、页码范围和 `terms`。
- 当前指标默认要求需要回答的样本命中全部 evidence group。

跨文档示例：

```json
{"id":"golden_cross_001","question":"论文 A 和论文 B 对 rerank 的处理有什么不同？","answerable":true,"expectation":"direct_answer","evidence":[{"doc_key":"paper_a","page_start":2,"page_end":3,"terms":["rerank","cross-encoder"]},{"doc_key":"paper_b","page_start":5,"page_end":5,"terms":["LLM rerank"]}],"answer_terms":["paper_a","paper_b","rerank"],"reference_answer":"","notes":"[A1 可回答][B6 跨论文对比][C1 词面接近] 示例。"}
```

## Evidence Terms 与 Answer Terms

`evidence[].terms` 用于判断检索文本是否真正覆盖人工标注的原文锚点：

- 建议填写论文原文中稳定出现的英文术语、数字、数据集名或方法名。
- 不要填写过长段落，避免格式、换行或 PDF 解析差异导致误判。
- 对英文论文，专业名词建议保持原文写法，例如 `VSI-Bench`、`SI'Bench`。
- term 匹配会做大小写不敏感和连续空白归一化，但不会做中英翻译、同义词扩展或语义匹配。

`answer_terms` 用于判断最终答案是否覆盖关键结论：

- 多个顶层词条之间是 AND 关系，答案需要覆盖全部词条。
- 单个词条内可以用 `/` 表示 OR 备选，例如 `下降/没有提升`。
- 对 `out_of_scope_refusal`，`answer_terms` 应包含标准拒答文本中的关键标记，例如 `不足以回答`。
- 对 `corrective_answer`，`answer_terms` 应同时覆盖纠错方向和关键证据结论。
- 对 `insufficient_detail`，`answer_terms` 应覆盖“未提供该细节”的判断，而不是要求模型编造缺失细节。

## 各类问题的标注约定

当 `expectation: "direct_answer"` 时：

- `evidence` 必须至少包含一个 evidence group。
- `answer_terms` 应覆盖最终答案中的核心事实或结论。
- 正确答案应给出 citation，citation 应命中人工 evidence。

当 `expectation: "corrective_answer"` 时：

- `evidence` 必须指向能反驳问题错误前提的原文。
- 正确答案不应拒答，而应说明问题前提不成立。
- `answer_terms` 应包含纠错所需关键词，例如“没有提升”“不是 30fps”等。

当 `expectation: "insufficient_detail"` 时：

- `evidence` 必须指向与问题相关、但只能证明论文没有给出所问细节的上下文。
- 正确答案不应输出标准拒答，也不应编造细节。
- 正确答案应引用证据说明论文只提供了哪些信息、哪些细节未说明。

当 `expectation: "out_of_scope_refusal"` 时：

- 如果问题完全无关或语料中没有可定位上下文，`evidence` 可以为空数组 `[]`。
- 正确结果应输出标准拒答，并且不应包含 citation。
- `answer_terms` 应填写拒答文本中的关键锚点，例如 `不足以回答`。

## 文档短键映射表

为了避免在每条 eval case 中反复填写很长的 PDF 文件名，数据集使用文档短键映射表：

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
- `source_path` 必填，表示从项目根目录出发到原始评测 PDF 的相对路径，或可直接读取的绝对路径。
- `notes` 可选，用于记录论文简称、版本或人工备注。
- 每个 `doc_key` 都必须能在映射表中找到。
- 评测 runner 应从 `source_path` 所在目录构建或复用评测索引，不依赖 Web 上传后的运行时文件名。

## 指标含义

当前确定性指标按以下方式使用数据集字段：

- 文档匹配：runner 先把 `evidence[].doc_key` 解析成 `source_path`，再按 `source_path` 或 basename 判断 retrieval / citation 是否命中。
- 页码匹配：按每个 evidence group 的闭区间 overlap 判断。
- 证据 term 匹配：按每个 evidence group 的 `terms` 判断检索文本是否覆盖关键锚点。
- 答案 term 匹配：按顶层 `answer_terms` 判断最终答案或拒答文本是否覆盖关键锚点。
- 检索命中率：只把 `direct_answer`、`corrective_answer`、`insufficient_detail` 纳入 hit@k 分母。
- 回答成功率：只把 `direct_answer`、`corrective_answer`、`insufficient_detail` 纳入 answer/citation/answer_terms 综合判断。
- 拒答成功率：只把 `out_of_scope_refusal` 纳入 refusal 指标。

## JSON Schema

机器可读 schema 位于：

```text
eval/schemas/eval_case.schema.json
```

后续 dataset parser 应使用同一套规则校验每个 JSONL 对象，并额外做跨行校验，例如重复 `id` 检查。
