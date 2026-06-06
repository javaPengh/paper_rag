# 01 CLI MVP 补充任务 01：文档身份、版本与去重策略

## 任务状态规则

- 未完成：`- [ ]`
- 已完成：`- [x]`
- 已删除/取消：`- [ ] ~~任务内容~~`
- 每完成一个任务，就只勾选对应任务，不批量勾选。

## 目标

把当前依赖本地 `source_path` 判断文档身份的 MVP 实现，调整为更接近企业生产环境的文档身份模型：路径只是来源位置，不能作为文档唯一身份；系统内部使用稳定 `document_id`，内容变化通过 `content_hash` / version 判断，同租户内通过 `tenant_id + content_hash` 做内容去重。

## 1. 数据模型调整

- [x] 在 `Document` 中加入 `tenant_id`
- [x] 在 `Document` 中加入稳定的系统内部 `id`，不再由本地路径派生
- [x] 在 `Document` 中加入可选 `source_id`，用于未来对接外部系统稳定文件 ID
- [x] 在 `Document` 中加入 `source_uri`，用于保存本地路径、S3 URI、SharePoint URL 等来源位置
- [x] 在 `Document` 中保留 `file_name`、`title`、`page_count` 等展示字段
- [x] 新增 `DocumentVersion` 数据结构
- [x] `DocumentVersion` 包含 `id`、`document_id`、`content_hash`、`source_uri`、`page_count`、`created_at`
- [x] 在 `Chunk` 中加入 `document_version_id`
- [x] 保留 `Chunk.document_id`，用于跨版本归属查询

## 2. 身份与去重规则

- [x] 默认单用户本地模式使用 `tenant_id = "default"`
- [x] 本地文件导入时，`source_uri` 使用 resolved file path 字符串
- [x] 内容指纹使用 SHA-256 `content_hash`
- [x] 同一 `tenant_id + content_hash` 已存在时，识别为相同内容
- [x] 同一 `source_id` 或同一 `source_uri` 内容未变时，复用已有版本和索引
- [x] 同一 `source_id` 或同一 `source_uri` 内容变化时，创建新的 `DocumentVersion`
- [x] 不再用 `source_path` 作为 `Document` 唯一身份
- [x] 不再用 `source_path + content_hash` 生成 `document_id`

## 3. SQLite 元数据存储调整

- [x] 新增或改造 `documents` 表，保存稳定文档身份
- [x] 新增 `document_versions` 表
- [x] `documents` 支持按 `tenant_id + source_id` 查询
- [x] `documents` 支持按 `tenant_id + source_uri` 查询
- [x] `document_versions` 支持按 `tenant_id + content_hash` 查询
- [x] `chunks` 表保存 `document_version_id`
- [x] `IndexStatus.sources` 改为记录当前版本来源信息
- [x] 保留向后兼容迁移或明确重建索引策略

## 4. Chroma 向量索引调整

- [x] Chroma metadata 加入 `tenant_id`
- [x] Chroma metadata 加入 `document_version_id`
- [x] Chroma metadata 保留 `document_id`、页码、chunk 序号、文件名
- [x] 删除旧版本索引时按 `document_version_id` 删除向量
- [x] 检索时支持按 `tenant_id` 隔离数据
- [x] 检索结果仍通过 SQLite 回查完整 `Chunk` 和 `Document`

## 5. 导入与重建流程调整

- [x] 扫描 PDF 后解析规范化文本并计算 `content_hash`
- [x] 根据 `tenant_id + source_uri` 查找已有来源记录
- [x] 根据 `tenant_id + content_hash` 查找已有内容版本
- [x] 内容未变化时跳过切分、embedding
- [x] 内容变化时创建新版本并重建 chunk/vector
- [x] 相同内容不同路径导入时，不重复生成 embedding
- [x] 相同内容不同路径导入时，复用已有文档，策略已在代码中固定
- [x] CLI 输出区分 `indexed`、`reused_source`、`reused_content`、`reindexed`

## 6. CLI 与配置调整

- [x] `index` 命令支持 `--tenant-id`，默认 `default`
- [x] `ask` 命令支持 `--tenant-id`，默认 `default`
- [x] `list-docs` 命令展示 `tenant_id`、`document_id`、当前 `version_id`
- [x] `show-chunks` 命令展示 `document_version_id`
- [x] README 更新文档身份、版本与去重说明
- [x] 手动验收文档更新对应命令

## 7. 测试与验收

- [x] 测试同一路径同内容重复导入会复用索引
- [x] 测试同一路径内容变化会创建新版本并重建索引
- [x] 测试不同路径相同内容在同一 tenant 内不会重复 embedding
- [x] 测试不同 tenant 上传相同内容时数据隔离
- [x] 测试 Chroma 检索按 tenant 隔离
- [x] 测试 `list-docs` 能显示文档当前版本
- [x] 测试 `show-chunks` 能显示 chunk 所属版本
- [x] 跑通完整 CLI 本地验收流程
- [x] `pytest` 全部通过
- [x] `ruff check src tests scripts` 全部通过

## 8. 暂不实现

- [ ] ~~多用户认证系统~~
- [ ] ~~真实企业 connector 接入~~
- [ ] ~~跨租户内容级物理存储复用~~
- [ ] ~~复杂版本回滚 UI~~
- [ ] ~~权限 ACL / RBAC~~
