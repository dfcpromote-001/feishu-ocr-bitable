from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class FeishuMessageService:
    """Mock 飞书消息服务：后续替换成真实发消息接口。"""

    async def reply_text(self, chat_id: str | None, text: str) -> None:
        logger.info("[MOCK FEISHU MESSAGE] chat_id=%s text=%s", chat_id, text)
