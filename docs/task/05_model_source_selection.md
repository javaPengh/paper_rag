# Task5：模型来源选择与评测配置追踪

## Summary

本任务在 Task4 的 RAG 组件边界之上，补齐“前端可选择不同供应商及其模型、后端按选择创建组件、评测报告记录来源和模型”的轻量能力。目标不是引入完整 provider/plugin 平台，而是让当前只涉及的 embedding 和对话模型可以清晰切换、并存和留档。

## Key Changes

- 新增轻量模型来源配置：
  - `EMBEDDING_SOURCE` / `EMBEDDING_MODEL` 表示当前选中的 embedding 来源和模型。
  - `CHAT_SOURCE` / `CHAT_MODEL` 表示当前选中的对话来源和模型。
  - `SILICONFLOW_*_MODELS`、`OPENAI_*_MODELS` 表示各来源下前端可选模型列表。
  - 某来源某类别既没有模型列表也没有当前选中模型时，该来源不会出现在对应下拉框中。
  - 外部来源、模型、密钥和必要连接信息缺失时不填入占位默认值，调用路径直接抛出明确错误。
  - 旧 `PAPER_RAG_EMBEDDING_MODEL` 和 `PAPER_RAG_LLM_MODEL` 继续兼容。

- 后端 registry 继续保留五类组件边界：
  - 组件仍是 `openai_embedder` 和 `openai_generator`。
  - 工厂新增 `source` 参数，根据 `local`、`openai`、`siliconflow` 注入不同 API key 和 base URL。
  - `/api/components` 新增 `model_catalog`，供前端按 embedding/chat 分别渲染来源和模型下拉框。

- Web Inspector 改为模型来源驱动：
  - 上传区选择 embedding 来源和模型。
  - 提问区分别选择查询 embedding 来源/模型和对话来源/模型。
  - 页面首次加载使用后端显式配置的当前来源和模型，之后保留用户当前选择。

- CLI 和评测支持来源参数：
  - `paper-rag index` 支持 `--embedding-source`。
  - `paper-rag ask` 支持 `--embedding-source`、`--chat-source` 和 `--chat-model`。
  - `paper-rag eval` 支持 `--embedding-source`、`--chat-source` 和 `--chat-model`。
  - `--llm-model` 作为旧别名继续可用。

- 评测和索引追踪来源：
  - `run.rag_config.embedder.source` 记录 embedding 来源。
  - `run.rag_config.generator.source` 记录对话来源。
  - `IndexStatus.embedding_source` 记录当前向量索引使用的 embedding 来源。

## Checklist

- [x] 新增轻量模型来源配置和环境变量解析
- [x] 保留旧模型环境变量兼容
- [x] registry 支持按来源创建 embedding/generator
- [x] `/api/components` 返回 `model_catalog`
- [x] Web Inspector 改为来源和模型下拉框
- [x] CLI 新增来源参数并保留旧模型参数兼容
- [x] Evaluation report 记录组件来源
- [x] README 和 `eval/README.md` 更新模型来源说明
- [x] `docs/task_history.md` 追加任务历史

## Test Plan

- 配置测试：确认新环境变量能读取模型来源、当前模型和模型列表；空模型列表不会回退默认值；旧变量仍兼容。
- Registry 测试：确认 embedding/chat catalog 只暴露当前类别有模型的外部来源，且只返回密钥配置状态。
- API 测试：确认 `/api/components` 返回 `model_catalog`，且不泄露 API key。
- 回归测试：确认本地上传、索引、提问和 eval 行为不变。
- 报告测试：确认 JSON report 的 `run.rag_config` 包含 `source`。
