"""Embedding 和向量库管理（智谱 embedding-3）"""
import json
import uuid
import logging
from typing import Optional

import chromadb
from openai import OpenAI

from config.settings import (
    CHROMA_PATH, OPENAI_API_KEY, OPENAI_BASE_URL,
    EMBEDDING_MODEL
)

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Embedding 管理，使用智谱 embedding-3"""

    def __init__(self):
        self.client = OpenAI(
            api_key=OPENAI_API_KEY,
            base_url=OPENAI_BASE_URL,
        )
        self.model = EMBEDDING_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量生成 embedding"""
        if not texts:
            return []
        import time
        for attempt in range(3):
            try:
                resp = self.client.embeddings.create(
                    model=self.model,
                    input=texts,
                )
                return [item.embedding for item in resp.data]
            except Exception as e:
                logger.error(f"Embedding 生成失败 (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
        return []


class VectorStore:
    """Chroma 向量库管理"""

    def __init__(self):
        self.client = chromadb.PersistentClient(path=CHROMA_PATH)
        self.paper_collection = self.client.get_or_create_collection(
            name="paper_chunks",
            metadata={"hnsw:space": "cosine"}
        )
        self.embedding_manager = EmbeddingManager()

    def index_chunks(self, chunks: list[dict]):
        """将 chunks 索引到向量库"""
        if not chunks:
            return

        texts = [c["text"] for c in chunks]
        ids = [c["chunk_id"] for c in chunks]
        metadatas = [{
            "paper_id": c["paper_id"],
            "paper_title": c.get("paper_title", ""),
            "authors": c.get("authors", ""),
            "year": c.get("year", 0),
            "section_title": c.get("section_title", ""),
            "section_level": c.get("section_level", "L2"),
            "has_table": c.get("has_table", False),
        } for c in chunks]

        # 批量生成 embedding（智谱单次最多64条）
        batch_size = 16
        for i in range(0, len(texts), batch_size):
            batch_texts = texts[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_meta = metadatas[i:i+batch_size]

            embeddings = self.embedding_manager.embed(batch_texts)
            if not embeddings:
                logger.error(f"Embedding 为空，跳过批次 {i}")
                continue

            self.paper_collection.upsert(
                ids=batch_ids,
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_meta,
            )
        logger.info(f"已索引 {len(chunks)} 个 chunks")

    def vector_search(self, query: str, top_k: int = 20, where: dict = None) -> list[dict]:
        """向量检索"""
        query_embedding = self.embedding_manager.embed([query])
        if not query_embedding:
            return []

        # top_k 不能超过库中总数
        count = self.paper_collection.count()
        actual_k = min(top_k, count) if count > 0 else 0
        if actual_k == 0:
            return []

        results = self.paper_collection.query(
            query_embeddings=query_embedding,
            n_results=actual_k,
            where=where,
            include=["documents", "metadatas", "distances"]
        )

        output = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                output.append({
                    "chunk_id": results["ids"][0][i],
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i],
                })
        return output

    def get_all_chunks(self) -> list[dict]:
        """获取所有已索引的 chunks"""
        count = self.paper_collection.count()
        if count == 0:
            return []
        results = self.paper_collection.get(
            include=["documents", "metadatas"],
            limit=count
        )
        output = []
        if results["ids"]:
            for i in range(len(results["ids"])):
                output.append({
                    "chunk_id": results["ids"][i],
                    "text": results["documents"][i],
                    "metadata": results["metadatas"][i],
                })
        return output

    def get_chunks_by_paper(self, paper_id: str) -> list[dict]:
        """获取某篇论文的所有 chunks（按 section_level 和 section_title 排序）"""
        try:
            results = self.paper_collection.get(
                where={"paper_id": paper_id},
                include=["documents", "metadatas"],
            )
        except Exception as e:
            logger.error(f"获取论文 chunks 失败: {e}")
            return []

        output = []
        if results["ids"]:
            for i in range(len(results["ids"])):
                meta = results["metadatas"][i] if results["metadatas"] else {}
                output.append({
                    "chunk_id": results["ids"][i],
                    "text": results["documents"][i],
                    "section_title": meta.get("section_title", ""),
                    "section_level": meta.get("section_level", "L2"),
                    "has_table": meta.get("has_table", False),
                })
        # Sort: L0 first (abstract), then L1, then L2
        level_order = {"L0": 0, "L1": 1, "L2": 2}
        output.sort(key=lambda c: level_order.get(c["section_level"], 2))
        return output

    def delete_paper(self, paper_id: str):
        """删除某篇论文的所有 chunks"""
        self.paper_collection.delete(
            where={"paper_id": paper_id}
        )

    def get_stats(self) -> dict:
        """获取向量库统计"""
        count = self.paper_collection.count()
        return {"total_chunks": count}


# 全局单例
vector_store = VectorStore()
embedding_manager = EmbeddingManager()
