from fastapi import APIRouter, Request

from app.services.webhook_service import WebhookService

router = APIRouter(prefix="/webhook", tags=["webhook"])
service = WebhookService()


@router.post("/feishu")
async def feishu_webhook(request: Request) -> dict:
    payload = await request.json()
    return await service.handle(payload)
