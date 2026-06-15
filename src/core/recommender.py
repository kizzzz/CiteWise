"""智能文献推荐 — 基于语义相似度和引用关系"""
import json
import logging
import re
import numpy as np
from typing import Optional

from src.core.memory import project_memory
from src.core.embedding import vector_store

logger = logging.getLogger(__name__)


def get_paper_embeddings(project_id: str) -> dict[str, list[float]]:
    """Compute paper-level embeddings by averaging chunk embeddings."""
    papers = project_memory.get_papers(project_id)
    result = {}

    for paper in papers:
        paper_id = paper["id"]
        try:
            # Get chunks for this paper from vector store
            chunks = vector_store.get_chunks_by_paper(paper_id)
            if chunks:
                embeddings = [c.get("embedding", []) for c in chunks if c.get("embedding")]
                if embeddings:
                    avg_embedding = np.mean(embeddings, axis=0).tolist()
                    result[paper_id] = avg_embedding
        except Exception as e:
            logger.warning(f"Failed to get embedding for paper {paper_id}: {e}")

    return result


def compute_similarity_matrix(embeddings: dict[str, list[float]]) -> dict[str, list[tuple[str, float]]]:
    """Compute pairwise cosine similarity between paper embeddings."""
    if len(embeddings) < 2:
        return {}

    paper_ids = list(embeddings.keys())
    emb_matrix = np.array([embeddings[pid] for pid in paper_ids])

    # Normalize
    norms = np.linalg.norm(emb_matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    normalized = emb_matrix / norms

    # Cosine similarity
    sim_matrix = np.dot(normalized, normalized.T)

    result = {}
    for i, pid in enumerate(paper_ids):
        similarities = []
        for j, other_pid in enumerate(paper_ids):
            if i != j:
                similarities.append((other_pid, float(sim_matrix[i][j])))
        similarities.sort(key=lambda x: x[1], reverse=True)
        result[pid] = similarities

    return result


def extract_citations(text: str) -> list[str]:
    """Extract author-year citations from text."""
    # Match patterns like (Author, 2024), (Author et al., 2023)
    pattern = r'\(([^)]+?,\s*\d{4})\)'
    matches = re.findall(pattern, text)
    return list(set(matches))


def build_citation_graph(project_id: str) -> dict[str, set[str]]:
    """Build a citation graph from paper full texts."""
    papers = project_memory.get_papers(project_id)
    graph = {}

    for paper in papers:
        pid = paper["id"]
        title = paper.get("title", "")
        authors = paper.get("authors", "")
        full_text = paper.get("raw_text", "") or ""

        # This paper cites others
        cited = set()
        for other in papers:
            if other["id"] == pid:
                continue
            other_title = other.get("title", "")
            other_authors = other.get("authors", "")
            # Check if other paper is referenced
            if other_title and other_title in full_text:
                cited.add(other["id"])
            elif other_authors:
                # Check by author name
                first_author = other_authors.split(",")[0].strip()
                if first_author and first_author in full_text:
                    cited.add(other["id"])

        graph[pid] = cited

    return graph


def get_recommendations(project_id: str, top_k: int = 5) -> list[dict]:
    """Generate paper recommendations: internal similarity + external APIs + LLM fallback."""
    papers = project_memory.get_papers(project_id)

    # Try external recommendations (Semantic Scholar)
    external = _semantic_scholar_recommendations(papers, top_k)

    # Internal recommendations need >= 2 papers
    internal = []
    if len(papers) >= 2:
        # Build paper ID to title mapping
        pid_to_title = {p["id"]: p.get("title", "Untitled") for p in papers}
        pid_to_authors = {p["id"]: p.get("authors", "") for p in papers}
        pid_to_year = {p["id"]: str(p.get("year", "")) for p in papers}

        # Compute similarity
        embeddings = get_paper_embeddings(project_id)
        if embeddings:
            sim_matrix = compute_similarity_matrix(embeddings)
            citation_graph = build_citation_graph(project_id)
            citation_count = {}
            for pid, cited in citation_graph.items():
                for cited_pid in cited:
                    citation_count[cited_pid] = citation_count.get(cited_pid, 0) + 1

            for pid, similar in sim_matrix.items():
                for other_pid, score in similar[:top_k]:
                    cit_boost = citation_count.get(other_pid, 0) * 0.05
                    internal.append({
                        "source_paper_id": pid,
                        "source_paper_title": pid_to_title.get(pid, ""),
                        "recommended_paper_id": other_pid,
                        "recommended_paper_title": pid_to_title.get(other_pid, ""),
                        "recommended_paper_authors": pid_to_authors.get(other_pid, ""),
                        "recommended_paper_year": pid_to_year.get(other_pid, ""),
                        "similarity_score": round(min(1.0, score + cit_boost), 3),
                        "recommendation_reason": f"与「{pid_to_title.get(pid, '未知')[:20]}」高度相关"
                            + (f"，被引用 {citation_count.get(other_pid, 0)} 次" if citation_count.get(other_pid, 0) > 0 else ""),
                    })
        else:
            internal = _chunk_based_recommendations(project_id, papers, top_k)

    # Merge and deduplicate
    seen = set()
    merged = []
    for rec in sorted(internal + external, key=lambda x: x["similarity_score"], reverse=True):
        key = (rec.get("source_paper_id", ""), rec.get("recommended_paper_id", ""), rec.get("recommended_paper_title", ""))
        if key not in seen:
            seen.add(key)
            merged.append(rec)

    # Fallback: if no results from any source, use LLM to generate recommendations
    if not merged and papers:
        merged = _llm_fallback_recommendations(papers, top_k, project_memory.get_project(project_id))

    return merged[:top_k * max(len(papers), 1)]


def _chunk_based_recommendations(project_id: str, papers: list[dict], top_k: int) -> list[dict]:
    """Fallback: recommend based on shared keywords between paper titles/abstracts."""
    from src.core.retriever import hybrid_search

    pid_to_title = {p["id"]: p.get("title", "Untitled") for p in papers}
    pid_to_authors = {p["id"]: p.get("authors", "") for p in papers}
    pid_to_year = {p["id"]: str(p.get("year", "")) for p in papers}

    recommendations = []
    for paper in papers:
        title = paper.get("title", "")
        if not title:
            continue

        # Search for similar papers
        results = hybrid_search(title, top_k=top_k + 1, project_id=project_id)
        for r in results:
            other_pid = r.get("paper_id", "")
            if other_pid and other_pid != paper["id"]:
                # Fallback title: try result field, then pid_to_title mapping
                rec_title = r.get("paper_title", "") or pid_to_title.get(other_pid, "Unknown")
                recommendations.append({
                    "source_paper_id": paper["id"],
                    "source_paper_title": pid_to_title.get(paper["id"], ""),
                    "recommended_paper_id": other_pid,
                    "recommended_paper_title": rec_title,
                    "recommended_paper_authors": pid_to_authors.get(other_pid, ""),
                    "recommended_paper_year": pid_to_year.get(other_pid, ""),
                    "similarity_score": round(1.0 / (1.0 + r.get("distance", 1.0)), 3),
                    "recommendation_reason": f"基于检索相似性推荐",
                })

    return recommendations[:top_k * len(papers)]


def _semantic_scholar_recommendations(papers: list[dict], top_k: int) -> list[dict]:
    """Recommend external papers via Semantic Scholar API (no key required for basic use)."""
    import os
    import httpx

    api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
    if not papers:
        return []

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    # Collect paper titles for search queries
    titles = [p.get("title", "") for p in papers if p.get("title")]
    if not titles:
        return []

    recommendations = []
    seen_titles = set()

    # Use up to 3 paper titles as search seeds
    for title in titles[:3]:
        try:
            # Search Semantic Scholar for related papers
            url = "https://api.semanticscholar.org/graph/v1/paper/search"
            params = {
                "query": title[:200],
                "limit": top_k + 2,
                "fields": "title,authors,year,citationCount,abstract,url",
            }
            with httpx.Client(timeout=10) as client:
                resp = client.get(url, params=params, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Semantic Scholar API returned {resp.status_code}")
                continue

            data = resp.json()
            for paper_data in data.get("data", []):
                rec_title = paper_data.get("title", "")
                if not rec_title or rec_title in seen_titles:
                    continue
                # Skip papers already in the project
                if any(rec_title.lower() == t.lower() for t in titles):
                    continue
                seen_titles.add(rec_title)

                authors = ", ".join(a.get("name", "") for a in paper_data.get("authors", [])[:3])
                year = str(paper_data.get("year", ""))
                citations = paper_data.get("citationCount", 0)
                url = paper_data.get("url", "")

                recommendations.append({
                    "source_paper_id": "",
                    "source_paper_title": "",
                    "recommended_paper_id": url or f"ss_{paper_data.get('paperId', '')[:8]}",
                    "recommended_paper_title": rec_title,
                    "recommended_paper_authors": authors,
                    "recommended_paper_year": year,
                    "similarity_score": round(min(1.0, min(citations, 100) / 100 * 0.7 + 0.1), 3),
                    "recommendation_reason": f"外部推荐：引用 {citations} 次" if citations > 0 else "外部推荐：语义相关",
                    "external_url": url,
                })
        except Exception as e:
            logger.warning(f"Semantic Scholar search failed for '{title[:30]}': {e}")

    return recommendations[:top_k * 2]


def _llm_fallback_recommendations(
    papers: list[dict], top_k: int, project: Optional[dict] = None
) -> list[dict]:
    """Fallback: use LLM + web search to recommend related papers."""
    from src.core.llm import llm_client
    from src.tools.web_search import web_search

    titles = [p.get("title", "") for p in papers if p.get("title")]
    if not titles:
        return []

    topic = project.get("topic", "") if project else ""

    # Step 1: Web search for related papers
    web_results = []
    for query_seed in (titles[:2] if titles else [topic])[:2]:
        results = web_search(f"{query_seed} related papers research", top_k=5)
        web_results.extend(results)

    web_text = "\n".join(
        f"- [{r.get('title', '')}]({r.get('url', '')}): {r.get('snippet', '')}"
        for r in web_results[:10]
    ) if web_results else "No web results available."

    # Step 2: LLM generates recommendations
    prompt = f"""Based on the following research papers and web search results, recommend {top_k} related academic papers that would be valuable to read.

Current papers in the project:
{json.dumps([{'title': t} for t in titles[:5]], ensure_ascii=False, indent=2)}

Research topic: {topic or 'general'}

Web search results:
{web_text}

For each recommendation provide:
- title: exact paper title
- authors: up to 3 author names
- year: publication year (estimate if unsure)
- reason: why this paper is relevant (one sentence in Chinese)

Return JSON:
{{"recommendations": [{{"title": "...", "authors": "...", "year": "...", "reason": "..."}}]}}

Only return JSON. Focus on real, well-known papers if possible."""

    try:
        result = llm_client.chat_json(
            [
                {"role": "system", "content": "You are an academic paper recommendation expert. Only return valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
        )

        recs = result.get("recommendations", [])
        recommendations = []
        for i, r in enumerate(recs[:top_k]):
            rec_title = r.get("title", "")
            if not rec_title:
                continue
            recommendations.append({
                "source_paper_id": "",
                "source_paper_title": "",
                "recommended_paper_id": f"llm_rec_{i}",
                "recommended_paper_title": rec_title,
                "recommended_paper_authors": r.get("authors", ""),
                "recommended_paper_year": r.get("year", ""),
                "similarity_score": round(0.5 + 0.1 * (top_k - i) / top_k, 3),
                "recommendation_reason": r.get("reason", "LLM 推荐：相关研究"),
            })
        return recommendations

    except Exception as e:
        logger.warning(f"LLM fallback recommendations failed: {e}")
        return []
