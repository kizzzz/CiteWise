# CiteWise 项目状态

> 最后更新: 2026-04-03
> 状态: **MVP Demo 可运行**

## 项目概况
- 目标: AI产品经理面试核心项目 — 从文献梳理到论文产出的全流程智能助手
- 技术栈: 智谱 GLM-4-flash + embedding-3 + Chroma + Streamlit
- API: 智谱 (base_url=open.bigmodel.cn)

## 已实现功能
- [x] PDF上传解析 + 层级切片(L0论文级/L1章节级/L2段落级)
- [x] 混合检索(BM25+向量+RRF融合+重排)
- [x] 主对话(全局记忆) + 子对话(章节级，只读继承主对话)
- [x] 程序化来源标注(📖RAG蓝/🌐联网绿/🧠推理紫)
- [x] 联网搜索(DuckDuckGo API)
- [x] 思考过程展示(Agent Think Steps)
- [x] 结构化总结(自定义字段 + Excel导出 + 可视化图表)
- [x] 侧边栏章节管理(增删 + 导航到子对话)
- [x] 主对话自然语言管理章节("删除引言"/"帮我写文献综述")
- [x] 6篇测试论文已入库

## 项目结构
```
~/CiteWise/
├── app.py                    # Streamlit 前端
├── config/settings.py        # 智谱 API 配置
├── src/
│   ├── core/llm.py          # LLM 调用层(chat + chat_json)
│   ├── core/rag.py          # PDF 解析+层级切片
│   ├── core/embedding.py    # Embedding(智谱embedding-3) + Chroma向量库
│   ├── core/retriever.py    # 混合检索(BM25+向量+RRF+重排)
│   ├── core/prompt.py       # 5层动态Prompt模板
│   ├── core/memory.py       # 三层记忆(GlobalProfile/ProjectMemory/WorkingMemory)
│   ├── core/agent.py        # ReAct Agent + 意图路由 + 来源标注
│   └── tools/web_search.py  # 联网搜索(DuckDuckGo)
├── data/db/citewise.db       # SQLite(项目/论文/提取/章节)
├── data/db/chroma/           # Chroma向量库
├── papers/                   # 上传的PDF文件
└── docs/                     # 技术设计文档(10篇)
```

## 关键设计决策
1. 来源标注用**程序化后处理**(不依赖LLM加emoji)，遍历段落匹配引用和关键词
2. 结构化总结结果存session_state，rerun后在主区域独立渲染，避免expander嵌套
3. 章节去重: DB层用 `get_unique_sections()` 同名只保留最新
4. 提取去重: `get_extractions()` 每篇论文只计最新一次
5. 子对话augmented prompt明确告知LLM当前编辑的章节名

## 已修复的历史问题
- openpyxl缺失 → pip install openpyxl
- BM25空列表ZeroDivision → 空列表检查
- SYSTEM_PROMPT未导入 → agent.py添加import
- PDF年份解析为0 → 始终调用_parse_from_filename
- 意图路由答非所问 → 问句检测(？→explore) + generate需比explore分高
- 来源标注不显示 → agent添加_annotate_sources后处理
- StreamlitDuplicateElementKey → key加索引
- 前端容器嵌套错位 → 完整重写app.py，分离渲染逻辑
- session_state.pop导致界面消失 → 改为get保留数据

## 待完成
1. Prompt调优: 生成内容质量和引用准确度
2. 错误处理: LLM API调用失败时的优雅降级
3. 导出增强: Word/PDF格式导出
4. 多轮对话记忆: 主对话历史太长时的压缩策略
5. 面试Demo脚本: 按docs/09-demo-script.md演练

## 数据库状态
- 论文: 6篇
- 提取记录: 6条(已去重)
- 生成章节: 3个(引言/方法论/结论，已去重)
