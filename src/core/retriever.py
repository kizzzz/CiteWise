"""混合检索：BM25 + 向量 + RRF 融合 + 重排序"""
import re
import logging
from rank_bm25 import BM25Okapi
import jieba

from config.settings import RRF_K, RERANK_TOP_K, VECTOR_TOP_K, BM25_TOP_K
from src.core.embedding import vector_store

logger = logging.getLogger(__name__)


class BM25Index:
    """基于 rank_bm25 的 BM25 索引"""

    def __init__(self):
        self.bm25 = None
        self.chunk_map: dict[str, dict] = {}

    def build_index(self, chunks: list[dict]):
        """从 chunks 构建 BM25 索引"""
        self.chunk_map = {c["chunk_id"]: c for c in chunks}
        texts = [c["text"] for c in chunks]

        # 中英文混合分词
        tokenized = []
        for text in texts:
            # 英文按空格分割，中文用 jieba
            en_tokens = re.findall(r'[a-zA-Z]+', text)
            zh_tokens = list(jieba.cut(text))
            tokenized.append(en_tokens + zh_tokens)

        self.bm25 = BM25Okapi(tokenized)
        logger.info(f"BM25 索引已构建，共 {len(chunks)} 个文档")

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """BM25 检索"""
        if not self.bm25:
            return []
        en_tokens = re.findall(r'[a-zA-Z]+', query)
        zh_tokens = list(jieba.cut(query))
        tokenized_query = en_tokens + zh_tokens

        scores = self.bm25.get_scores(tokenized_query)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        results = []
        chunk_ids = list(self.chunk_map.keys())
        for idx in ranked[:top_k]:
            cid = chunk_ids[idx]
            chunk = self.chunk_map[cid]
            results.append({
                "chunk_id": cid,
                "text": chunk["text"],
                "metadata": chunk.get("metadata", {}),
                "bm25_score": float(scores[idx]),
            })
        return results


# 全局 BM25 索引
bm25_index = BM25Index()


def reciprocal_rank_fusion(vector_results: list[dict], bm25_results: list[dict],
                           k: int = RRF_K) -> list[str]:
    """RRF 融合两路检索结果"""
    scores = {}

    for rank, doc in enumerate(vector_results):
        doc_id = doc["chunk_id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)

    for rank, doc in enumerate(bm25_results):
        doc_id = doc["chunk_id"]
        scores[doc_id] = scores.get(doc_id, 0) + 1.0 / (k + rank + 1)

    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [doc_id for doc_id, _ in ranked]


def rerank_by_relevance(query: str, candidates: list[dict], top_k: int = RERANK_TOP_K) -> list[dict]:
    """混合重排序：LLM 精排（候选≤10）+ 向量距离粗排（候选>10）"""
    if not candidates:
        return []

    # For >10 candidates, use simple scoring first to reduce to 10
    if len(candidates) > 10:
        scored = []
        for c in candidates:
            score = 1.0 / (1.0 + c.get("distance", 1.0))
            query_terms = set(re.findall(r'[a-zA-Z]{3,}', query.lower()))
            text_terms = set(re.findall(r'[a-zA-Z]{3,}', c["text"].lower()))
            overlap = len(query_terms & text_terms)
            if overlap > 0:
                score += 0.1 * overlap
            scored.append((c, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        candidates = [c for c, s in scored[:10]]

    # LLM-based reranking for the top candidates
    try:
        return _llm_rerank(query, candidates, top_k)
    except Exception as e:
        logger.warning(f"LLM rerank failed, falling back to simple scoring: {e}")
        # Fallback to simple scoring
        scored = []
        for c in candidates:
            score = 1.0 / (1.0 + c.get("distance", 1.0))
            scored.append((c, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, s in scored[:top_k]]


def _llm_rerank(query: str, candidates: list[dict], top_k: int) -> list[dict]:
    """Use LLM to score candidate chunks for relevance to the query."""
    from src.core.llm import llm_client

    # Build candidate list for LLM
    chunks_text = ""
    for i, c in enumerate(candidates):
        chunks_text += f"\n[{i+1}] {c['text'][:200]}\n"

    prompt = f"""请评估以下文献片段与查询的相关性，给每个片段打1-10分。
查询：{query}

片段：
{chunks_text}

请用 JSON 格式回复：{{"scores": [分数1, 分数2, ...]}}
只回复 JSON。"""

    messages = [
        {"role": "system", "content": "你是相关性评估器，只输出 JSON。"},
        {"role": "user", "content": prompt},
    ]

    result = llm_client.chat_json(messages, temperature=0.1, max_retries=1)
    scores = result.get("scores", [])

    if not scores or len(scores) != len(candidates):
        raise ValueError(f"Score count mismatch: got {len(scores)}, expected {len(candidates)}")

    # Combine LLM score with vector distance
    scored = []
    for i, c in enumerate(candidates):
        llm_score = float(scores[i])
        vec_score = 1.0 / (1.0 + c.get("distance", 1.0))
        # Weighted: 70% LLM score, 30% vector similarity
        combined = 0.7 * llm_score + 0.3 * vec_score * 10
        scored.append((c, combined))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [c for c, s in scored[:top_k]]


def hybrid_search(query: str, top_k: int = RERANK_TOP_K, where: dict = None,
                  project_id: str = None) -> list[dict]:
    """混合检索主入口：向量 + BM25 → RRF 融合 → 重排序

    project_id 参数接受但不用于过滤（Chroma metadata 中无此字段），
    保留参数以兼容调用方签名。后续可按 paper_id 列表过滤。
    """
    # 1. 向量检索
    vector_results = vector_store.vector_search(query, top_k=VECTOR_TOP_K, where=where)

    # 2. BM25 检索
    bm25_results = bm25_index.search(query, top_k=BM25_TOP_K)

    # 3. RRF 融合
    fused_ids = reciprocal_rank_fusion(vector_results, bm25_results)

    # 4. 收集候选文档
    id_to_doc = {}
    for doc in vector_results + bm25_results:
        id_to_doc[doc["chunk_id"]] = doc

    candidates = [id_to_doc[cid] for cid in fused_ids if cid in id_to_doc]

    # 5. 重排序
    results = rerank_by_relevance(query, candidates, top_k=top_k)

    # 6. 格式化输出（带引用信息）
    for r in results:
        meta = r.get("metadata", {})
        r["citation"] = f"[{meta.get('authors', 'Unknown')}, {meta.get('year', 'N/A')}]"
        r["paper_title"] = meta.get("paper_title", "")
        r["section_title"] = meta.get("section_title", "")

    return results


def format_chunks_with_citations(chunks: list[dict]) -> str:
    """为检索片段添加引用标注，用于 Prompt 注入"""
    formatted = []
    for i, chunk in enumerate(chunks, 1):
        citation = chunk.get("citation", "")
        paper_title = chunk.get("paper_title", "")
        section = chunk.get("section_title", "")
        header = f"--- 文献 {i}: {paper_title} {citation} | 章节: {section} ---"
        formatted.append(f"{header}\n{chunk['text']}")
    return "\n\n".join(formatted)


def _normalize_author(author: str) -> str:
    """标准化作者名用于模糊匹配：去'等'/'et al.'，取姓氏部分"""
    author = author.strip()
    # 去掉 "等" / "et al." 后缀
    author = re.sub(r'\s*等\.?\s*$', '', author)
    author = re.sub(r'\s*et al\.?\s*$', '', author, flags=re.IGNORECASE)
    # 取第一个姓氏/词
    parts = author.split()
    return parts[0].lower() if parts else author.lower()


def validate_citations(generated_text: str, retrieved_chunks: list[dict]) -> dict:
    """校验生成文本中的引用是否都有检索依据"""
    # 提取引用（英文 [Author et al., 2025] + 中文 [张明等, 2023]）
    en_citations = re.findall(r'\[([A-Z][\w\s]+(?:et al\.)?,\s*\d{4})\]', generated_text)
    zh_citations = re.findall(r'\[([\u4e00-\u9fff]+等?,\s*\d{4})\]', generated_text)
    citations_in_text = en_citations + zh_citations

    # 有效引用集合 — 同时建立 (year, normalized_author) 索引
    valid_refs = set()
    year_author_pairs = []
    for c in retrieved_chunks:
        meta = c.get("metadata", {})
        authors = meta.get("authors", "") or c.get("authors", "")
        year = meta.get("year", "") or c.get("year", "")
        if authors and year:
            valid_refs.add(f"{authors}, {year}")
            year_author_pairs.append((str(year), _normalize_author(authors)))

    # 精确匹配 + 模糊匹配
    unverified = []
    for cite in citations_in_text:
        if cite in valid_refs:
            continue
        # 模糊匹配：提取引用的年份和作者
        cite_year_match = re.search(r'(\d{4})', cite)
        cite_year = cite_year_match.group(1) if cite_year_match else ""
        cite_author = _normalize_author(re.sub(r',?\s*\d{4}$', '', cite))
        matched = False
        for ref_year, ref_author in year_author_pairs:
            if cite_year == ref_year and cite_author == ref_author:
                matched = True
                break
        if not matched:
            unverified.append(cite)

    return {
        "total_citations": len(citations_in_text),
        "verified": len(citations_in_text) - len(unverified),
        "unverified": unverified,
        "verification_rate": (len(citations_in_text) - len(unverified)) / max(len(citations_in_text), 1)
    }
