"""章节管理路由"""
import asyncio
import logging
import re

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import PlainTextResponse

from api.deps import require_auth
from api.schemas import SectionCreate, SectionUpdate

logger = logging.getLogger(__name__)
router = APIRouter()

# Valid section ID pattern: sec_ followed by hex characters
SECTION_ID_PATTERN = re.compile(r'^sec_[0-9a-f]+$')


@router.get("/sections")
async def list_sections(project_id: str, user: dict = Depends(require_auth)):
    from src.core.memory import project_memory
    return project_memory.get_unique_sections(project_id)


@router.post("/sections")
async def create_section(req: SectionCreate, user: dict = Depends(require_auth)):
    from src.core.agents.coordinator import coordinator
    from src.core.memory import project_memory

    if not req.name or not req.name.strip():
        raise HTTPException(status_code=422, detail="Section name must not be empty")

    try:
        result = await asyncio.to_thread(
            coordinator.process,
            f"帮我写{req.name}", req.project_id,
            section_name=req.name,
            gen_params={
                "style": req.style,
                "target_length": req.target_length,
                "citation_density": req.citation_density,
            },
        )

        # 保存到数据库
        content = result.get("content", "")
        citations = result.get("citations", [])
        project_memory.save_section(req.project_id, req.name, content, citations)

        return {
            "section_name": req.name,
            "content": content,
            "type": result.get("type", "section"),
            "citations": citations,
            "sources": result.get("sources"),
            "thinking_steps": result.get("thinking_steps", []),
        }
    except Exception as e:
        logger.error(f"Section creation error: {e}", exc_info=True)
        return {"content": "生成章节内容失败，请稍后重试", "type": "error"}


@router.put("/sections/{section_id}")
async def update_section(section_id: str, req: SectionUpdate, user: dict = Depends(require_auth)):
    if not SECTION_ID_PATTERN.match(section_id):
        raise HTTPException(status_code=400, detail="Invalid section ID format")
    from src.core.memory import project_memory
    project_memory.update_section_by_id(section_id, req.content)
    return {"status": "ok"}


@router.delete("/sections/{section_id}")
async def delete_section(section_id: str, user: dict = Depends(require_auth)):
    if not SECTION_ID_PATTERN.match(section_id):
        raise HTTPException(status_code=400, detail="Invalid section ID format")
    from src.core.memory import project_memory
    project_memory.delete_section(section_id)
    return {"status": "ok"}


@router.get("/sections/export")
async def export_document(project_id: str, user: dict = Depends(require_auth)):
    """导出所有章节为 Markdown 文档"""
    from src.core.memory import project_memory

    sections = project_memory.get_unique_sections(project_id)
    proj = project_memory.get_project(project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    doc = f"# {proj['name']}\n\n"
    for s in sections:
        doc += f"## {s['section_name']}\n\n{s['content']}\n\n---\n\n"

    filename = proj["name"].replace(" ", "_")
    return PlainTextResponse(
        content=doc,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename={filename}.md"},
    )
