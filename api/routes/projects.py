"""项目管理路由"""
import logging

from fastapi import APIRouter

from api.schemas import ProjectCreate

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/projects")
async def list_projects():
    from src.core.memory import project_memory
    projects = project_memory.list_projects()
    return projects


@router.post("/projects")
async def create_project(req: ProjectCreate):
    from src.core.memory import project_memory, global_profile
    pid = project_memory.create_project(req.name, req.topic)
    global_profile.update("research_field", req.topic)
    project = project_memory.get_project(pid)
    return project


@router.get("/projects/{project_id}/state")
async def get_project_state(project_id: str):
    from src.core.memory import project_memory
    state = project_memory.get_project_state(project_id)
    return state
