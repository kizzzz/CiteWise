"""知识地图 API — 文献关系可视化"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/knowledge-map")
async def get_knowledge_map(project_id: str):
    """获取文献关系图数据（节点 + 边）"""
    from src.core.memory import project_memory
    from src.core.recommender import get_paper_embeddings, compute_similarity_matrix, build_citation_graph

    papers = project_memory.get_papers(project_id)
    if not papers:
        return {"nodes": [], "edges": []}

    # Build nodes
    nodes = []
    for p in papers:
        nodes.append({
            "id": p["id"],
            "title": p.get("title", "Untitled"),
            "authors": p.get("authors", ""),
            "year": str(p.get("year", "")),
            "chunk_count": p.get("chunk_count", 0),
            "filename": p.get("filename", ""),
        })

    # Build edges from similarity
    edges = []
    try:
        embeddings = get_paper_embeddings(project_id)
        if embeddings and len(embeddings) >= 2:
            sim_matrix = compute_similarity_matrix(embeddings)
            for pid, similar in sim_matrix.items():
                for other_pid, score in similar:
                    if score >= 0.5:  # Threshold for similarity edge
                        edges.append({
                            "source": pid,
                            "target": other_pid,
                            "type": "similarity",
                            "weight": round(score, 3),
                        })
    except Exception as e:
        logger.warning(f"Similarity edges failed: {e}")

    # Build edges from citations
    try:
        citation_graph = build_citation_graph(project_id)
        for pid, cited_set in citation_graph.items():
            for cited_pid in cited_set:
                edges.append({
                    "source": pid,
                    "target": cited_pid,
                    "type": "citation",
                    "weight": 1.0,
                })
    except Exception as e:
        logger.warning(f"Citation edges failed: {e}")

    return {"nodes": nodes, "edges": edges}
