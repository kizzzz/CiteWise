"""CoordinatorAgent — 多 Agent 编排与调度"""
import logging

from src.core.agents.base import BaseAgent
from src.core.agents.router import RouterAgent
from src.core.agents.researcher import ResearchAgent
from src.core.agents.writer import WriterAgent
from src.core.agents.analyst import AnalystAgent

logger = logging.getLogger(__name__)


class CoordinatorAgent(BaseAgent):
    """协调 Agent — 统一入口，调度多 Agent 协同"""

    def __init__(self):
        super().__init__("Coordinator")
        self.router = RouterAgent()
        self.researcher = ResearchAgent()
        self.writer = WriterAgent()
        self.analyst = AnalystAgent()

    def process(self, user_input: str, project_id: str = None, **kwargs) -> dict:
        """统一处理入口 — 路由 → 检索 → 生成/分析"""
        self.reset()

        # 1. 路由
        try:
            route_result = self.router.process(user_input, project_id)
            intent = route_result["intent"]
            target_agent = route_result["target_agent"]
            thinking_steps = list(route_result.get("thinking_steps", []))
        except Exception as e:
            logger.error(f"[Coordinator] 路由失败: {e}")
            return {"type": "text", "content": f"路由阶段出错: {e}", "thinking_steps": self.thinking_steps}

        self.think(f"路由 → {target_agent} (意图: {intent})")

        # 2. 检索（所有意图都需要 RAG，除了 export）
        research_result = {}
        if intent not in ("export",):
            try:
                research_result = self.researcher.process(
                    user_input, project_id, intent=intent
                )
                thinking_steps.extend(research_result.get("thinking_steps", []))
            except Exception as e:
                logger.error(f"[Coordinator] 检索失败: {e}")
                self.think(f"检索阶段出错: {e}")

        # 3. 执行目标 Agent
        result = {}
        try:
            if target_agent == "researcher":
                # 探索/总结/联网 — 直接构建响应
                result = self._build_research_response(
                    user_input, intent, research_result, project_id
                )
            elif target_agent == "writer":
                result = self.writer.process(
                    user_input, project_id,
                    intent=intent,
                    research_result=research_result,
                    section_name=kwargs.get("section_name"),
                    section_topic=kwargs.get("section_topic"),
                    framework=kwargs.get("framework", []),
                    target_content=kwargs.get("target_content", ""),
                )
            elif target_agent == "analyst":
                result = self.analyst.process(
                    user_input, project_id,
                    intent=intent,
                    table_content=kwargs.get("table_content", ""),
                    split_by=kwargs.get("split_by", "columns"),
                    desc_a=kwargs.get("desc_a", ""),
                    desc_b=kwargs.get("desc_b", ""),
                )
        except Exception as e:
            logger.error(f"[Coordinator] 执行失败: {e}")
            result = {"type": "text", "content": f"执行阶段出错: {e}"}

        # 4. 汇总思考步骤
        result["thinking_steps"] = thinking_steps + result.get("thinking_steps", [])
        return result

    def _build_research_response(self, user_input: str, intent: str,
                                 research_result: dict, project_id: str) -> dict:
        """构建基于检索的响应"""
        from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE
        from src.core.source_annotation import annotate_sources

        chunks = research_result.get("chunks", [])
        web_results = research_result.get("web_results", [])

        # Sanitize user input for prompt injection prevention
        safe_input = user_input.replace("```", " ").replace("<|", " ").strip()

        if intent == "websearch" and web_results:
            # 联网搜索 — 多源整合
            rag_content = research_result.get("rag_content", "")
            web_snippets = "\n".join(
                f"- [{r['title']}]({r['url']}): {r['snippet']}"
                for r in web_results
            )
            llm_knowledge = research_result.get("llm_knowledge", "")

            prompt = f"""## 用户问题
{safe_input}

## 网络搜索结果
{web_snippets}

## 知识库文献
{rag_content if rag_content else '（无）'}

## LLM 自身知识
{llm_knowledge}

请整合以上来源回答用户问题，"""
        else:
            # 普通探索
            rag_content = research_result.get("rag_content", "（无相关内容）")
            prompt = f"""## 用户问题
{safe_input}

## 参考材料（知识库检索）
{rag_content}

请基于参考材料和自身知识回答，使用 [作者, 年份] 标注引用。"""

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_BASE},
            {"role": "user", "content": prompt},
        ]

        from src.core.llm import llm_client
        response = llm_client.chat(messages, temperature=0.7)

        # 程序化来源标注
        response = annotate_sources(response, chunks, web_results)

        from src.core.retriever import validate_citations
        citation_check = validate_citations(response, chunks) if chunks else {}

        sources = [
            {"title": c.get("paper_title", ""), "citation": c.get("citation", "")}
            for c in chunks
        ] if chunks else []

        return {
            "type": "text",
            "content": response,
            "intent": intent,
            "citations": citation_check,
            "sources": sources,
            "content_sources": {
                "rag": bool(chunks),
                "llm": True,
                "web": bool(web_results),
            },
        }


# 全局单例
coordinator = CoordinatorAgent()
