from __future__ import annotations

import json
import logging
from typing import Any

from app.clients.feishu_client import FeishuClient
from app.core.config import settings
from app.models.schemas import ExtractedFields
from app.services.bitable_service import BitableService
from app.services.field_extractor import FieldExtractor
from app.services.ocr_service import OCRService
from app.utils.errors import AppError

logger = logging.getLogger(__name__)


class WebhookService:
    def __init__(self) -> None:
        self.feishu_client = FeishuClient()
        self.ocr_service = OCRService(self.feishu_client)
        self.extractor = FieldExtractor()
        self.bitable_service = BitableService(self.feishu_client)

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        # 飞书 URL 校验
        if payload.get("type") == "url_verification":
            self._validate_verification_token(payload)
            return {"challenge": payload.get("challenge")}

        header = payload.get("header", {})
        event_type = header.get("event_type")
        if event_type != "im.message.receive_v1":
            logger.info("Ignore event_type=%s", event_type)
            return {"ok": True, "ignored": True}

        event = payload.get("event", {})
        message = event.get("message", {})
        chat_id = message.get("chat_id")
        message_id = message.get("message_id")
        message_type = message.get("message_type")

        if not chat_id or not message_id:
            raise AppError("消息缺少 chat_id 或 message_id")

        if settings.target_chat_id and chat_id != settings.target_chat_id:
            logger.info("Ignore non-target chat: %s", chat_id)
            return {"ok": True, "ignored": True}

        if message_type != "image":
            logger.info("Ignore non-image message: %s", message_type)
            return {"ok": True, "ignored": True}

        image_key = self._get_image_key(message)
        if not image_key:
            raise AppError("图片消息缺少 image_key")

        logger.info("Start process message_id=%s chat_id=%s", message_id, chat_id)

        image_bytes = await self.feishu_client.download_image(message_id=message_id, file_key=image_key)
        ocr_text = await self.ocr_service.recognize_image_text(image_bytes)
        extracted = self.extractor.extract(ocr_text)

        missing_items = extracted.missing_items()
        if missing_items:
            missing_msg = "字段缺失：" + "、".join(missing_items)
            await self.feishu_client.send_text_to_chat(chat_id, missing_msg)
            logger.info("missing fields, message_id=%s missing=%s", message_id, missing_items)
            return {"ok": True, "missing": missing_items}

        await self.bitable_service.create_record(extracted)
        await self.feishu_client.send_text_to_chat(chat_id, "已录入")

        logger.info("record created successfully, message_id=%s data=%s", message_id, extracted.model_dump())
        return {"ok": True, "recorded": True}

    @staticmethod
    def _get_image_key(message: dict[str, Any]) -> str | None:
        content = message.get("content")
        if not content:
            return None

        try:
            content_obj = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return None

        return content_obj.get("image_key")

    @staticmethod
    def _validate_verification_token(payload: dict[str, Any]) -> None:
        token = payload.get("token")
        if token != settings.feishu_verification_token:
            raise AppError("verification token 校验失败", status_code=401)
