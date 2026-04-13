"""来源标注与摘要 — 独立的纯函数模块"""
import re
import logging

logger = logging.getLogger(__name__)


def _normalize_author(author: str) -> str:
    """标准化作者名：去'等'/'et al.'，取姓氏部分"""
    author = author.strip()
    author = re.sub(r'\s*等\.?\s*$', '', author)
    author = re.sub(r'\s*et al\.?\s*$', '', author, flags=re.IGNORECASE)
    parts = author.split()
    return parts[0].lower() if parts else author.lower()


def _cite_matches_rag(cite: str, year_author_pairs: list, rag_citations: set) -> bool:
    """检查引用是否匹配 RAG 来源（精确 + 模糊）"""
    if cite in rag_citations:
        return True
    # 模糊匹配
    cite_year_match = re.search(r'(\d{4})', cite)
    cite_year = cite_year_match.group(1) if cite_year_match else ""
    cite_author = _normalize_author(re.sub(r',?\s*\d{4}$', '', cite))
    for ref_year, ref_author in year_author_pairs:
        if cite_year == ref_year and cite_author == ref_author:
            return True
    return False


def annotate_sources(content: str, rag_chunks: list[dict], web_results: list[dict]) -> str:
    """程序化标注内容来源：RAG文献 / 网络搜索 / LLM推理

    遍历每一段落，根据引用和关键词匹配判断来源类型，在段首添加标记。
    """
    if not content or not content.strip():
        return content

    # 1. 构建 RAG 引用匹配集合
    rag_citations = set()
    year_author_pairs = []
    for c in rag_chunks:
        meta = c.get("metadata", {})
        authors = meta.get("authors", "") or c.get("authors", "")
        year = meta.get("year", "") or c.get("year", "")
        if authors and year:
            rag_citations.add(f"{authors}, {year}")
            year_author_pairs.append((str(year), _normalize_author(authors)))

    # 2. 构建网络来源关键词集合
    web_keywords = set()
    web_urls = []
    for r in web_results:
        title = r.get("title", "")
        if title:
            for word in re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', title):
                web_keywords.add(word.lower())
        url = r.get("url", "")
        if url:
            web_urls.append(url)
            domain_match = re.search(r'://([^/]+)', url)
            if domain_match:
                web_keywords.add(domain_match.group(1).lower())

    # 3. 按段落处理
    paragraphs = content.split("\n")
    annotated = []
    source_stats = {"rag": 0, "web": 0, "llm": 0}

    for para in paragraphs:
        stripped = para.strip()
        if not stripped or stripped.startswith("#"):
            annotated.append(para)
            continue

        is_rag = False
        is_web = False

        en_cites = re.findall(r'\[([A-Z][\w\s]+(?:et al\.)?,\s*\d{4})\]', stripped)
        zh_cites = re.findall(r'\[([\u4e00-\u9fff]+等?,\s*\d{4})\]', stripped)
        all_cites = en_cites + zh_cites

        for cite in all_cites:
            if _cite_matches_rag(cite, year_author_pairs, rag_citations):
                is_rag = True
                break

        if not is_rag and web_keywords:
            for url in web_urls:
                if url and url in stripped:
                    is_web = True
                    break
            if not is_web:
                para_words = set(re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}', stripped.lower()))
                overlap = para_words & web_keywords
                if len(overlap) >= 2:
                    is_web = True

        if is_rag:
            annotated.append(f"[KB] {para}")
            source_stats["rag"] += 1
        elif is_web:
            annotated.append(f"[WEB] {para}")
            source_stats["web"] += 1
        else:
            annotated.append(f"[AI] {para}")
            source_stats["llm"] += 1

    logger.info(f"[Annotate] RAG={source_stats['rag']}, Web={source_stats['web']}, LLM={source_stats['llm']}")
    return "\n".join(annotated)


def summarize_section(llm_client, content: str) -> str:
    """用 LLM 压缩章节为100字摘要"""
    if len(content) < 200:
        return content
    messages = [
        {"role": "system", "content": "将以下论文章节压缩为100字以内的简洁摘要，保留核心观点和关键引用。"},
        {"role": "user", "content": content[:3000]},
    ]
    return llm_client.chat(messages, temperature=0.3, max_tokens=200)
