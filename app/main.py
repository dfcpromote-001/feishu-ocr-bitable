from fastapi import FastAPI

from app.config import settings
from app.routes.feishu_webhook import router as feishu_router
from app.utils.logger import setup_logger

setup_logger()

app = FastAPI(title=settings.app_name)
app.include_router(feishu_router)


@app.get("/health")
async def health() -> dict:
    return {"ok": True, "env": settings.app_env}
