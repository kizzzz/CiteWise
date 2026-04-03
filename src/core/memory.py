"""记忆系统 - 三层架构（全局画像/项目记忆/工作记忆）"""
import json
import os
import sqlite3
import logging
from datetime import datetime
from typing import Optional

from config.settings import DB_PATH, PROFILE_PATH, DATA_DIR

logger = logging.getLogger(__name__)


class GlobalProfile:
    """Layer 1: 全局用户画像"""

    def __init__(self):
        self.path = PROFILE_PATH
        self.data = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        return self._default()

    def _default(self) -> dict:
        return {
            "user_id": "user_001",
            "research_field": "",
            "focus_areas": [],
            "field_preferences": [],
            "field_templates": [],
            "writing_style": "academic_formal",
            "projects_history": [],
        }

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    def update(self, key: str, value):
        """更新画像字段"""
        self.data[key] = value
        self.save()

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def add_field_template(self, name: str, fields: list[str]):
        """添加字段模板"""
        template = {
            "name": name,
            "fields": fields,
            "usage_count": 1,
            "last_used": datetime.now().isoformat(),
        }
        self.data.setdefault("field_templates", []).append(template)
        self.save()

    def get_reusable_assets(self) -> dict:
        """获取可跨项目复用的资产"""
        templates = self.data.get("field_templates", [])
        last_template = templates[-1] if templates else None
        return {
            "default_template": last_template,
            "writing_style": self.data.get("writing_style", "academic_formal"),
            "research_field": self.data.get("research_field", ""),
        }


class ProjectMemory:
    """Layer 2: 项目记忆（SQLite）"""

    def __init__(self):
        self.db_path = DB_PATH
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                topic TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                config TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS papers (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                title TEXT,
                authors TEXT,
                year INTEGER,
                filename TEXT,
                chunk_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                indexed_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS extractions (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                paper_id TEXT,
                template_name TEXT,
                fields TEXT DEFAULT '{}',
                confidence TEXT DEFAULT '{}',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS generated_sections (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                section_name TEXT,
                content TEXT,
                word_count INTEGER DEFAULT 0,
                citations TEXT DEFAULT '[]',
                generated_at TEXT DEFAULT (datetime('now'))
            );
        """)
        conn.commit()
        conn.close()

    # --- 项目管理 ---
    def create_project(self, name: str, topic: str = "") -> str:
        import uuid
        pid = f"proj_{uuid.uuid4().hex[:8]}"
        conn = self._get_conn()
        conn.execute("INSERT INTO projects (id, name, topic) VALUES (?, ?, ?)",
                     (pid, name, topic))
        conn.commit()
        conn.close()
        return pid

    def get_project(self, project_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def list_projects(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # --- 论文管理 ---
    def add_paper(self, paper_id: str, project_id: str, title: str,
                  authors: str, year: int, filename: str, chunk_count: int = 0):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO papers (id, project_id, title, authors, year, filename, chunk_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paper_id, project_id, title, authors, year, filename, chunk_count)
        )
        conn.commit()
        conn.close()

    def get_papers(self, project_id: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute("SELECT * FROM papers WHERE project_id=?", (project_id,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_paper_count(self, project_id: str) -> int:
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) as cnt FROM papers WHERE project_id=?",
                           (project_id,)).fetchone()
        conn.close()
        return row["cnt"] if row else 0

    # --- 提取结果 ---
    def save_extraction(self, project_id: str, paper_id: str,
                        template_name: str, fields: dict, confidence: dict):
        import uuid
        eid = f"ext_{uuid.uuid4().hex[:8]}"
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO extractions (id, project_id, paper_id, template_name, fields, confidence) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (eid, project_id, paper_id, template_name,
             json.dumps(fields, ensure_ascii=False),
             json.dumps(confidence, ensure_ascii=False))
        )
        conn.commit()
        conn.close()

    def get_extractions(self, project_id: str) -> list[dict]:
        conn = self._get_conn()
        # 每篇论文只取最新一次提取，避免重复计数
        rows = conn.execute(
            "SELECT e.* FROM extractions e "
            "INNER JOIN (SELECT paper_id, MAX(created_at) as latest FROM extractions WHERE project_id=? GROUP BY paper_id) sub "
            "ON e.paper_id = sub.paper_id AND e.created_at = sub.latest "
            "WHERE e.project_id=?",
            (project_id, project_id)
        ).fetchall()
        conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["fields"] = json.loads(d["fields"]) if d["fields"] else {}
            d["confidence"] = json.loads(d["confidence"]) if d["confidence"] else {}
            results.append(d)
        return results

    # --- 生成记录 ---
    def save_section(self, project_id: str, section_name: str,
                     content: str, citations: list = None):
        import uuid
        sid = f"sec_{uuid.uuid4().hex[:8]}"
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO generated_sections (id, project_id, section_name, content, word_count, citations) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (sid, project_id, section_name, content, len(content),
             json.dumps(citations or [], ensure_ascii=False))
        )
        conn.commit()
        conn.close()

    def get_sections(self, project_id: str) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM generated_sections WHERE project_id=? ORDER BY generated_at",
            (project_id,)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def delete_section(self, section_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM generated_sections WHERE id=?", (section_id,))
        conn.commit()
        conn.close()

    def get_unique_sections(self, project_id: str) -> list[dict]:
        """获取去重后的章节（同名只保留最新）"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT s.* FROM generated_sections s "
            "INNER JOIN (SELECT section_name, MAX(generated_at) as latest FROM generated_sections WHERE project_id=? GROUP BY section_name) sub "
            "ON s.section_name = sub.section_name AND s.generated_at = sub.latest "
            "WHERE s.project_id=? ORDER BY s.generated_at",
            (project_id, project_id)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_project_state(self, project_id: str) -> dict:
        """获取项目完整状态"""
        project = self.get_project(project_id)
        if not project:
            return {}
        papers = self.get_papers(project_id)
        extractions = self.get_extractions(project_id)
        unique_sections = self.get_unique_sections(project_id)

        return {
            "name": project["name"],
            "topic": project.get("topic", ""),
            "paper_count": len(papers),
            "papers": papers,
            "extracted_fields": list(set(
                k for e in extractions for k in (e.get("fields") or {}).keys()
            )),
            "completed_sections": [s["section_name"] for s in unique_sections],
            "section_count": len(unique_sections),
            "sections_with_id": [{"id": s["id"], "name": s["section_name"]} for s in unique_sections],
            "extraction_count": len(extractions),
        }


class WorkingMemory:
    """Layer 3: 工作记忆（会话级，内存）"""

    def __init__(self):
        self.current_project_id: Optional[str] = None
        self.current_task: Optional[str] = None
        self.focus_paper: Optional[str] = None
        self.pending_confirmation: Optional[dict] = None
        self.section_summaries: list[dict] = []  # 滑动窗口摘要
        self.dialogue_history: list[dict] = []
        self.max_summary_tokens: int = 2000

    def add_section_summary(self, section_name: str, summary: str, word_count: int):
        """添加章节摘要到滑动窗口"""
        self.section_summaries.append({
            "section": section_name,
            "summary": summary,
            "word_count": word_count,
        })
        self._compress_if_needed()

    def get_previous_summary(self) -> str:
        """获取前文摘要"""
        if not self.section_summaries:
            return "（这是第一章，无前文）"
        parts = [f"【{s['section']}】{s['summary']}" for s in self.section_summaries]
        return "\n\n".join(parts)

    def _compress_if_needed(self):
        """如果摘要过长，压缩早期摘要"""
        total = sum(len(s["summary"]) for s in self.section_summaries)
        while total > self.max_summary_tokens and len(self.section_summaries) > 1:
            oldest = self.section_summaries[0]
            compressed = oldest["summary"][:200] + "..."
            total -= len(oldest["summary"]) - len(compressed)
            self.section_summaries[0]["summary"] = compressed

    def reset(self):
        """重置工作记忆（新会话）"""
        self.current_task = None
        self.focus_paper = None
        self.pending_confirmation = None
        self.section_summaries = []
        self.dialogue_history = []


# 全局单例
global_profile = GlobalProfile()
project_memory = ProjectMemory()
working_memory = WorkingMemory()
