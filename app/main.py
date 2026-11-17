"""FastAPI 入口。

启动：uvicorn app.main:app --reload
"""

from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings

app = FastAPI(title="低代码表单生成 Agent", version="1.0.0")
app.include_router(router)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "model": settings.model_name,
        "llm_configured": bool(settings.openai_api_key),
        "max_retry": settings.max_retry,
    }
