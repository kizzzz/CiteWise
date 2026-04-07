"""论文管理路由"""
import os
import json
import asyncio
import logging

from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from sse_starlette.sse import EventSourceResponse

from config.settings import PAPERS_DIR

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.get("/papers")
async def list_papers(project_id: str):
    from src.core.memory import project_memory
    return project_memory.get_papers(project_id)


@router.post("/papers/upload")
async def upload_papers(files: list[UploadFile] = File(...), project_id: str = Form(...)):
    """上传论文 — JSON 响应（适合简单前端）"""
    result = await _process_uploads(files, project_id)
    return result


@router.post("/papers/upload/stream")
async def upload_papers_stream(files: list[UploadFile] = File(...), project_id: str = Form(...)):
    """上传论文 — SSE 流式返回进度（适合需要实时进度的前端）"""
    async def progress_generator():
        from src.core.rag import parse_pdf, chunk_paper
        from src.core.memory import project_memory

        total = len(files)
        all_chunks = []
        fig_count = 0
        processed = 0

        yield {"event": "progress", "data": json.dumps({
            "phase": "uploading", "total": total, "current": 0
        }, ensure_ascii=False)}

        for idx, f in enumerate(files):
            safe_name = os.path.basename(f.filename or "unknown.pdf")

            # Validate file extension
            if not safe_name.lower().endswith('.pdf'):
                yield {"event": "warning", "data": json.dumps({
                    "file": safe_name, "error": "仅支持 PDF 文件",
                }, ensure_ascii=False)}
                continue

            # Read content for validation
            content = await f.read()
            if len(content) > MAX_FILE_SIZE:
                yield {"event": "warning", "data": json.dumps({
                    "file": safe_name, "error": "File exceeds 50MB size limit",
                }, ensure_ascii=False)}
                continue

            # Validate PDF magic bytes
            if not content.startswith(b'%PDF-'):
                logger.warning(f"跳过非PDF文件: {safe_name}")
                yield {"event": "warning", "data": json.dumps({
                    "file": safe_name, "error": "无效的 PDF 文件格式",
                }, ensure_ascii=False)}
                continue

            path = os.path.join(PAPERS_DIR, safe_name)
            with open(path, "wb") as fp:
                fp.write(content)

            yield {"event": "progress", "data": json.dumps({
                "phase": "parsing", "file": safe_name,
                "current": idx + 1, "total": total,
            }, ensure_ascii=False)}

            try:
                data = await asyncio.to_thread(parse_pdf, path)
                chunks = await asyncio.to_thread(chunk_paper, data)

                project_memory.add_paper(
                    data["paper_id"], project_id,
                    data.get("title", f.filename), data.get("authors", ""),
                    data.get("year", 0), safe_name, len(chunks)
                )
                all_chunks.extend(chunks)

                for fig in data.get("figures", []):
                    project_memory.add_figure(
                        fig["figure_id"], data["paper_id"], project_id,
                        fig["page"], fig["caption"],
                        fig.get("context_before", ""), fig.get("context_after", ""),
                        fig.get("section_title", ""),
                        fig.get("width", 0), fig.get("height", 0)
                    )
                    fig_count += 1
                processed += 1

                yield {"event": "progress", "data": json.dumps({
                    "phase": "parsed", "file": safe_name,
                    "chunks": len(chunks),
                    "current": idx + 1, "total": total,
                }, ensure_ascii=False)}

            except Exception as e:
                logger.error(f"解析 {safe_name} 失败: {e}")
                yield {"event": "warning", "data": json.dumps({
                    "file": safe_name, "error": "文件解析失败",
                }, ensure_ascii=False)}

        # 索引阶段
        if all_chunks:
            yield {"event": "progress", "data": json.dumps({
                "phase": "indexing", "chunks": len(all_chunks),
            }, ensure_ascii=False)}

            from src.core.embedding import vector_store
            from src.core.retriever import bm25_index

            await asyncio.to_thread(vector_store.index_chunks, all_chunks)
            all_indexed = await asyncio.to_thread(vector_store.get_all_chunks)
            await asyncio.to_thread(bm25_index.build_index, all_indexed)

        yield {"event": "done", "data": json.dumps({
            "message": f"已入库 {processed} 篇论文，{len(all_chunks)} 个片段" +
                       (f"，{fig_count} 张图表" if fig_count else ""),
            "chunks_count": len(all_chunks),
            "papers_count": processed,
        }, ensure_ascii=False)}

    return EventSourceResponse(progress_generator())


async def _process_uploads(files: list[UploadFile], project_id: str) -> dict:
    """处理上传文件的共享逻辑"""
    from src.core.rag import parse_pdf, chunk_paper
    from src.core.embedding import vector_store
    from src.core.retriever import bm25_index
    from src.core.memory import project_memory

    all_chunks = []
    fig_count = 0
    processed = 0

    for f in files:
        safe_name = os.path.basename(f.filename or "unknown.pdf")

        # Validate file extension
        if not safe_name.lower().endswith('.pdf'):
            logger.warning(f"跳过非PDF文件: {safe_name}")
            continue

        # Read content for validation
        file_content = await f.read()
        if len(file_content) > MAX_FILE_SIZE:
            logger.warning(f"跳过超大文件: {safe_name}")
            continue

        # Validate PDF magic bytes
        if not file_content.startswith(b'%PDF-'):
            logger.warning(f"跳过非PDF文件: {safe_name}")
            continue

        path = os.path.join(PAPERS_DIR, safe_name)
        with open(path, "wb") as fp:
            fp.write(file_content)

        try:
            data = await asyncio.to_thread(parse_pdf, path)
            chunks = await asyncio.to_thread(chunk_paper, data)
            project_memory.add_paper(
                data["paper_id"], project_id,
                data.get("title", f.filename), data.get("authors", ""),
                data.get("year", 0), safe_name, len(chunks)
            )
            all_chunks.extend(chunks)

            for fig in data.get("figures", []):
                project_memory.add_figure(
                    fig["figure_id"], data["paper_id"], project_id,
                    fig["page"], fig["caption"],
                    fig.get("context_before", ""), fig.get("context_after", ""),
                    fig.get("section_title", ""),
                    fig.get("width", 0), fig.get("height", 0)
                )
                fig_count += 1
            processed += 1
        except Exception as e:
            logger.error(f"解析 {safe_name} 失败: {e}")

    if all_chunks:
        await asyncio.to_thread(vector_store.index_chunks, all_chunks)
        all_indexed = await asyncio.to_thread(vector_store.get_all_chunks)
        await asyncio.to_thread(bm25_index.build_index, all_indexed)

    return {
        "message": f"已入库 {processed} 篇论文，{len(all_chunks)} 个片段" +
                   (f"，{fig_count} 张图表" if fig_count else ""),
        "chunks_count": len(all_chunks),
        "papers_count": processed,
    }


@router.delete("/papers/{paper_id}")
async def delete_paper(paper_id: str, project_id: str = ""):
    """删除论文及其向量索引"""
    if not project_id:
        raise HTTPException(status_code=400, detail="project_id is required")

    from src.core.memory import project_memory
    from src.core.embedding import vector_store
    from src.core.retriever import bm25_index

    # Verify paper belongs to project
    papers = project_memory.get_papers(project_id)
    if not any(p["id"] == paper_id for p in papers):
        raise HTTPException(status_code=404, detail="Paper not found in project")

    vector_store.delete_paper(paper_id)
    project_memory.delete_paper_cascade(paper_id)

    # 重建 BM25 索引
    all_chunks = await asyncio.to_thread(vector_store.get_all_chunks)
    if all_chunks:
        await asyncio.to_thread(bm25_index.build_index, all_chunks)
    else:
        bm25_index.bm25 = None

    return {"status": "ok", "paper_id": paper_id}


@router.get("/papers/{paper_id}")
async def get_paper_detail(paper_id: str):
    from src.core.memory import project_memory
    from src.core.retriever import hybrid_search

    row = project_memory.get_paper_row(paper_id)
    if not row:
        return {"error": "Paper not found"}

    paper = dict(row)

    # 尝试从向量库获取摘要
    try:
        chunks = await asyncio.to_thread(
            hybrid_search,
            f"{paper.get('title', '')} abstract summary",
            top_k=3, where={"paper_id": paper_id}
        )
        abstract = "\n".join(c.get("text", "") for c in chunks[:2]) if chunks else "暂无摘要"
    except Exception:
        abstract = "暂无摘要"

    paper["abstract"] = abstract
    return paper
