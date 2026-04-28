from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config import settings
from app.models.schemas import FeishuWebhookPayload
from app.services.message_image_extractor import extract_image_keys_from_message_content
from app.services.revenue_import_service import RevenueImportService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["feishu"])
revenue_import_service = RevenueImportService()


def _is_valid_event_signature(request: Request, payload: FeishuWebhookPayload) -> bool:
    """
    扩展点：飞书事件签名校验（当前占位实现）。

    后续可在这里基于请求头和请求体，接入飞书提供的签名算法校验逻辑。
    当前返回 True，表示暂不拦截。
    """
    _ = request
    _ = payload
    return True


async def _send_message_receipt_extension(_: FeishuWebhookPayload) -> None:
    """
    扩展点：消息回执/处理结果回传（当前占位实现）。

    后续可以在这里接入飞书消息回执、群内回复或状态通知逻辑。
    """
    return None


@router.post("/feishu")
async def feishu_webhook(request: Request, payload: FeishuWebhookPayload) -> dict:
    """
    接收飞书 webhook 事件，并在第一期只处理图片消息。

    当前实现：
    1) 处理 url_verification 校验请求；
    2) 处理 im.message.receive_v1 事件；
    3) 仅接收 image 消息，非图片直接返回忽略；
    4) 记录完整事件日志，供后续排障与联调。
    """
    # 扩展点：后续接入飞书事件签名校验
    if not _is_valid_event_signature(request, payload):
        raise HTTPException(status_code=401, detail="invalid event signature")

    # 飞书 URL 校验
    if payload.type == "url_verification":
        if payload.token != settings.feishu_verification_token:
            raise HTTPException(status_code=401, detail="invalid verification token")
        return {"challenge": payload.challenge}

    # 记录收到的事件原始内容（结构化日志）
    logger.info("received feishu event: %s", payload.model_dump_json(exclude_none=True))

    event_type = payload.header.event_type if payload.header else None
    if event_type != "im.message.receive_v1":
        return {"ok": True, "ignored": True, "reason": "unsupported event type"}

    message = payload.event.message if payload.event else None
    if not message:
        raise HTTPException(status_code=400, detail="missing message")

    image_keys = extract_image_keys_from_message_content(message.message_type, message.content)
    if not image_keys:
        return {"ok": True, "ignored": True, "reason": "message without supported image"}

    if not message.message_id:
        raise HTTPException(status_code=400, detail="missing message_id or image_key")
    logger.info(
        "image message accepted: message_id=%s chat_id=%s image_count=%s",
        message.message_id,
        message.chat_id,
        len(image_keys),
    )

    summaries = []
    for image_key in image_keys:
        # 执行营业截图导入（通过配置选择 mock/real OCR）
        import_result = await revenue_import_service.import_from_feishu_message(
            message_id=message.message_id,
            image_key=image_key,
            use_mock_ocr=settings.use_mock_ocr,
        )
        summaries.append({"image_key": image_key, "summary": import_result.model_dump()})

    # 扩展点：后续可基于 import_result 回传飞书消息回执
    await _send_message_receipt_extension(payload)

    return {
        "ok": True,
        "accepted": True,
        "message_type": message.message_type,
        "image_count": len(image_keys),
        "summaries": summaries,
    }
