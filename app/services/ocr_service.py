from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Any

from app.clients.feishu_client import FeishuAPIError, FeishuClient
from app.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """
    OCR 服务层（可替换设计）。

    统一输出格式：
    {
      "full_text": "完整识别文本",
      "lines": ["逐行文本1", "逐行文本2"]
    }
    """

    def __init__(self, feishu_client: FeishuClient | None = None) -> None:
        self.feishu_client = feishu_client or FeishuClient()

    async def recognize(self, image_ref: str | None, *, use_mock: bool = True) -> dict[str, Any]:
        if not image_ref:
            logger.warning("OCR skipped: empty image_ref")
            return self._build_result("")

        try:
            if use_mock:
                return await self.mock_ocr(image_ref)
            return await self.basic_recognize(image_ref)
        except Exception as exc:
            logger.exception("OCR failed for image_ref=%s, error=%s", image_ref, str(exc))
            return self._build_result("")

    async def mock_ocr(self, image_ref: str) -> dict[str, Any]:
        logger.info("[MOCK OCR] start, image_ref=%s", image_ref)
        mock_text = (
            "截止 2026.04.23 至 2026.04.23\n"
            "门店：示例门店X店\n"
            "营业金额(元)：100\n"
            "门店：示例门店X\n"
            "营业金额(元)：50\n"
            "门店：示例门店Y店\n"
            "营业金额(元)：80"
        )
        result = self._build_result(mock_text)
        logger.info("[MOCK OCR] done, lines=%s", len(result["lines"]))
        return result

    async def basic_recognize(self, image_ref: str) -> dict[str, Any]:
        logger.info("[FEISHU OCR] basic_recognize start, image_ref=%s", image_ref)
        raise RuntimeError(
            "basic_recognize(image_ref) is not supported directly. "
            "Use recognize_from_message_image(message_id, image_key) for Feishu image events."
        )

    async def recognize_from_message_image(self, *, message_id: str, image_key: str) -> dict[str, Any]:
        image_bytes = await self.feishu_client.download_message_image(message_id=message_id, image_key=image_key)

        max_attempts = 3
        last_exc: FeishuAPIError | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self.feishu_client.ocr_basic_recognize(image_bytes=image_bytes)
            except FeishuAPIError as exc:
                last_exc = exc
                if exc.code == 99991400 and attempt < max_attempts:
                    backoff = 2 ** (attempt - 1)
                    logger.warning(
                        "OCR rate limited, retrying: attempt=%s/%s sleep=%ss log_id=%s",
                        attempt,
                        max_attempts,
                        backoff,
                        exc.log_id,
                    )
                    await asyncio.sleep(backoff)
                    continue
                break

        if self._should_use_local_fallback(last_exc):
            logger.warning(
                "use local OCR fallback provider=%s code=%s log_id=%s",
                settings.local_ocr_provider,
                getattr(last_exc, "code", None),
                getattr(last_exc, "log_id", None),
            )
            return await self._local_ocr_fallback(image_bytes)

        if last_exc:
            raise last_exc
        return self._build_result("")

    def _should_use_local_fallback(self, err: FeishuAPIError | None) -> bool:
        if not settings.use_local_ocr_fallback:
            return False
        if err is None:
            return False
        if settings.local_ocr_fallback_on_any_feishu_ocr_error:
            return True
        return err.code == 99991400

    async def _local_ocr_fallback(self, image_bytes: bytes) -> dict[str, Any]:
        provider = settings.local_ocr_provider.strip().lower()
        if provider != "rapidocr":
            raise RuntimeError(f"unsupported local OCR provider: {provider}")
        return await self._local_ocr_with_rapidocr(image_bytes)

    async def _local_ocr_with_rapidocr(self, image_bytes: bytes) -> dict[str, Any]:
        try:
            from rapidocr_onnxruntime import RapidOCR  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "local OCR fallback requires rapidocr_onnxruntime. "
                "Please install: pip install rapidocr_onnxruntime"
            ) from exc

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            result, _ = await asyncio.to_thread(RapidOCR(), tmp_path)
            lines: list[str] = []
            if isinstance(result, list):
                for item in result:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        text = item[1]
                        if isinstance(text, str) and text.strip():
                            lines.append(text.strip())
            logger.info("[LOCAL OCR] rapidocr done, lines=%s", len(lines))
            return {"full_text": "\n".join(lines), "lines": lines}
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:
                pass

    def _build_result(self, full_text: str) -> dict[str, Any]:
        lines = [line.strip() for line in full_text.splitlines() if line.strip()]
        return {"full_text": full_text, "lines": lines}

    def _build_result_from_lines(self, lines: list[str]) -> dict[str, Any]:
        normalized_lines = [line.strip() for line in lines if line and line.strip()]
        return {"full_text": "\n".join(normalized_lines), "lines": normalized_lines}
