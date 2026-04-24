from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime
from typing import Any

from app.config.store_config import StoreConfigNotFoundError, StoreMeta, get_store_meta
from app.config import settings
from app.models.schemas import RevenueImportResult
from app.services.bitable_service import BitableService, BitableServiceError
from app.services.ocr_service import OCRService
from app.services.parser_service import ParserService

logger = logging.getLogger(__name__)


class RevenueImportService:
    """营业截图导入主流程服务：OCR -> 解析 -> 门店映射 -> upsert -> 月字段重算。"""

    def __init__(
        self,
        ocr_service: OCRService | None = None,
        parser_service: ParserService | None = None,
        bitable_service: BitableService | None = None,
    ) -> None:
        self.ocr_service = ocr_service or OCRService()
        self.parser_service = parser_service or ParserService()
        self.bitable_service = bitable_service or BitableService(use_mock=settings.use_mock_bitable)

    async def import_from_image_ref(self, image_ref: str, *, use_mock_ocr: bool = True) -> RevenueImportResult:
        """
        主入口：接收截图文件引用（URL / file_id / image_key），并执行完整导入流程。

        错误分类：
        - OCR_FAILED: OCR 调用失败或无文本
        - STORE_MAPPING_FAILED: 门店映射失败
        - BITABLE_UPSERT_FAILED: 飞书写入失败
        - MONTHLY_RECOMPUTE_FAILED: 月字段重算失败
        """
        logger.info("revenue import start: image_ref=%s use_mock_ocr=%s", image_ref, use_mock_ocr)

        if not image_ref:
            error = "OCR_FAILED: screenshot reference is empty"
            logger.error(error)
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=1,
                upserted_record_ids=[],
                store_results=[],
                errors=[error],
            )

        try:
            ocr_result = await self.ocr_service.recognize(image_ref=image_ref, use_mock=use_mock_ocr)
            logger.info("ocr done: image_ref=%s lines=%s", image_ref, len(ocr_result.get("lines", [])))
        except Exception as exc:
            error = f"OCR_FAILED: {exc}"
            logger.exception(error)
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=1,
                upserted_record_ids=[],
                store_results=[],
                errors=[error],
            )

        if not ocr_result.get("full_text", "").strip():
            error = "OCR_FAILED: OCR returned empty text"
            logger.error(error)
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=1,
                upserted_record_ids=[],
                store_results=[],
                errors=[error],
            )

        return await self.import_from_ocr_result(ocr_result)

    async def import_from_feishu_message(
        self,
        *,
        message_id: str,
        image_key: str,
        use_mock_ocr: bool,
    ) -> RevenueImportResult:
        """
        从飞书消息图片触发导入。
        - mock 模式：沿用 image_key 走 mock OCR
        - real 模式：下载飞书消息图片并调用真实 OCR
        """
        logger.info(
            "revenue import from feishu message: message_id=%s image_key=%s use_mock_ocr=%s",
            message_id,
            image_key,
            use_mock_ocr,
        )
        if use_mock_ocr:
            return await self.import_from_image_ref(image_ref=image_key, use_mock_ocr=True)

        try:
            ocr_result = await self.ocr_service.recognize_from_message_image(message_id=message_id, image_key=image_key)
        except Exception as exc:
            error = f"OCR_FAILED: {exc}"
            logger.exception(error)
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=1,
                upserted_record_ids=[],
                store_results=[],
                errors=[error],
            )
        return await self.import_from_ocr_result(ocr_result)

    async def import_from_ocr_result(self, ocr_result: dict[str, Any]) -> RevenueImportResult:
        full_text = ocr_result.get("full_text", "")
        logger.info("start parse OCR text length=%s", len(full_text))

        try:
            parsed_records = self.parser_service.parse(full_text)
        except Exception as exc:
            error = f"PARSER_FAILED: {exc}"
            logger.exception(error)
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=1,
                upserted_record_ids=[],
                store_results=[],
                errors=[error],
            )

        if not parsed_records:
            logger.warning(
                "revenue import skipped: parser returned empty records, ocr_text=%r",
                full_text,
            )
            return RevenueImportResult(
                imported_count=0,
                skipped_count=1,
                success_store_count=0,
                failed_store_count=0,
                upserted_record_ids=[],
                store_results=[],
                errors=[],
            )

        # 按 日期+标准门店聚合，确保一条记录=一个门店+一天
        aggregate_amounts: dict[tuple[str, str], float] = defaultdict(float)
        meta_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        store_results: list[dict[str, Any]] = []
        errors: list[str] = []

        for rec in parsed_records:
            date_str = str(rec["date"])
            store_raw = str(rec["store_raw"])
            daily_total = float(rec["daily_total"])

            try:
                store_meta = await self._resolve_store_meta(store_raw)
            except StoreConfigNotFoundError as exc:
                error = f"STORE_MAPPING_FAILED: {exc}"
                logger.error("store mapping failed: date=%s store_raw=%s error=%s", date_str, store_raw, str(exc))
                store_results.append(
                    {
                        "date": date_str,
                        "store_raw": store_raw,
                        "store_name": None,
                        "action": "failed",
                        "success": False,
                        "error": error,
                    }
                )
                errors.append(error)
                continue

            canonical_name = store_meta.store_name
            key = (date_str, canonical_name)
            aggregate_amounts[key] += daily_total
            meta_by_key[key] = {
                "store_raw": store_raw,
                "subject": store_meta.subject,
                "receipt_ratio": store_meta.receipt_ratio,
            }

        upserted_ids: list[str] = []
        touched_store_months: set[tuple[str, str]] = set()

        for (date_str, store_name), amount in aggregate_amounts.items():
            weekday = self._weekday_cn(date_str)
            month = self._month_str(date_str)
            meta = meta_by_key[(date_str, store_name)]

            payload = {
                "日期": date_str,
                "门店": store_name,
                "营业额科目": meta["subject"],
                "星期": weekday,
                "日营业额": round(amount, 2),
                "月份": month,
                "月营业额": 0.0,
                "实收系数": meta["receipt_ratio"],
                "公司月实收金额": 0.0,
                "raw_store_name": meta["store_raw"],
            }

            logger.info("upsert start: date=%s store=%s daily_total=%s", date_str, store_name, amount)
            try:
                upsert_result = await self.bitable_service.upsert_daily_record(payload)
                if upsert_result.get("success"):
                    upserted_ids.append(upsert_result["record_id"])
                    if upsert_result.get("action") != "skipped":
                        touched_store_months.add((store_name, month))
                    store_results.append(
                        {
                            "date": date_str,
                            "store_raw": meta["store_raw"],
                            "store_name": store_name,
                            "action": upsert_result.get("action"),
                            "record_id": upsert_result.get("record_id"),
                            "success": True,
                        }
                    )
                else:
                    error = "BITABLE_UPSERT_FAILED: upsert result success=false"
                    errors.append(error)
                    store_results.append(
                        {
                            "date": date_str,
                            "store_raw": meta["store_raw"],
                            "store_name": store_name,
                            "action": "failed",
                            "success": False,
                            "error": error,
                        }
                    )
            except BitableServiceError as exc:
                error = f"BITABLE_UPSERT_FAILED: {exc}"
                logger.exception("bitable upsert failed: date=%s store=%s", date_str, store_name)
                errors.append(error)
                store_results.append(
                    {
                        "date": date_str,
                        "store_raw": meta["store_raw"],
                        "store_name": store_name,
                        "action": "failed",
                        "success": False,
                        "error": error,
                    }
                )

        # 按要求：对每个涉及的门店月份重算月字段
        for store_name, month in sorted(touched_store_months):
            try:
                logger.info("recompute monthly start: store=%s month=%s", store_name, month)
                await self.bitable_service.recompute_monthly_fields(store_name=store_name, month=month)
            except Exception as exc:
                error = f"MONTHLY_RECOMPUTE_FAILED: store={store_name} month={month} error={exc}"
                logger.exception(error)
                errors.append(error)

        success_count = sum(1 for x in store_results if x.get("success"))
        failed_count = sum(1 for x in store_results if not x.get("success"))

        summary = RevenueImportResult(
            imported_count=success_count,
            skipped_count=failed_count,
            upserted_record_ids=upserted_ids,
            success_store_count=success_count,
            failed_store_count=failed_count,
            store_results=store_results,
            errors=errors,
        )
        logger.info(
            "revenue import summary: success=%s failed=%s upserted=%s",
            summary.success_store_count,
            summary.failed_store_count,
            len(summary.upserted_record_ids),
        )
        return summary

    @staticmethod
    def _weekday_cn(date_str: str) -> str:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        return weekdays[dt.weekday()]

    @staticmethod
    def _month_str(date_str: str) -> str:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m")

    async def _resolve_store_meta(self, store_raw: str) -> StoreMeta:
        dynamic_meta = await self._resolve_store_meta_from_bitable_options(store_raw)
        if dynamic_meta:
            return dynamic_meta
        return get_store_meta(store_raw)

    async def _resolve_store_meta_from_bitable_options(self, store_raw: str) -> StoreMeta | None:
        try:
            store_options = await self.bitable_service.list_select_options("门店")
        except Exception as exc:
            logger.warning("load store options from bitable failed, fallback to store_config: %s", exc)
            return None

        if not store_options:
            return None

        raw_key = self._normalize_store_match_key(store_raw)
        for option in store_options:
            if self._normalize_store_match_key(option) != raw_key:
                continue

            subject = await self._infer_subject_from_store_option(option)
            return StoreMeta(
                store_name=option,
                subject=subject,
                receipt_ratio=self._receipt_ratio_for_subject(subject),
            )

        return None

    async def _infer_subject_from_store_option(self, store_name: str) -> str:
        if "示例科目B" in store_name:
            return "示例科目B"
        if "娃娃" in store_name or "集合营" in store_name:
            return "示例科目A"

        try:
            subject_options = await self.bitable_service.list_select_options("营业额科目")
        except Exception:
            subject_options = []

        if len(subject_options) == 1:
            return subject_options[0]
        return "示例科目A"

    @staticmethod
    def _receipt_ratio_for_subject(subject: str) -> float:
        if subject == "示例科目B":
            return 1.0
        return 0.54

    @staticmethod
    def _normalize_store_match_key(text: str) -> str:
        normalized = text.strip()
        normalized = re.sub(r"[\s\-－_（）()·.。]", "", normalized)
        for token in ("示例业务类型", "示例科目A", "示例科目B", "集合营", "门店", "店"):
            normalized = normalized.replace(token, "")
        return normalized
