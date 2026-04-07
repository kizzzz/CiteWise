"""AgentEval Dashboard — 评估可视化"""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/eval/metrics")
async def get_eval_metrics(project_id: str = None, days: int = 7):
    from src.eval.metrics import get_metrics_summary, generate_optimization_suggestions
    metrics = get_metrics_summary(project_id, days)
    metrics["suggestions"] = generate_optimization_suggestions(metrics)
    return metrics


@router.get("/eval/trends")
async def get_eval_trends(project_id: str = None, days: int = 30):
    from src.eval.metrics import get_daily_trends
    return get_daily_trends(project_id, days)


@router.post("/eval/rate")
async def submit_user_rating(data: dict):
    """Submit user rating for a response"""
    # data: {session_id, rating (1-5)}
    from src.eval.metrics import _EVAL_DB_PATH
    if not _EVAL_DB_PATH:
        return {"status": "error", "message": "Eval DB not initialized"}
    import sqlite3
    conn = sqlite3.connect(_EVAL_DB_PATH)
    conn.execute(
        "UPDATE eval_records SET user_rating=? WHERE session_id=? ORDER BY timestamp DESC LIMIT 1",
        (data.get("rating"), data.get("session_id"))
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}
