import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置，从环境变量读取。"""

    def __init__(self) -> None:
        self.openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
        self.openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.rag_doc_dir: str = os.getenv("RAG_DOC_DIR", "./data/specs")
        self.embedding_model: str = os.getenv(
            "OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"
        )
        self.rag_cache_path: str = os.getenv(
            "RAG_CACHE_PATH", "./data/cache/rag_index.npz"
        )
        self.max_retry: int = int(os.getenv("MAX_RETRY", "2"))
        self.port: int = int(os.getenv("PORT", "8000"))


@lru_cache
def get_settings() -> Settings:
    return Settings()
