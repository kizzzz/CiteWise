"""WriterAgent — 章节生成 + 改写"""
import json
import logging

from src.core.agents.base import BaseAgent
from src.core.retriever import validate_citations

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    """写作 Agent — 负责内容生成和改写"""

    def __init__(self):
        super().__init__("Writer")
        self._llm = None
        self._profile = None
        self._pm = None
        self._wm = None

    def _ensure_deps(self):
        if self._llm is None:
            from src.core.llm import llm_client
            from src.core.memory import global_profile, project_memory, working_memory
            self._llm = llm_client
            self._profile = global_profile
            self._pm = project_memory
            self._wm = working_memory

    def generate_section(self, section_name: str, section_topic: str,
                         research_result: dict, project_id: str,
                         framework: list = None, gen_params: dict = None) -> dict:
        """基于检索结果生成章节"""
        self.reset()
        self._ensure_deps()
        self.think(f"生成章节: {section_name}")

        from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE

        # Extract generation parameters with defaults
        params = gen_params or {}
        style = params.get("style", "学术正式")
        target_words = params.get("target_length", 1000)
        citation_density = params.get("citation_density", "正常")

        # Map citation density to minimum citations per paragraph
        density_map = {"高": "每段至少 2 个引用", "正常": "适当引用关键观点", "低": "仅在关键结论处引用"}
        citation_instruction = density_map.get(citation_density, "适当引用关键观点")

        rag_content = research_result.get("rag_content", "")
        chunks = research_result.get("chunks", [])
        previous_summary = self._wm.get_previous_summary()

        system = SYSTEM_PROMPT_BASE
        task_prompt = prompt_engine.build_section_prompt(
            section_name=section_name,
            section_topic=section_topic,
            reference_material=rag_content,
            framework=str(framework) if framework else "",
            previous_summary=previous_summary,
            target_words=target_words,
            writing_style=style,
        )

        # Add citation density instruction
        task_prompt += f"\n\n### 引用密度要求\n{citation_instruction}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task_prompt},
        ]

        self.think("调用 LLM 生成...")
        content = self._llm.chat(messages, temperature=0.7, max_tokens=4000)
        self.think(f"生成完成: {len(content)} 字")

        # 来源标注
        from src.core.source_annotation import annotate_sources, summarize_section
        content = annotate_sources(content, chunks, [])
        self.think("来源标注完成")

        # 保存
        self._pm.save_section(project_id, section_name, content)
        summary = summarize_section(self._llm, content)
        self._wm.add_section_summary(section_name, summary, len(content))

        citation_check = validate_citations(content, chunks)

        return {
            "type": "section",
            "content": content,
            "section_name": section_name,
            "intent": "generate",
            "citations": citation_check,
            "word_count": len(content),
            "sources": [
                {"title": c.get("paper_title", ""), "citation": c.get("citation", "")}
                for c in chunks
            ] if chunks else [],
            "thinking_steps": self.thinking_steps,
        }

    def modify_content(self, instruction: str, target_content: str,
                       research_result: dict, project_id: str) -> dict:
        """修改已有内容"""
        self.reset()
        self._ensure_deps()
        self.think(f"修改指令: {instruction[:50]}")

        from src.core.prompt import prompt_engine, SYSTEM_PROMPT_BASE

        chunks = research_result.get("chunks", [])
        reference = research_result.get("rag_content", "")

        task_prompt = prompt_engine.build_rewrite_prompt(
            instruction=instruction,
            target_paragraph=target_content[:4000],
            full_article="",
            reference_material=reference,
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT_BASE},
            {"role": "user", "content": task_prompt},
        ]

        result = self._llm.chat_json(messages, temperature=0.5)
        self.think("修改完成")

        return {
            "type": "modify",
            "content": result.get("modified_paragraph", target_content),
            "change_summary": result.get("change_summary", "已修改"),
            "intent": "modify",
            "thinking_steps": self.thinking_steps,
        }

    def process(self, user_input: str, project_id: str = None, **kwargs) -> dict:
        intent = kwargs.get("intent", "generate")
        research_result = kwargs.get("research_result", {})
        gen_params = kwargs.get("gen_params", None)

        if intent == "modify":
            target_content = kwargs.get("target_content", "")
            return self.modify_content(user_input, target_content, research_result, project_id)
        else:
            section_name = kwargs.get("section_name", "文献综述")
            section_topic = kwargs.get("section_topic", "")
            framework = kwargs.get("framework", [])
            return self.generate_section(
                section_name, section_topic, research_result, project_id, framework, gen_params
            )
