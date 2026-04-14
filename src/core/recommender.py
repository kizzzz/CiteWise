"""智能文献推荐 — 基于语义相似度和引用关系"""
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
    """Generate paper recommendations based on similarity and citation network."""
    papers = project_memory.get_papers(project_id)
    if len(papers) < 2:
        return []

    # Build paper ID to title mapping
    pid_to_title = {p["id"]: p.get("title", "Untitled") for p in papers}
    pid_to_authors = {p["id"]: p.get("authors", "") for p in papers}
    pid_to_year = {p["id"]: str(p.get("year", "")) for p in papers}

    # Compute similarity
    embeddings = get_paper_embeddings(project_id)
    if not embeddings:
        # Fallback: use chunk-level text similarity
        return _chunk_based_recommendations(project_id, papers, top_k)

    sim_matrix = compute_similarity_matrix(embeddings)

    # Get citation counts
    citation_graph = build_citation_graph(project_id)
    citation_count = {}
    for pid, cited in citation_graph.items():
        for cited_pid in cited:
            citation_count[cited_pid] = citation_count.get(cited_pid, 0) + 1

    # Generate recommendations
    recommendations = []
    for pid, similar in sim_matrix.items():
        for other_pid, score in similar[:top_k]:
            # Boost score by citation count
            cit_boost = citation_count.get(other_pid, 0) * 0.05
            final_score = min(1.0, score + cit_boost)

            recommendations.append({
                "source_paper_id": pid,
                "source_paper_title": pid_to_title.get(pid, ""),
                "recommended_paper_id": other_pid,
                "recommended_paper_title": pid_to_title.get(other_pid, ""),
                "recommended_paper_authors": pid_to_authors.get(other_pid, ""),
                "recommended_paper_year": pid_to_year.get(other_pid, ""),
                "similarity_score": round(score, 3),
                "recommendation_reason": f"与「{pid_to_title.get(pid, '未知')[:20]}」高度相关"
                    + (f"，被引用 {citation_count.get(other_pid, 0)} 次" if citation_count.get(other_pid, 0) > 0 else ""),
            })

    # Sort by similarity score and deduplicate
    seen = set()
    unique = []
    for rec in sorted(recommendations, key=lambda x: x["similarity_score"], reverse=True):
        key = (rec["source_paper_id"], rec["recommended_paper_id"])
        if key not in seen:
            seen.add(key)
            unique.append(rec)

    return unique[:top_k * len(papers)]


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
                recommendations.append({
                    "source_paper_id": paper["id"],
                    "source_paper_title": pid_to_title.get(paper["id"], ""),
                    "recommended_paper_id": other_pid,
                    "recommended_paper_title": r.get("paper_title", ""),
                    "recommended_paper_authors": pid_to_authors.get(other_pid, ""),
                    "recommended_paper_year": pid_to_year.get(other_pid, ""),
                    "similarity_score": round(1.0 / (1.0 + r.get("distance", 1.0)), 3),
                    "recommendation_reason": f"基于检索相似性推荐",
                })

    return recommendations[:top_k * len(papers)]
