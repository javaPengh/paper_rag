# 02 Web Inspector MVP：从前端完整触发本地 RAG 流程

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除/取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，只勾选对应任务，不批量勾选。

## 阶段目标

搭建一个工程化的 Web Inspector，用浏览器完整触发并检验当前本地 RAG MVP 流程：

```text
上传 PDF
 -> 受控保存到本地 source storage
 -> 调用现有解析、切分、embedding、索引流程
 -> 刷新索引状态、文档列表和 chunk
 -> 从前端提问
 -> 展示 answer、evidence、citation
 -> 能追溯 citation 到原始 chunk/page
```

这个阶段的 Web Inspector 是开发、调试和验收入口，不是最终正式产品 UI。前端不能直接依赖 CLI 输出格式，必须通过 FastAPI 暴露的结构化 API 调用后端能力。

## 1. FastAPI 基础边界

- [x] 增加 FastAPI 和本地开发服务器依赖
- [x] 在 `src/paper_rag/api/` 下创建 FastAPI application factory
- [x] 增加 `GET /health`
- [x] 增加 `GET /api/index/status`
- [x] 增加 `GET /api/documents`
- [x] 增加 `GET /api/documents/{document_id}/chunks`
- [x] 增加 `POST /api/ask`
- [x] API request/response 使用明确模型，不复用 CLI 文本输出格式
- [x] CLI 增加 `serve` 命令，作为本地开发和验收启动入口

## 2. 只读 Inspector 页面

- [x] 增加由 FastAPI 托管的静态 Inspector 页面
- [x] 支持选择 `tenant_id`
- [x] 支持选择或输入 `index_dir`
- [x] 展示索引状态、文档数、chunk 数和 embedding model
- [x] 展示已索引文档列表
- [x] 展示文档版本、`content_hash`、`source_uri` 等调试信息
- [x] 选择文档后展示 chunk 列表
- [x] 支持从前端提问
- [x] 展示答案、citation 和 evidence chunk

## 3. 文档上传与本地 source storage

- [x] 增加 multipart upload 所需依赖
- [x] 设计本地上传文件存储根目录，默认使用 `.paper_rag/uploads/`
- [x] 上传文件按 `tenant_id` 做目录隔离
- [x] 只允许上传单个 PDF 文件
- [x] 校验文件扩展名，拒绝非 PDF 文件
- [x] 校验基础 content type 或文件头，降低误上传风险
- [x] 对原始文件名做安全化处理，避免路径穿越和非法字符
- [x] 保存上传文件到受控 source storage
- [x] 使用受控保存路径作为 `source_uri`
- [x] 为后续删除、重建和版本追溯保留清晰的存储约定

## 4. Web 触发索引流程

- [x] 增加 `POST /api/documents/upload`
- [x] 上传成功后调用现有 `build_index_from_directory`
- [x] 支持 `tenant_id`
- [x] 支持 `index_dir`
- [x] 支持 `local` 离线 embedding 模式
- [x] 支持配置 `chunk_size`
- [x] 支持配置 `chunk_overlap`
- [x] 复用现有文档身份、版本和内容去重策略
- [x] 返回结构化 indexing summary
- [x] summary 区分 `indexed`、`reused_source`、`reused_content`、`reindexed`
- [x] 返回 skipped files、warnings 和 errors
- [x] MVP 阶段使用同步索引，暂不引入异步任务队列

## 5. 上传 UI 与前端闭环

- [x] 页面增加 PDF 文件选择控件
- [x] 页面增加上传并索引按钮
- [x] 页面增加 `chunk_size` 和 `chunk_overlap` 控件
- [x] 页面上传流程支持 `local` embedding toggle
- [x] 上传/索引过程中显示 loading 状态
- [x] 上传完成后展示 indexing summary
- [x] 上传完成后自动刷新 index status
- [x] 上传完成后自动刷新 documents
- [x] 上传完成后允许继续选择文档查看 chunks
- [x] 上传完成后允许直接从 Ask 面板提问
- [x] 上传错误、解析 warning 和索引 error 能在页面上看到

## 6. 前端端到端验收路径

- [x] 从一个空 index directory 开始
- [x] 在浏览器上传一个 PDF
- [x] 上传后文档出现在 documents 列表
- [x] 选择文档后能看到 chunk 切分结果
- [x] 从浏览器提出相关问题
- [x] 答案包含 citation
- [x] evidence 区域显示命中的 chunk
- [x] citation 能追溯到对应 chunk 和页码
- [x] 从浏览器提出无关问题时返回证据不足

## 7. 错误处理与 MVP 约束

- [x] 非 PDF 上传返回清晰 API 错误
- [x] 空文件上传返回清晰 API 错误
- [x] 解析失败不会导致服务崩溃
- [x] 索引失败返回结构化错误
- [x] 前端阻止空问题提交
- [x] 前端阻止未选择文件时上传
- [x] 文档上传大小限制先作为配置或 README 约束说明
- [x] 明确当前阶段暂不支持多文件批量上传
- [x] 明确当前阶段暂不支持后台异步索引任务

## 8. 测试与验证

- [x] 增加 API 测试：health
- [x] 增加 API 测试：文档列表
- [x] 增加 API 测试：chunk 列表
- [x] 增加 API 测试：本地 ask
- [x] 增加 API 测试：PDF 上传并触发索引
- [x] 增加 API 测试：拒绝非 PDF 上传
- [x] 增加 API 测试：上传后能查询文档和 chunk
- [x] 增加 API 测试：上传后能从 API ask 并返回 citation
- [x] 更新手动验收文档
- [x] 更新 README 的 Web Inspector 使用说明
- [x] 运行 `pytest`
- [x] 运行 `ruff check src tests scripts`

## 9. 当前阶段暂不实现

- [ ] ~~正式产品级 Web App~~
- [ ] ~~React/Vite 前端工程化构建~~
- [ ] ~~多文件批量上传~~
- [ ] ~~后台异步索引任务队列~~
- [ ] ~~上传进度条的真实后端进度事件~~
- [ ] ~~用户认证与权限系统~~
- [ ] ~~文档删除、恢复和版本回滚 UI~~
- [ ] ~~远程对象存储，如 S3、MinIO、SharePoint~~
