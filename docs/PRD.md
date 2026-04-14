# CiteWise 智能研究助手 — 产品需求文档 (PRD)

> **版本**: V3.2 (已校准代码)
> **更新日期**: 2026-04-14 (代码验证更新)
> **产品定位**: AI 驱动的多 Agent 学术研究助手
> **技术栈**: FastAPI + LangGraph + 智谱 GLM-4.7 + ChromaDB + Tailwind CSS SPA
> **项目路径**: `C:/Users/77230/CiteWise/`
> **访问地址**: `http://localhost:5328`

---

## 1. Executive Summary

### 1.1 Problem Statement

学术研究者在文献综述和论文写作过程中面临三大核心痛点：(1) 大量论文阅读效率低下，难以快速定位关键信息；(2) 跨论文知识整合缺乏系统化工具，依赖人工对比和手动摘录；(3) 论文写作中的资料引用、框架搭建和内容生成缺乏智能辅助，重复劳动严重。现有方案（如 ChatPDF、SciSpace）多为单轮问答，缺乏多 Agent 协同、透明推理和全流程写作支持。

### 1.2 Proposed Solution

CiteWise 是基于 **LangGraph Supervisor 多 Agent 编排架构** 的 AI 智能研究助手。通过声明式状态图调度 5 个专业 Agent（Supervisor / Researcher / Responder / Writer / Analyst），结合混合检索引擎（BM25 + 向量搜索 + RRF 融合）和三层记忆架构，为研究者提供从文献上传、知识检索、智能问答到论文写作的全链路支持。

**核心差异化**：
1. **LangGraph Supervisor 多 Agent 编排** — 声明式状态图，非简单链式调用
2. **实时 Agent Timeline 可视化** — 用户可追踪每一步推理过程
3. **三源标注系统** — `[KB]` 文献库 / `[WEB]` 联网 / `[AI]` 推理，来源透明可验证
4. **混合检索引擎** — BM25 + 向量 + RRF 融合 + 重排序
5. **内置评估体系** — AgentEval 面板，5 大核心指标 + 自动优化建议

### 1.3 Success Criteria

| KPI | 目标值 | 衡量方式 |
|-----|--------|----------|
| 检索召回率 (Recall@20) | >= 85% | 标注数据集回归评测 |
| 引用标注准确率 | >= 95% | 人工抽检 100 条引用 |
| 首 Token 延迟 (TTFT) | < 3s (P95) | SSE 流式输出首 token 时间戳 |
| 任务成功率 | >= 85% | AgentEval 自动统计 |
| 用户满意度 | >= 4.2/5.0 | 用户反馈评分均值 |

---

## 2. User Experience & Functionality

### 2.1 User Personas

| Persona | 描述 | 核心需求 | 使用频率 |
|---------|------|----------|----------|
| **研究生小李** | 研一学生，首次进行系统文献综述 | 快速理解论文要点、生成综述框架、标注引用来源 | 每日 2-3 次 |
| **博士生张教授** | 领域专家，需要跨论文对比分析 | 知识矩阵提取、多维度对比、数据可视化 | 每周 3-5 次 |
| **科研助理王姐** | 负责团队文献管理和报告撰写 | 批量论文处理、结构化提取、文档导出 | 每日 5-10 次 |

### 2.2 User Stories & Acceptance Criteria

#### US-01: 智能问答与知识检索
> As a 研究者, I want to 用自然语言提问并获取基于文献库的精准回答 with 来源标注, so that 我无需逐篇翻阅即可获取可信答案.

**Acceptance Criteria:**
- [ ] 输入问题后 3s 内开始 SSE 流式输出
- [ ] 回答中包含 `[作者, 年份]` 格式引用标注
- [ ] 每条引用标注来源类型：`[KB]` 文献库 / `[WEB]` 联网 / `[AI]` 推理
- [ ] Agent Timeline 右侧面板实时显示 Supervisor → Researcher → Responder 执行链路
- [ ] 支持多轮对话，10+ 轮上下文不丢失
- [ ] 混合检索自动执行，用户无需选择检索策略
- [ ] 联网搜索在文献库覆盖不足时自动触发

#### US-02: 文献上传与管理
> As a 研究者, I want to 批量上传 PDF/DOCX 论文并自动提取元数据和建立检索索引, so that 我能快速建立个人文献库.

**Acceptance Criteria:**
- [ ] 支持 PDF / DOC / DOCX / MD / TXT 五种格式
- [ ] 自动提取标题、作者、年份、摘要并展示
- [ ] 上传进度实时显示进度条
- [ ] 解析失败时返回明确错误信息并跳过，不阻塞批量流程
- [ ] 自动完成分层分块 (L0/L1/L2) + Embedding + ChromaDB 存储
- [ ] 论文列表支持按时间/标题排序和关键词搜索
- [ ] 单篇删除时同步清理 ChromaDB 向量数据

#### US-03: 论文写作辅助
> As a 研究者, I want to 基于已读文献自动生成论文各章节初稿 with 引用标注, so that 我能从框架而非空白页开始写作.

**Acceptance Criteria:**
- [ ] 支持生成预设章节：摘要、引言、文献综述、方法论、讨论、结论
- [ ] 生成内容基于 RAG 检索结果，每段标注引用来源
- [ ] 支持自然语言修改指令（如 "把第三段改得更学术化"）
- [ ] 支持子对话模式：点击某一段落进入独立编辑上下文（`/api/chat/sub`）
- [ ] 编辑内容实时自动保存到后端
- [ ] 最终文档可合并导出为 Markdown 格式

#### US-04: 跨论文对比分析
> As a 博士生, I want to 横向对比多篇论文的研究方法和实验结果, so that 我能快速发现研究空白和趋势.

**Acceptance Criteria:**
- [ ] 支持选择 2-10 篇论文进行矩阵提取
- [ ] 用户可自定义对比维度（方法、数据集、指标、结论等）
- [ ] 结果以学术风格表格展示
- [ ] 支持导出 CSV 格式

#### US-05: 数据可视化
> As a 研究者, I want to 以图表形式展示研究趋势和统计数据, so that 我能直观理解文献库的整体情况.

**Acceptance Criteria:**
- [ ] 支持自然语言描述生成图表（如 "展示近五年各方法的准确率趋势"）
- [ ] 图表基于 D3.js 渲染，支持交互（缩放、悬浮提示）
- [ ] AgentEval 面板内置趋势柱状图

#### US-06: 模型灵活切换
> As a 用户, I want to 在不同 LLM 供应商之间切换, so that 我能根据任务和成本选择最合适的模型.

**Acceptance Criteria:**
- [ ] 支持智谱 / DeepSeek / OpenAI / Moonshot / 千问 / 自定义 6+ 供应商
- [ ] API Key 保存前自动验证有效性并获取可用模型列表
- [ ] 切换模型后聊天立即可用新模型

### 2.3 Non-Goals

以下明确 **不在** 当前版本范围内：

- 多用户实时协作编辑（同步/异步）
- 论文全文翻译功能
- LaTeX 格式导出
- 移动端原生 App（仅桌面 Web）
- 付费订阅和计费系统
- Zotero / Mendeley 深度集成
- 本地模型部署支持

---

## 3. AI System Requirements

### 3.1 Multi-Agent Architecture

#### 3.1.1 编排模型

采用 **LangGraph Supervisor** 模式，声明式 `StateGraph` 定义 Agent 协作流程：

```
用户输入 → [Supervisor] → 意图分类（10 类） → 路由决策
  ├── explore / websearch → [Researcher] → [Responder]
  ├── generate / modify / framework → [Researcher] → [Writer]
  ├── analyze / chart / figures → [Researcher] → [Analyst]
  ├── summarize → [Researcher] → [Responder]
  └── export → [Writer]
```

**核心实现文件**：
- `src/core/graph_state.py` — `AgentState` TypedDict 定义
- `src/core/graph.py` — `StateGraph` 声明式图结构 + `MemorySaver`
- `src/core/agents/router.py` — Supervisor 意图分类 + 路由

#### 3.1.2 Agent 职责矩阵

| Agent | 职责 | 输入 | 输出 | 模型 | 文件 |
|-------|------|------|------|------|------|
| **Supervisor** | 意图分类(10种) + 路由 + 分级模型选择 | 用户消息 + 历史上下文 | 路由指令 + 模型选择 | glm-4-flash | `agents/router.py` |
| **Researcher** | RAG 混合检索 + 联网搜索 + 上下文组装 | 查询 + 检索参数 | 检索结果 + 来源标注 | glm-4-flash | `agents/researcher.py` |
| **Responder** | 生成带三源标注的回答 | 检索结果 + 用户问题 | 结构化回答 + `[KB]/[WEB]/[AI]` 标注 | glm-4.7 | `graph.py` (内置节点) |
| **Writer** | 学术内容生成/修改/导出 | 检索结果 + 写作指令 | 章节内容 + 引用 + 修改摘要 | glm-4.7 | `agents/writer.py` |
| **Analyst** | 数据分析 + 可视化 + 框架 + 图表索引 | 检索结果 + 分析指令 | 图表配置 + 分析报告 + 图表列表 | glm-4.7 | `agents/analyst.py` |

#### 3.1.3 意图分类体系

| Intent | 描述 | 路由目标 | 模型 | 典型输入 |
|--------|------|----------|------|----------|
| `explore` | 探索性知识问答 | Researcher → Responder | glm-4-flash | "Transformer 在 NLP 中有哪些应用？" |
| `summarize` | 论文/主题摘要 | Researcher → Responder | glm-4-flash | "总结这篇论文的核心贡献" |
| `generate` | 生成论文章节 | Researcher → Writer | glm-4.7 | "帮我写文献综述" |
| `modify` | 修改已有内容 | Researcher → Writer | glm-4.7 | "把这段改得更学术化" |
| `framework` | 生成论文框架 | Researcher → Writer | glm-4.7 | "生成论文大纲" |
| `export` | 导出文档 | Writer | glm-4-flash | "导出所有章节" |
| `chart` | 生成图表 | Researcher → Analyst | glm-4.7 | "画一个趋势图" |
| `analyze` | 深度分析 | Researcher → Analyst | glm-4-flash | "分析这些论文的研究趋势" |
| `websearch` | 联网搜索 | Researcher → Responder | glm-4-flash | "搜索最新的 RLHF 论文" |
| `figures` | 图表索引查询 | Researcher → Analyst | glm-4-flash | "列出所有图表" |

### 3.2 RAG Pipeline

#### 3.2.1 文档处理流水线

```
文件上传 → 格式检测 → 对应解析器
  ├── PDF → Docling(优先) / pdfplumber(fallback) → 元数据+文本+表格+图表
  ├── DOCX → python-docx → 段落提取
  ├── MD/TXT → 直接读取
  └── XLSX → openpyxl → 表格提取
         → 分层分块(L0/L1/L2)
         → Embedding(embedding-3, 2048 维)
         → ChromaDB 存储
```

**分块策略**（实现：`src/core/rag.py` + `src/core/file_parser.py`）：

| 层级 | 粒度 | 大小 | overlap | 用途 |
|------|------|------|---------|------|
| L0 | 文档级 | 全文摘要 | - | 全局概览 |
| L1 | 章节级 | 500-1500 字 | 10-20% | 上下文理解 |
| L2 | 段落级 | 200-500 字 | 10-20% | 精准检索 |

#### 3.2.2 混合检索引擎

**实现文件**：`src/core/retriever.py`

```
用户查询 → Query 改写
         → BM25 关键词检索 (Top-20, jieba中英混合分词)  ──┐
         → 向量语义检索 (Top-20, ChromaDB cosine)     ──┤→ RRF 融合(k=60)
         → [可选] DuckDuckGo 联网搜索                 ──┘
         → LLM 重排序 (候选≤10条时触发, 70%LLM+30%向量相似度)
         → 最终 Top-5 结果 + 引用格式化
```

| 参数 | 值 | 说明 |
|------|-----|------|
| BM25 Top-K | 20 | jieba 中英文混合分词 |
| Vector Top-K | 20 | ChromaDB 语义相似度 (cosine) |
| RRF k 参数 | 60 | 倒数排名融合权重 |
| LLM Rerank 权重 | 70% LLM + 30% Vector | 候选≤10条时触发 |
| Embedding 维度 | 2048 | embedding-3 模型 |
| 最终输出 | Top-5 | 带 `[作者, 年份]` 引用格式化 |

### 3.3 Prompt Engineering (5 层分层模板)

**实现文件**：`src/core/prompt.py`

| 层级 | 内容 | 动态性 | 示例 |
|------|------|--------|------|
| Layer 1-2 | 系统基础约束 | 固定 | "强制溯源、禁止幻觉、结构化输出" |
| Layer 3 | 用户画像 | 半静态 | 研究领域、关注方向、写作风格 |
| Layer 4 | 项目状态 | 动态 | 文献数量、已提取字段、当前框架 |
| Layer 5 | 任务 Prompt | 按意图切换 | 提取字段/生成章节/分析对比等 |

PromptEngine 类负责动态组装模板，根据意图选择对应的 Layer 5 模板，注入用户画像和项目状态。

### 3.4 Memory Architecture

三层记忆系统：

| 层级 | 存储 | 持久性 | 内容 | 实现类 |
|------|------|--------|------|--------|
| **GlobalProfile** | JSON 文件 (`data/user_profile.json`) | 永久 | 用户画像、研究偏好、字段模板、写作风格 | `memory.py` GlobalProfile |
| **ProjectMemory** | SQLite (`data/db/citewise.db`) | 永久 | 7 张表: projects/papers/extractions/sections/figures/users/sessions+messages | `memory.py` ProjectMemory |
| **WorkingMemory** | LangGraph AgentState (内存) | 会话级 | 19 字段状态，含当前项目/任务/焦点论文/对话历史(10轮滑动窗口) | `graph_state.py` AgentState |

**跨项目复用**：GlobalProfile 提供字段模板和写作偏好的跨项目复用，新项目创建时自动继承。

### 3.4 Evaluation Strategy

#### 3.4.1 AgentEval 评估面板

**实现文件**：`api/routes/eval.py` + `static/js/eval-panel.js`

| 维度 | 指标 | 目标 | 数据来源 |
|------|------|------|----------|
| 任务成功率 | 成功任务数 / 总任务数 | >= 85% | 自动统计 |
| 引用准确率 | 已验证引用数 / 总引用数 | >= 80% | 自动 + 人工 |
| 幻觉率 | 未验证陈述数 / 总陈述数 | <= 10% | CoVe 验证 |
| 响应时间 | 平均完成时间 | <= 10s | SSE 时间戳 |
| 调用成本 | Token 消耗统计 | 监控 | API 响应 |

#### 3.4.2 自动优化规则

| 条件 | 触发动作 |
|------|----------|
| 成功率 < 85% | 建议优化路由逻辑和错误处理 |
| 幻觉率 > 10% | 建议增强 RAG 检索质量，引入 CoVe 验证 |
| 响应时间 > 10s | 建议优化 LLM 调用链，减少 top_k |
| 引用准确率 < 80% | 建议改进检索器重排序策略 |

### 3.5 CoVe (Chain-of-Verification) 验证系统

**实现文件**：`src/core/cove.py`

四步验证流程：
1. **声明提取** — 从生成内容中提取可验证的事实性声明（claims）
2. **问题生成** — 为每个声明生成验证问题
3. **交叉验证** — 用 RAG 检索 + LLM 回答验证问题
4. **置信度评分** — 对比原始声明与验证结果，标记置信度

输出：
- 整体置信度分数 (0-1)
- 逐条声明验证结果：verified / contradicted / unverifiable
- 矛盾声明高亮标记

### 3.6 知识图谱与推荐系统

**实现文件**：`src/core/recommender.py` + `api/routes/knowledge_map.py` + `api/routes/recommendations.py`

| 功能 | 描述 | API |
|------|------|-----|
| 引用关系图 | 基于论文间引用关系构建知识图谱 | `/api/knowledge-map` |
| 相似度推荐 | 基于向量相似度的论文推荐 | `/api/recommendations` |
| D3.js 可视化 | 前端交互式图谱展示 | 前端内置 |

### 3.7 Model Configuration

| 用途 | 模型 | 原因 | 成本级别 |
|------|------|------|----------|
| 意图分类 (Supervisor) | glm-4-flash | 低延迟、高准确 | 低 |
| 检索 & 上下文组装 (Researcher) | glm-4-flash | 大量调用、成本控制 | 低 |
| 最终回答生成 (Responder) | glm-4.7 | 高质量、长文本 | 高 |
| 内容修改 & 导出 (Writer) | glm-4.7 | 理解复杂修改指令 | 高 |
| 分析 & 可视化 (Analyst) | glm-4.7 | 结构化输出质量 | 高 |
| Embedding | embedding-3 | 2048 维，中英双语 | 低 |

---

## 4. Technical Specifications

### 4.1 Architecture Overview

```
┌──────────────────────────────────────────────────────────────┐
│                    Frontend (Tailwind CSS SPA)                │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Chat View│ │ Paper Mgmt│ │ Section  │ │ Agent Timeline │  │
│  │ (SSE)    │ │          │ │ Editor   │ │ (可视化)       │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └──────┬─────────┘  │
└───────┼─────────────┼────────────┼──────────────┼────────────┘
        │ SSE/REST    │ REST       │ REST         │ SSE
        ▼             ▼            ▼              ▼
┌──────────────────────────────────────────────────────────────┐
│                 FastAPI Backend (Port 5328)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Chat API │ │ Paper API│ │ Project  │ │ Eval API       │  │
│  │ /api/chat│ │ /api/... │ │ API      │ │ /api/eval      │  │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────────────────┘  │
│       │             │            │                            │
│  ┌────┴─────────────┴────────────┴──────────────────────┐    │
│  │           LangGraph Supervisor StateGraph             │    │
│  │  [Supervisor] → [Researcher] → [Responder/Writer/    │    │
│  │                                 Analyst]              │    │
│  └────────┬────────────┬────────────────────────────────┘    │
│           │            │                                      │
│  ┌────────┴──┐  ┌──────┴──────┐  ┌────────────────────┐     │
│  │ ChromaDB  │  │   SQLite    │  │ 智谱 GLM API       │     │
│  │ (向量库)  │  │ (项目数据库)│  │ open.bigmodel.cn   │     │
│  └───────────┘  └─────────────┘  └────────────────────┘     │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 API Specification

#### 4.2.1 Chat API

| Endpoint | Method | 描述 | 流式 |
|----------|--------|------|------|
| `/api/chat` | POST | 主对话（SSE 流式） | Yes |
| `/api/chat/sub` | POST | 子对话（段落编辑） | Yes |
| `/api/sessions` | GET | 获取会话列表 | No |
| `/api/sessions/{id}` | DELETE | 删除会话 | No |
| `/api/sessions/{id}/messages` | GET | 获取会话消息历史 | No |

**Chat Request Schema:**
```json
{
  "message": "string (required, max 2000 chars)",
  "project_id": "string (required)",
  "session_id": "string (optional)",
  "intent": "string (optional, auto-detected)"
}
```

**SSE Event Types:**
```
event: agent_start    → {agent: "Researcher", timestamp: "..."}
event: token          → {content: "文本片段"}
event: agent_end      → {agent: "Responder", duration_ms: 1234}
event: sources        → {sources: [{type: "KB", title: "...", authors: "..."}]}
event: done           → 对话完成
event: error          → {message: "错误描述"}
```

#### 4.2.2 Project API

| Endpoint | Method | 描述 |
|----------|--------|------|
| `/api/projects` | POST | 创建项目 |
| `/api/projects` | GET | 获取项目列表 |
| `/api/projects/{id}` | GET / PUT / DELETE | 项目 CRUD |

#### 4.2.3 Paper API

| Endpoint | Method | 描述 |
|----------|--------|------|
| `/api/papers/upload` | POST | 上传论文（multipart/form-data） |
| `/api/papers` | GET | 获取论文列表 |
| `/api/papers/{id}` | GET / DELETE | 论文详情 / 删除 |
| `/api/papers/{id}/chunks` | GET | 查看论文分块详情 |

#### 4.2.4 Search & Analysis API

| Endpoint | Method | 描述 |
|----------|--------|------|
| `/api/search/hybrid` | POST | 混合检索（BM25 + Vector + RRF） |
| `/api/extraction/extract` | POST | 结构化提取 |
| `/api/extract/matrix` | POST | 跨论文矩阵提取 |

#### 4.2.5 Auth & Config API

| Endpoint | Method | 描述 |
|----------|--------|------|
| `/api/auth/register` | POST | 用户注册 |
| `/api/auth/login` | POST | 用户登录（JWT） |
| `/api/config/providers` | GET / POST | LLM 供应商管理 |
| `/api/config/api-keys` | POST / DELETE | API Key 管理 |

### 4.3 Data Models

#### 4.3.1 SQLite Schema

```sql
-- 项目表
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 会话表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 消息表
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    intent TEXT,
    sources TEXT,          -- JSON: [{type, title, authors, year, ...}]
    agent_events TEXT,     -- JSON: [{agent, status, duration_ms, ...}]
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 论文表
CREATE TABLE papers (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT,
    authors TEXT,
    year INTEGER,
    abstract TEXT,
    file_path TEXT NOT NULL,
    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    chunk_count INTEGER DEFAULT 0
);

-- 章节表
CREATE TABLE sections (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    session_id TEXT REFERENCES sessions(id),
    section_type TEXT,     -- abstract/intro/literature_review/method/discussion/conclusion
    title TEXT,
    content TEXT,
    order_index INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 评估表
CREATE TABLE eval_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    intent TEXT,
    success BOOLEAN,
    citation_count INTEGER DEFAULT 0,
    verified_citations INTEGER DEFAULT 0,
    hallucination_count INTEGER DEFAULT 0,
    response_time_ms INTEGER,
    token_count INTEGER,
    user_rating INTEGER CHECK(user_rating BETWEEN 1 AND 5),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 4.3.2 ChromaDB Collections

```
Collection: paper_chunks
├── id: chunk_uuid (string)
├── embedding: float[2048] (embedding-3)
├── document: chunk_text (string)
└── metadata:
    ├── paper_id: string
    ├── title: string
    ├── authors: string
    ├── year: int
    ├── section_level: "L0" | "L1" | "L2"
    ├── section_title: string
    ├── page_num: int
    └── chunk_index: int
```

### 4.4 Frontend Architecture

#### 4.4.1 Component Structure

```
```
static/
├── index.html              -- SPA 入口 (Tailwind CDN, 1105 行)
├── css/
│   └── tailwind.css        -- Tailwind CSS (空，使用 CDN)
├── js/
│   └── app.js              -- 主应用逻辑 (2410 行单体文件)
│                              包含：路由/状态管理/对话/SSE/论文管理/章节编辑/Timeline
├── vendor/
│   ├── animate.min.css     -- 动画库
│   ├── lucide.min.js       -- 图标库
│   └── tailwindcss.js      -- Tailwind 本地 fallback
└── data/                   -- 运行时数据
```
```

#### 4.4.2 Frontend Performance Targets

| 指标 | 目标 | 衡量方式 |
|------|------|----------|
| FCP | < 1.5s | Lighthouse |
| LCP | < 2.5s | Lighthouse |
| CLS | < 0.1 | Lighthouse |
| JS Bundle (gzip) | < 200KB | 构建产物 |
| SSE 首 token | < 500ms | 网络面板 |

### 4.5 Security & Privacy

#### 4.5.1 数据安全措施

| 措施 | 实现方式 |
|------|----------|
| API Key 管理 | `.env` 环境变量 / 前端 localStorage，不入库 |
| 文件上传限制 | 单文件 50MB 上限，白名单格式校验 |
| Rate Limiting | 30 请求/分钟/IP（内存级，FastAPI middleware） |
| 输入验证 | Pydantic schema 校验所有 API 入参 |
| XSS 防护 | 前端内容渲染转义 |
| SQL 注入 | ORM 参数化查询 |
| 安全头 | `X-Content-Type-Options` / `X-Frame-Options` / `Referrer-Policy` |
| 用户数据隔离 | JWT Token + user_id 过滤 |

#### 4.5.2 隐私合规

- 用户论文数据本地存储，不上传至第三方 LLM
- LLM 调用仅传输检索结果片段和用户输入，不传输论文全文
- 会话数据仅保留在本地 SQLite，用户可随时删除
- 不收集任何用户行为追踪数据

### 4.6 Integration Points

| 集成 | 协议 | 用途 | 配置 |
|------|------|------|------|
| 智谱 GLM API | HTTPS REST | LLM 推理 | `OPENAI_BASE_URL=open.bigmodel.cn` |
| 智谱 Embedding API | HTTPS REST | 文本向量化 | `EMBEDDING_MODEL=embedding-3` |
| ChromaDB | 本地进程 | 向量存储和 ANN 检索 | `data/db/chroma` |
| DuckDuckGo API | HTTPS | 联网搜索补充 | 自动触发 |
| SQLite | 本地文件 | 结构化数据持久化 | `data/db/citewise.db` |
| D3.js | CDN | 数据可视化 | 前端内联 |

---

## 5. Risks & Roadmap

### 5.1 Technical Risks

| 风险 | 概率 | 影响 | 缓解策略 |
|------|------|------|----------|
| 智谱 API 不可用/限流 | 中 | 高 | 降级到 glm-4-flash；本地缓存常见查询结果 |
| 大文件 PDF 解析超时 | 中 | 中 | 异步处理 + 进度通知；50MB 硬限制 |
| 向量库性能瓶颈 | 低 | 中 | 分片索引；定期优化；增量更新 |
| 长对话上下文溢出 | 中 | 中 | 自动摘要压缩；滑动窗口；会话拆分 |
| BM25 中文分词不准 | 低 | 低 | 自定义词典；jieba 优化加载 |
| LangGraph Breaking Changes | 中 | 中 | 锁定依赖版本；关注 Release Notes |

### 5.2 Phased Roadmap

#### V1.0 — MVP ✅ (已完成)

- 单 Agent 对话
- PDF 上传和解析
- 基础向量检索
- 简单问答

#### V2.0 — 多 Agent 架构 ✅ (已完成)

- LangGraph Supervisor 模式
- 4 个专业 Agent（Router/Researcher/Writer/Analyst）
- 章节生成和管理
- 前端 SPA 重构

#### V3.0 — 生产级系统 ✅ (已完成)

- Token 级 SSE 流式输出
- Agent 时间线可视化
- 三源标注系统 ([KB]/[WEB]/[AI])
- Skill 和工具箱
- AgentEval 评估面板
- 多供应商 API Key 管理
- 用户认证系统（JWT）

#### V3.1 — 稳定性增强 ✅ (已完成)

- SSE CRLF 兼容解析修复
- 模型选择器 UI 重构（向上展开）
- 自动创建默认项目
- 端口冲突修复（5328 替代 10000）
- Playwright E2E 测试套件

#### V3.2 — 当前版本 🔄

| 特性 | 优先级 | 状态 |
|------|--------|------|
| 异步 LLM 流式优化 | P0 | ✅ 已完成 (`async_graph.py`) |
| CoVe (Chain-of-Verification) 验证系统 | P1 | ✅ 已完成 (`src/core/cove.py`) |
| 高级 PDF 解析（Docling + 表格/图表提取） | P1 | ✅ 已完成 (`advanced_parser.py` + `file_parser.py`) |
| 多轮对话上下文管理优化 | P1 | ✅ 已完成 (10 轮滑动窗口) |
| 知识图谱可视化 (D3.js) | P1 | ✅ 已完成 (`api/routes/knowledge_map.py`) |
| 文献推荐系统 | P1 | ✅ 已完成 (`src/core/recommender.py`) |
| A/B 测试框架 | P2 | ✅ 已完成 (`src/eval/ab_test.py`) |
| 多格式文件解析 (DOCX/MD/TXT/XLSX) | P2 | ✅ 已完成 (`file_parser.py`) |
| 部署优化（Docker + Render） | P2 | 规划中 |
| 面试 Demo 脚本 | P1 | 规划中 |

#### V4.0 — 高级能力 📋 (规划中)

| 特性 | 优先级 | 描述 |
|------|--------|------|
| 多用户协作 | P0 | 注册/登录、权限管理、团队共享 |
| Zotero 集成 | P1 | 导入 Zotero 文献库、双向同步 |
| LaTeX 导出 | P1 | 支持导出 LaTeX 格式论文 |
| 实时协作编辑 | P2 | 多人同时编辑、评论和批注 |
| 移动端适配 | P2 | 响应式 PWA |
| 多 LLM 支持 | P2 | OpenAI / Claude / 本地模型自由切换 |
| 插件市场 | P3 | 社区 Skill 分享和安装 |

### 5.3 Dependencies

| 依赖 | 版本要求 | 风险级别 | 说明 |
|------|----------|----------|------|
| Python | >= 3.10 | 低 | 稳定 |
| FastAPI | >= 0.104 | 低 | 稳定 |
| LangGraph | >= 0.0.40 | **中** | 快速迭代，关注 Breaking Changes |
| ChromaDB | >= 0.4.0 | 低 | 稳定 |
| 智谱 GLM API | glm-4.7 / glm-4-flash | **中** | 第三方依赖，需监控可用性 |
| jieba | >= 0.42 | 低 | 中文分词 |
| D3.js | v7 | 低 | 前端可视化 |
| pdfplumber / PyPDF2 | latest | 低 | PDF 解析 |

---

## Appendix

### A. Key File Reference

| 文件 | 路径 | 职责 |
|------|------|------|
| 入口 | `run.py` | 服务启动 (port=5328) |
| API 主路由 | `api/main.py` | FastAPI app + 中间件 + 生命周期 |
| 聊天路由 | `api/routes/chat.py` | SSE 流式对话 + `astream_events` |
| Agent 图定义 | `src/core/graph.py` | LangGraph `StateGraph` + `MemorySaver` |
| 异步图定义 | `src/core/async_graph.py` | 异步图 + 直接 SSE 流式输出 |
| Agent 状态 | `src/core/graph_state.py` | `AgentState` TypedDict (19字段) |
| Supervisor | `src/core/agents/router.py` | 意图分类(10种) + 路由 + 分级模型选择 |
| Researcher | `src/core/agents/researcher.py` | RAG 检索 + 联网搜索 |
| Responder | `src/core/graph.py` (responder_node) | 生成带引用回答 (内嵌节点) |
| Writer | `src/core/agents/writer.py` | 内容生成 / 修改 / 导出 |
| Analyst | `src/core/agents/analyst.py` | 分析 / 可视化 / 框架 |
| 兼容层 | `src/core/agents/coordinator.py` | graph.invoke 兼容包装 |
| 检索器 | `src/core/retriever.py` | BM25 + Vector + RRF 融合 + LLM 重排序 |
| PDF 解析 | `src/core/rag.py` | PDF 分层分块 (L0/L1/L2) + 语义切块 |
| 文件解析 | `src/core/file_parser.py` | 统一解析器: PDF/DOCX/MD/TXT/XLSX |
| 高级解析 | `src/core/advanced_parser.py` | Docling PDF 解析 + fallback |
| Prompt 引擎 | `src/core/prompt.py` | 5 层分层 Prompt 模板 + PromptEngine |
| 记忆系统 | `src/core/memory.py` | 三层记忆: GlobalProfile/ProjectMemory/WorkingMemory |
| 来源标注 | `src/core/source_annotation.py` | [KB]/[WEB]/[AI] 程序化标注 |
| CoVe 验证 | `src/core/cove.py` | Chain-of-Verification 事实核查 |
| 推荐 | `src/core/recommender.py` | 论文相似度 + 引用推荐 |
| Embedding | `src/core/embedding.py` | embedding-3 + ChromaDB VectorStore |
| 评估系统 | `src/eval/metrics.py` | AgentEval 5 大指标 + SQLite |
| 评估面板 | `src/eval/dashboard.py` | 评估 API (/eval/metrics, /eval/trends) |
| A/B 测试 | `src/eval/ab_test.py` | A/B 测试框架 |
| 联网搜索 | `src/tools/web_search.py` | DuckDuckGo 搜索 + LLM 摘要 |
| 前端入口 | `static/index.html` | SPA 主页面 (1105行, Tailwind CDN) |
| 前端主逻辑 | `static/js/app.js` | 完整前端逻辑 (2410行单体) |
| 配置 | `config/settings.py` | 环境变量 + 路径 + 参数集中配置 |

### B. Environment Configuration

```env
# LLM Configuration
OPENAI_API_KEY=your_zhipu_api_key
OPENAI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
LLM_MODEL=glm-4.7
LLM_MODEL_LIGHT=glm-4-flash
EMBEDDING_MODEL=embedding-3

# Server
PORT=5328
HOST=0.0.0.0

# Data Paths
DATA_DIR=./data
PAPERS_DIR=./data/papers
DB_DIR=./data/db
```

### C. Startup Commands

```bash
# 启动服务
cd C:/Users/77230/CiteWise && python run.py

# 访问地址
http://localhost:5328
```

### D. Glossary

| 术语 | 定义 |
|------|------|
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| RRF | Reciprocal Rank Fusion，倒数排名融合 |
| SSE | Server-Sent Events，服务器推送事件 |
| TTFT | Time To First Token，首 token 延迟 |
| CoVe | Chain of Verification，验证链 |
| SPA | Single Page Application，单页应用 |
| Supervisor | 监督者 Agent，负责意图分类和 Agent 路由 |
| AgentEval | 内置 Agent 评估系统 |
| L0/L1/L2 | 文档分层分块的三个粒度级别 |
