"""LangChain RAG 检索模块。

- 从 RAG_DOC_DIR 加载规范文档，切分为 chunk。
- 优先使用 OpenAI Embeddings 做向量检索；无密钥/依赖时回退到关键词重叠打分。
- 文档目录为空时，使用内置默认规范兜底。
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

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
        self._init_embeddings()

    def _init_embeddings(self) -> None:
        if not self.settings.openai_api_key:
            return
        try:
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(
                api_key=self.settings.openai_api_key,
                base_url=self.settings.openai_base_url,
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

    # ---------- 检索 ----------

    def retrieve(self, query: str, k: int = 3) -> str:
        scored = self._score(query)
        top = sorted(scored, key=lambda x: x[1], reverse=True)[:k]
        return "\n".join(chunk for chunk, _ in top)

    def _score(self, query: str) -> list[tuple[str, float]]:
        if self._embeddings is not None:
            return self._vector_score(query)
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
        import numpy as np

        q_vec = np.array(self._embeddings.embed_query(query))
        result: list[tuple[str, float]] = []
        for chunk in self.chunks:
            c_vec = np.array(self._embeddings.embed_documents([chunk])[0])
            cos = float(q_vec @ c_vec / (np.linalg.norm(q_vec) * np.linalg.norm(c_vec) + 1e-8))
            result.append((chunk, cos))
        return result
