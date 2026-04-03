"""PDF 解析与层级切片模块"""
import re
import os
import json
import uuid
import logging
from pathlib import Path
from typing import Optional

import pdfplumber
from PyPDF2 import PdfReader

from config.settings import PAPERS_DIR, CHUNK_MIN_SIZE, CHUNK_MAX_SIZE

logger = logging.getLogger(__name__)


def parse_pdf(pdf_path: str) -> dict:
    """解析 PDF，提取元数据、文本、表格信息"""
    filename = os.path.basename(pdf_path)
    paper_id = f"paper_{uuid.uuid4().hex[:8]}"

    # 提取元数据
    metadata = {"paper_id": paper_id, "filename": filename}
    try:
        reader = PdfReader(pdf_path)
        info = reader.metadata
        if info:
            metadata["title"] = info.title or ""
            metadata["authors"] = info.author or ""
        metadata["page_count"] = len(reader.pages)
    except Exception as e:
        logger.warning(f"元数据提取失败: {e}")
        metadata["page_count"] = 0

    # 用文件名解析标题、作者和年份（文件名格式: "Author 等 - 2025 - Title.pdf"）
    if not metadata.get("title") or not metadata.get("authors") or not metadata.get("year"):
        _parse_from_filename(filename, metadata)

    # 提取文本和表格
    sections = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            current_section = {"title": "全文", "text": "", "tables": []}
            # 章节标题模式：匹配 "1. Introduction", "2.1 Methods" 等
            section_pattern = re.compile(
                r'^(\d+(?:\.\d+)*)\s+([A-Z][^\n]{2,80})'
            )

            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                if not text.strip():
                    continue

                # 提取表格
                tables = page.extract_tables()
                for table in tables:
                    if table and len(table) > 1:
                        table_md = _table_to_markdown(table)
                        current_section["tables"].append({
                            "page": i + 1,
                            "content": table_md
                        })

                # 逐行检测章节标题
                lines = text.split('\n')
                buffer_lines = []
                for line in lines:
                    stripped = line.strip()
                    match = section_pattern.match(stripped)
                    if match and len(stripped) < 80:
                        # 找到新章节标题，先保存之前的内容
                        if buffer_lines:
                            current_section["text"] += "\n" + "\n".join(buffer_lines)
                            buffer_lines = []
                        if current_section["text"].strip():
                            sections.append(current_section.copy())
                        current_section = {
                            "title": f"{match.group(1)} {match.group(2).strip()}",
                            "text": "",
                            "tables": []
                        }
                    else:
                        buffer_lines.append(line)

                # 把剩余行加入当前 section
                if buffer_lines:
                    current_section["text"] += "\n" + "\n".join(buffer_lines)

            # 保存最后一节
            if current_section["text"].strip():
                sections.append(current_section)

    except Exception as e:
        logger.error(f"PDF 文本提取失败: {e}")
        return {**metadata, "sections": [], "raw_text": "", "error": str(e)}

    # 如果没有检测到章节，整篇作为一节
    if not sections:
        all_text = ""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    all_text += (page.extract_text() or "") + "\n"
        except:
            pass
        sections = [{"title": "全文", "text": all_text, "tables": []}]

    return {
        **metadata,
        "sections": sections,
        "raw_text": "\n".join(s["text"] for s in sections),
    }


def chunk_paper(paper_data: dict) -> list[dict]:
    """将论文按层级切片"""
    paper_id = paper_data["paper_id"]
    chunks = []

    # L0: 论文级（元数据摘要）
    abstract = _extract_abstract(paper_data["raw_text"])
    chunks.append({
        "chunk_id": f"{paper_id}_L0_abstract",
        "paper_id": paper_id,
        "paper_title": paper_data.get("title", "Unknown"),
        "authors": paper_data.get("authors", "Unknown"),
        "year": paper_data.get("year", 0),
        "section_title": "摘要",
        "section_level": "L0",
        "text": abstract,
        "has_figure": False,
        "has_table": False,
    })

    # L1/L2: 章节级和段落级
    for section in paper_data["sections"]:
        text = section["text"].strip()
        if not text:
            continue

        section_title = section["title"]
        has_table = len(section.get("tables", [])) > 0

        # 如果章节文本短，直接作为一个 chunk
        if len(text) <= CHUNK_MAX_SIZE:
            chunks.append({
                "chunk_id": f"{paper_id}_L1_{uuid.uuid4().hex[:6]}",
                "paper_id": paper_id,
                "paper_title": paper_data.get("title", "Unknown"),
                "authors": paper_data.get("authors", "Unknown"),
                "year": paper_data.get("year", 0),
                "section_title": section_title,
                "section_level": "L1",
                "text": text,
                "has_figure": False,
                "has_table": has_table,
            })
        else:
            # 按段落分割
            paragraphs = _split_paragraphs(text)
            for para in paragraphs:
                if len(para.strip()) < CHUNK_MIN_SIZE:
                    continue
                chunks.append({
                    "chunk_id": f"{paper_id}_L2_{uuid.uuid4().hex[:6]}",
                    "paper_id": paper_id,
                    "paper_title": paper_data.get("title", "Unknown"),
                    "authors": paper_data.get("authors", "Unknown"),
                    "year": paper_data.get("year", 0),
                    "section_title": section_title,
                    "section_level": "L2",
                    "text": para.strip()[:CHUNK_MAX_SIZE],
                    "has_figure": False,
                    "has_table": has_table,
                })

    # 添加表格作为独立 chunk
    for section in paper_data["sections"]:
        for table in section.get("tables", []):
            chunks.append({
                "chunk_id": f"{paper_id}_tbl_{uuid.uuid4().hex[:6]}",
                "paper_id": paper_id,
                "paper_title": paper_data.get("title", "Unknown"),
                "authors": paper_data.get("authors", "Unknown"),
                "year": paper_data.get("year", 0),
                "section_title": f"{section['title']} - 表格",
                "section_level": "L2",
                "text": table["content"],
                "has_figure": False,
                "has_table": True,
            })

    return chunks


def _parse_from_filename(filename: str, metadata: dict):
    """从文件名解析作者和标题"""
    name = filename.replace(".pdf", "")
    # 格式: "Author 等 - 2025 - Title" 或 "Author - 2025 - Title"
    parts = name.split(" - ")
    if len(parts) >= 3:
        metadata["authors"] = parts[0].strip()
        try:
            metadata["year"] = int(parts[1].strip())
        except ValueError:
            metadata["year"] = 0
        metadata["title"] = parts[2].strip()
    elif len(parts) == 2:
        metadata["authors"] = parts[0].strip()
        metadata["title"] = parts[1].strip()
    else:
        metadata["title"] = name


def _extract_abstract(text: str) -> str:
    """提取摘要"""
    # 尝试匹配 Abstract 部分
    patterns = [
        r'(?:Abstract|ABSTRACT|摘要)[\s\n]*(.*?)(?:\n\s*\n|Introduction|INTRODUCTION|1\.|Keywords)',
        r'(?:Abstract|ABSTRACT)[\s\n:]*(.*?)(?:\n\n|\x0c)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            abstract = match.group(1).strip()
            if len(abstract) > 100:
                return abstract[:2000]
    # 回退：取前 1500 字符
    return text[:1500] if text else ""


def _table_to_markdown(table: list) -> str:
    """将表格转为 Markdown 文本"""
    if not table or len(table) < 2:
        return ""
    header = "| " + " | ".join(str(c or "") for c in table[0]) + " |"
    separator = "| " + " | ".join("---" for _ in table[0]) + " |"
    rows = []
    for row in table[1:]:
        rows.append("| " + " | ".join(str(c or "") for c in row) + " |")
    return header + "\n" + separator + "\n" + "\n".join(rows)


def _split_paragraphs(text: str) -> list[str]:
    """按段落分割文本"""
    # 按双换行分段
    paragraphs = re.split(r'\n\s*\n', text)
    # 合并过短的段落
    result = []
    buffer = ""
    for para in paragraphs:
        buffer += para + "\n"
        if len(buffer.strip()) >= CHUNK_MIN_SIZE:
            result.append(buffer.strip())
            buffer = ""
    if buffer.strip():
        if result and len(buffer.strip()) < CHUNK_MIN_SIZE:
            result[-1] += "\n" + buffer.strip()
        else:
            result.append(buffer.strip())
    return result
