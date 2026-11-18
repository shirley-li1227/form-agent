"""LangChain RAG 检索模块（带向量索引缓存）。

- 从 RAG_DOC_DIR 加载规范文档，切分为 chunk。
- 有密钥时：一次性把全部 chunk 做 embedding，结果归一化后缓存到磁盘（npz）。
  之后每次检索只做一次 query embedding + 一次矩阵乘法，避免重复嵌入。
  缓存签名 = chunk 内容 + embedding 模型 + base_url，任一变化自动重建。
- 无密钥 / 依赖缺失 / 调用失败时回退关键词重叠打分。
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from app.config import Settings, get_settings


DEFAULT_SPEC = (
    "手机号字段类型为 tel、必填、11位数字；姓名为 text、必填；"
    "邮箱为 email；地址为 textarea；城市为 select；字段标识使用蛇形命名。"
)


class Retriever:
    def __init__(self, settings: Optional[Settings] = None) -> None:
        self.settings = settings or get_settings()
        self.chunks: list[str] = self._load_documents()
        self._embeddings = None
        self._matrix: Optional[np.ndarray] = None
        self._mode = "keyword"
        self._cache_path = Path(self.settings.rag_cache_path)
        self._init_embeddings()

    # ---------- 初始化 ----------

    def _init_embeddings(self) -> None:
        if not self.settings.openai_api_key:
            return
        try:
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
                model=self.settings.embedding_model,
            )
        except Exception:
            self._embeddings = None

    def _load_documents(self) -> list[str]:
        doc_dir = Path(self.settings.rag_doc_dir)
        chunks: list[str] = []
        if doc_dir.exists():
            for file in doc_dir.rglob("*"):
                if file.suffix.lower() in {".md", ".txt"}:
                    text = file.read_text(encoding="utf-8", errors="ignore")
                    # 按二级标题/空行简单切分
                    for block in re.split(r"\n##? ", text):
                        block = block.strip()
                        if block:
                            chunks.append(block)
        return chunks or [DEFAULT_SPEC]

    # ---------- 索引 ----------

    @property
    def mode(self) -> str:
        """当前检索模式：vector（向量索引） / keyword（关键词兜底）。"""
        return self._mode

    @property
    def index_size(self) -> Optional[int]:
        return None if self._matrix is None else int(self._matrix.shape[0])

    @property
    def cache_path(self) -> str:
        return str(self._cache_path)

    def _signature(self) -> str:
        payload = json.dumps(
            {
                "chunks": self.chunks,
                "model": self.settings.embedding_model,
                "base_url": self.settings.openai_base_url,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]

    def _load_cache(self, signature: str) -> Optional[np.ndarray]:
        if not self._cache_path.exists():
            return None
        try:
            data = np.load(self._cache_path, allow_pickle=False)
            if str(data["signature"]) != signature:
                return None
            matrix = data["vectors"]
            if matrix.ndim != 2 or matrix.shape[0] != len(self.chunks):
                return None
            return matrix.astype("float32")
        except Exception:
            return None

    def _save_cache(self, signature: str, matrix: np.ndarray) -> None:
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez(
                self._cache_path,
                vectors=matrix,
                signature=np.array(signature),
            )
        except Exception:
            # 缓存写失败不影响检索，下次重建即可
            pass

    def _ensure_index(self) -> bool:
        """惰性构建向量索引：先读缓存，未命中才真正调用 embedding。"""
        if self._embeddings is None:
            return False
        if self._matrix is not None:
            return True

        signature = self._signature()
        cached = self._load_cache(signature)
        if cached is not None:
            self._matrix = cached
            self._mode = "vector"
            return True

        try:
            vectors = self._embeddings.embed_documents(self.chunks)
            matrix = np.array(vectors, dtype="float32")
            if matrix.ndim != 2 or matrix.shape[0] != len(self.chunks):
                return False
            matrix = self._normalize_rows(matrix)
            self._matrix = matrix
            self._mode = "vector"
            self._save_cache(signature, matrix)
            return True
        except Exception:
            self._matrix = None
            self._mode = "keyword"
            return False

    @staticmethod
    def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-8
        return matrix / norms

    # ---------- 检索 ----------

    def retrieve(self, query: str, k: int = 3) -> str:
        scored = self._score(query)
        top = sorted(scored, key=lambda x: x[1], reverse=True)[:k]
        return "\n".join(chunk for chunk, _ in top)

    def _score(self, query: str) -> list[tuple[str, float]]:
        if self._ensure_index():
            try:
                return self._vector_score(query)
            except Exception:
                # 维度不匹配或接口失败：丢弃缓存，降级关键词检索
                self._matrix = None
                self._mode = "keyword"
                try:
                    self._cache_path.unlink(missing_ok=True)
                except Exception:
                    pass
        return self._keyword_score(query)

    def _keyword_score(self, query: str) -> list[tuple[str, float]]:
        q_tokens = set(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]+", query))
        result: list[tuple[str, float]] = []
        for chunk in self.chunks:
            c_tokens = set(re.findall(r"[\u4e00-\u9fa5a-zA-Z0-9]+", chunk))
            overlap = len(q_tokens & c_tokens)
            result.append((chunk, float(overlap)))
        return result

    def _vector_score(self, query: str) -> list[tuple[str, float]]:
        q_vec = np.array(self._embeddings.embed_query(query), dtype="float32")
        if q_vec.ndim != 1 or self._matrix is None:
            raise ValueError("query embedding 维度异常")
        if q_vec.shape[0] != self._matrix.shape[1]:
            raise ValueError("query 与索引维度不一致")
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-8)
        scores = (self._matrix @ q_vec).tolist()
        return list(zip(self.chunks, scores))
