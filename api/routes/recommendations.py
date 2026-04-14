"""文献推荐路由"""
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/recommendations")
async def get_recommendations(project_id: str, top_k: int = 5):
    """获取文献推荐"""
    from src.core.recommender import get_recommendations

    try:
        recs = get_recommendations(project_id, top_k=top_k)
        return {"recommendations": recs, "total": len(recs)}
    except Exception as e:
        logger.error(f"Recommendation failed: {e}", exc_info=True)
        return {"recommendations": [], "total": 0, "error": str(e)}
