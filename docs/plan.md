下面是把 PaperQA2 抽象成“从 0 复现学习项目”的产品与技术蓝图。参考了 PaperQA2 官方 README 和 FutureHouse 对其定位的说明：它是面向科学文献的高准确率 RAG 系统，支持带引用回答、文档索引、证据检索、LLM 重排、上下文摘要和 agentic 查询流程。来源：[PaperQA2 GitHub](https://github.com/Future-House/paper-qa)、[FutureHouse benchmark 文章](https://www.futurehouse.org/research-announcements/paperqa2-achieves-sota-performance-on-rag-qa-arena-science-benchmark)。

**1. 项目解决的问题**
核心问题：研究者面对大量论文、PDF、笔记和技术文档时，很难快速、可靠地回答复杂问题。

具体痛点包括：

- 文献太多，人工阅读和筛选成本高。
- 普通聊天模型容易幻觉，无法给出可追溯引用。
- 普通向量检索只返回相似片段，不一定能判断证据是否真的支持答案。
- 科研问题通常需要跨多篇文献综合、比较、归纳、找矛盾。
- 用户希望问自然语言问题，而不是手动管理检索关键词。

所以这个学习项目可以定位为：

> 一个面向论文和本地知识库的“可引用 RAG 问答系统”，帮助用户从本地论文集合中检索证据、生成带出处的回答，并尽量降低幻觉。

**2. 目标用户**
优先目标用户：

- 学生：读论文、写综述、做课程项目。
- 科研人员：快速理解某个方向、找证据、比较方法。
- 工程师：阅读技术论文、标准文档、源码文档。
- 投资/咨询/产品研究人员：从报告和论文中抽取可靠结论。
- RAG 学习者：想系统学习 PDF 解析、向量检索、引用生成、重排、agent 工作流。

MVP 阶段建议只服务一种核心用户：

> 有一批 PDF 论文，希望用自然语言提问，并得到带页码/文档来源的答案。

**3. 核心用户流程**
推荐把流程设计成 5 步：

1. 用户导入论文  
   上传 PDF，或指定本地论文目录。

2. 系统解析和索引  
   提取文本、页码、标题、作者等元数据；切分 chunk；生成 embedding；写入向量库和文档库。

3. 用户提问  
   例如：“这几篇论文如何解决 long-context retrieval 的问题？”

4. 系统检索证据  
   根据问题检索相关 chunk；可选进行关键词检索 + 向量检索混合召回；再做重排。

5. 系统生成答案  
   LLM 根据证据回答，并附上引用，例如：`[Paper A, p.3]`、`[Paper B, p.8]`。

进阶版流程可以加入 agent：

- agent 先改写查询。
- 多轮检索不同关键词。
- 对证据做摘要和打分。
- 判断证据是否足够。
- 不足时继续检索。
- 最后生成答案。

但学习项目第一版不要一上来做完整 agent，容易范围失控。

**4. MVP 功能范围**
建议 MVP 做到“能跑通 PaperQA2 的核心精神”，不追求完整复刻。

必做功能：

- PDF 上传/目录导入。
- PDF 文本解析，保留页码。
- 文档元数据管理：文件名、标题、页数、导入时间。
- 文本切分：按页或 token chunk。
- embedding 生成。
- 向量检索。
- 问答接口。
- 回答中包含引用来源。
- 简单 Web UI 或 CLI。
- 本地索引缓存，避免每次重新解析。

MVP 查询流程：

```text
用户问题
 -> embedding 查询
 -> top_k chunks
 -> 拼接上下文
 -> LLM 生成答案
 -> 返回答案 + 引用 chunk
```

MVP 暂时不做：

- 自动联网找论文。
- Semantic Scholar / Crossref / Unpaywall 元数据增强。
- 临床试验查询。
- 多模态图表理解。
- agent 多步规划。
- 复杂 benchmark。
- Office 文档、源码、HTML 等多格式支持。

**5. 后续可扩展功能**
可以按学习阶段扩展。

第一阶段：检索质量增强

- BM25 + 向量混合检索。
- Cross-encoder 或 LLM rerank。
- query rewrite / query expansion。
- 多 chunk 合并去重。
- 按论文、章节、页码过滤。
- 引用置信度评分。

第二阶段：PaperQA2 风格的 RCS

PaperQA2 的一个关键思想是 re-ranking and contextual summarization，也就是先找候选 chunk，再让 LLM 判断相关性并生成上下文摘要。你可以扩展成：

```text
检索 top 30 chunks
 -> LLM 对每个 chunk 做“是否相关 + 证据摘要”
 -> 选 top 5 summaries
 -> 基于 summaries 生成最终答案
```

第三阶段：agentic RAG

- agent 自动决定是否继续搜索。
- 支持 narrow search / broad search。
- 支持“证据不足，请继续找”。
- 支持多轮工具调用：搜索、读取、总结、回答。
- 支持 reset / complete 之类的流程控制。

第四阶段：科研工作流

- 论文总结。
- 多论文对比表。
- 方法、数据集、指标抽取。
- 相关工作草稿生成。
- 矛盾检测：找不同论文之间结论冲突。
- 文献综述大纲。
- BibTeX / DOI / arXiv 元数据补全。

第五阶段：系统工程增强

- 多用户。
- 异步任务队列。
- 大规模索引。
- 增量更新。
- 成本统计。
- rate limit。
- 本地模型支持。
- Docker 部署。
- API 服务化。

**6. 推荐的技术架构**
如果你是从 0 学习，我建议用“简单但可扩展”的架构。

后端：

- Python 3.11+
- FastAPI：提供上传、索引、问答 API。
- Pydantic：定义文档、chunk、answer、citation 数据结构。
- PyMuPDF 或 pypdf：PDF 解析。
- tiktoken：token 计数和切分。
- OpenAI / LiteLLM：LLM 和 embedding 接口。
- Chroma / Qdrant / LanceDB：向量库。
- SQLite / PostgreSQL：文档元数据、任务状态、问答历史。

前端：

- 第一版可以先用 CLI 或 Streamlit。
- 如果做 Web App：React + Vite + Tailwind。
- 页面只需要：
  - 文档上传页
  - 文档列表页
  - 问答页
  - 答案引用展开面板

推荐模块拆分：

```text
app/
  api/              FastAPI routes
  core/             config, logging, errors
  documents/        PDF parsing, metadata
  indexing/         chunking, embeddings, vector store
  retrieval/        search, rerank
  qa/               prompt, answer generation, citations
  storage/          SQLite/Postgres repositories
  schemas/          Pydantic models
  ui/               optional frontend
```

核心数据流：

```text
PDF
 -> Parser
 -> Pages
 -> Chunks
 -> Embeddings
 -> Vector Store

Question
 -> Retriever
 -> Evidence Chunks
 -> Optional Reranker/Summarizer
 -> Answer Generator
 -> Answer + Citations
```

建议路线：

1. 先做 CLI MVP：本地目录导入 + 问答 + 引用。
2. 再做 FastAPI 服务。
3. 再做 Web UI。
4. 最后加 RCS 和 agentic workflow。
