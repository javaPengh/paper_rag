# CLI MVP 手动验收

以下命令均在项目根目录执行，并使用已创建的 conda 环境 `paper_rag`。

```powershell
conda activate paper_rag
pip install -e ".[dev]"
Get-ChildItem eval/papers
```

建立本地索引：

```powershell
paper-rag index eval/papers --index-dir .paper_rag/manual_index --tenant-id default --local --chunk-size 800 --chunk-overlap 120
```

查看已索引文档：

```powershell
paper-rag list-docs --index-dir .paper_rag/manual_index --tenant-id default
```

查看 chunk：

```powershell
paper-rag show-chunks "think in space.pdf" --index-dir .paper_rag/manual_index --tenant-id default --limit 3
```

提出相关问题，答案应包含引用：

```powershell
paper-rag ask "论文中提出的 VSI-Bench 基准测试集包含了多少个问答对？" --index-dir .paper_rag/manual_index --tenant-id default --local --top-k 3
```

提出无关问题，答案应提示证据不足：

```powershell
paper-rag ask "What is the capital of France?" --index-dir .paper_rag/manual_index --tenant-id default --local --top-k 3
```

重复运行 `index` 时，同一路径同内容应显示 `Documents reused by source` 增加；把相同内容复制到另一个 PDF 路径后再次运行，应显示 `Documents reused by content` 增加且不重新生成 embedding。

## Web Inspector 验收

启动本地检验台：

```powershell
paper-rag serve --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

在页面中填入：

```text
Index dir: .paper_rag/manual_index
Tenant: default
```

验收点：

- Index 面板显示 `ready`、文档数和 chunk 数。
- Documents 面板显示真实 PDF，例如 `think in space.pdf` 或 `SIBE-LM.pdf`。
- 选择文档后，Chunks 面板显示 chunk 文本和版本 ID。
- Ask 面板勾选 `Local` 后提问与已索引论文相关的问题，答案应包含 citation，Evidence 区域应显示命中的 chunk。

## Web Inspector 端到端验收：从空索引上传开始

准备一个新的空索引目录，例如：

```text
.paper_rag/browser_acceptance/index
```

启动本地检验台：

```powershell
paper-rag serve --host 127.0.0.1 --port 8000
```

打开：

```text
http://127.0.0.1:8000
```

在页面中填入：

```text
Index dir: .paper_rag/browser_acceptance/index
Tenant: default
```

验收步骤：

1. 点击 `Refresh`，Index 面板应显示空索引或 missing 状态。
2. 在 Upload 面板选择 `eval/papers/think in space.pdf` 或其他真实论文 PDF。
3. 保持 `Local` 勾选，设置 `Chunk size = 800`、`Overlap = 120`。
4. 点击 `Upload & index`。
5. 上传完成后应看到 indexing summary，包含 `indexed=1` 和非零 chunks。
6. Documents 面板应出现上传后的 PDF。
7. 选择该文档，Chunks 面板应显示 chunk 文本和页码。
8. 在 Ask 面板提问 `论文中提出的 VSI-Bench 基准测试集包含了多少个问答对？`。
9. 答案应包含 citation，Evidence 区域应显示命中的 chunk。
10. citation 应能追溯到对应 chunk 和页码，例如 `p.1`。
11. 再提问 `What is the capital of France?`，应返回证据不足，且不输出 citation。

当前上传约束：

- 仅支持单个 PDF 上传。
- 非 PDF、空文件、超过大小限制的文件应返回清晰错误。
- 默认上传大小限制为 50MB，可通过 `PAPER_RAG_UPLOAD_MAX_BYTES` 调整。
- 上传后同步索引，暂不支持后台异步索引任务。
- 暂不支持多文件批量上传。
