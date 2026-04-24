from __future__ import annotations

import asyncio
import logging
import threading
import time

import lark_oapi as lark

import app.config as app_config
from app.clients.feishu_client import FeishuClient
from app.config.env_setup import ensure_env_interactive
from app.models.schemas import RevenueImportResult
from app.services.message_image_extractor import extract_image_keys_from_message_content

logging.basicConfig(
    level=getattr(logging, app_config.settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

service = None
message_client = FeishuClient()
_DEDUP_TTL_SECONDS = 600
_seen_messages: dict[str, float] = {}
_processing_messages: set[str] = set()
_dedup_lock = threading.Lock()


async def _reply_text(message_id: str, text: str) -> None:
    try:
        await message_client.reply_text_message(message_id=message_id, text=text)
    except Exception as exc:
        logger.warning("reply message failed: message_id=%s error=%s", message_id, exc)


def _build_result_reply(result: RevenueImportResult) -> str:
    created_count = sum(1 for item in result.store_results if item.get("action") == "created")
    updated_count = sum(1 for item in result.store_results if item.get("action") == "updated")
    skipped_count = sum(1 for item in result.store_results if item.get("action") == "skipped")

    lines = [
        "处理完成",
        f"成功：{result.success_store_count} 家",
        f"失败：{result.failed_store_count} 家",
    ]
    if created_count or updated_count or skipped_count:
        lines.append(f"新增：{created_count}，更新：{updated_count}，跳过：{skipped_count}")
    if result.errors:
        lines.append("错误：" + "；".join(result.errors[:3]))
    return "\n".join(lines)


def _run_import(message_id: str, image_key: str) -> None:
    async def _task() -> None:
        if service is None:
            logger.error("import service is not initialized")
            return

        try:
            await _reply_text(message_id, "收到截图，开始识别并写入多维表。")
            result = await service.import_from_feishu_message(
                message_id=message_id,
                image_key=image_key,
                use_mock_ocr=app_config.settings.use_mock_ocr,
            )
            logger.info(
                "import finished: success=%s failed=%s records=%s errors=%s",
                result.success_store_count,
                result.failed_store_count,
                len(result.upserted_record_ids),
                result.errors,
            )
            await _reply_text(message_id, _build_result_reply(result))
        except Exception as exc:
            logger.exception("import task failed: message_id=%s error=%s", message_id, exc)
            await _reply_text(message_id, f"处理失败：{exc}")
        finally:
            with _dedup_lock:
                _processing_messages.discard(message_id)
                _seen_messages[message_id] = time.time()

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_task())
    except RuntimeError:
        asyncio.run(_task())


def handle_message(data: lark.im.v1.P2ImMessageReceiveV1) -> None:
    try:
        message = data.event.message
        image_keys = extract_image_keys_from_message_content(message.message_type, message.content)
        if not image_keys:
            logger.info(
                "ignore message without supported image: message_id=%s type=%s",
                message.message_id,
                message.message_type,
            )
            return

        if _should_skip_message(message.message_id):
            logger.info("skip duplicated message: message_id=%s", message.message_id)
            return

        image_key = image_keys[0]
        if len(image_keys) > 1:
            logger.info(
                "message contains multiple images, only first image will be imported: message_id=%s count=%s",
                message.message_id,
                len(image_keys),
            )

        logger.info(
            "receive image message: message_id=%s type=%s image_key=%s",
            message.message_id,
            message.message_type,
            image_key,
        )
        _run_import(message.message_id, image_key)
    except Exception as exc:
        logger.exception("handle message failed: %s", str(exc))


def _should_skip_message(message_id: str) -> bool:
    now = time.time()
    with _dedup_lock:
        expired = [mid for mid, ts in _seen_messages.items() if now - ts > _DEDUP_TTL_SECONDS]
        for mid in expired:
            _seen_messages.pop(mid, None)

        if message_id in _processing_messages:
            return True
        if message_id in _seen_messages:
            return True

        _processing_messages.add(message_id)
        return False


def main() -> None:
    global service

    env_updated = ensure_env_interactive()
    if env_updated:
        app_config.reload_settings()

    from app.services.revenue_import_service import RevenueImportService

    service = RevenueImportService()

    logger.info("start feishu long connection client")
    logger.info(
        "app_id=%s use_mock_ocr=%s use_mock_bitable=%s",
        app_config.settings.feishu_app_id,
        app_config.settings.use_mock_ocr,
        app_config.settings.use_mock_bitable,
    )

    event_handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(handle_message)
        .build()
    )

    client = lark.ws.Client(
        app_config.settings.feishu_app_id,
        app_config.settings.feishu_app_secret,
        event_handler=event_handler,
        log_level=lark.LogLevel.DEBUG,
    )
    client.start()


if __name__ == "__main__":
    main()
