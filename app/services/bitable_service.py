from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.clients.feishu_client import FeishuClient, FeishuAPIError
from app.config import settings

logger = logging.getLogger(__name__)

FEISHU_DATE_TIMEZONE = ZoneInfo("Asia/Shanghai")
FEISHU_WRITABLE_FIELDS = ("日期", "门店", "营业额科目", "日营业额")


class BitableServiceError(RuntimeError):
    """飞书多维表服务异常。"""


class BitableService:
    """
    门店日汇总表服务。

    - mock 模式：使用内存结构模拟飞书多维表
    - real 模式：预留真实飞书接口调用入口（当前占位）
    """

    def __init__(self, *, use_mock: bool = True) -> None:
        self.use_mock = use_mock
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        self._app_token = settings.bitable_app_token
        self._table_id = settings.bitable_table_id
        self._feishu_client = FeishuClient()
        self._select_options_cache: dict[str, list[str]] = {}

    async def find_record_by_date_and_store(self, date_str: str, store_name: str) -> dict[str, Any] | None:
        """按“日期 + 门店”查找记录。"""
        if self.use_mock:
            logger.info("[MOCK BITABLE] find record by date+store: date=%s store=%s", date_str, store_name)
            return self._records.get((date_str, store_name))

        try:
            logger.info("[FEISHU BITABLE] find record by date+store: date=%s store=%s", date_str, store_name)
            return await self._real_find_record_by_date_and_store(date_str, store_name)
        except Exception as exc:
            logger.exception("[FEISHU BITABLE] find failed: %s", str(exc))
            raise BitableServiceError(f"find_record_by_date_and_store failed: {exc}") from exc

    async def upsert_daily_record(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        按“日期 + 门店”进行 upsert。

        统一返回：
        {
          "action": "created" | "updated",
          "record_id": "...",
          "success": true
        }
        """
        normalized = self._normalize_payload(payload)
        date_str = normalized["日期"]
        store_name = normalized["门店"]

        if self.use_mock:
            return await self._mock_upsert_daily_record(normalized)

        try:
            logger.info("[FEISHU BITABLE] upsert start date=%s store=%s", date_str, store_name)
            existed = await self._real_find_record_by_date_and_store(date_str, store_name)
            writable_fields = self._to_feishu_record_fields(normalized)
            if existed:
                existing_daily_revenue = self._extract_daily_revenue(existed)
                incoming_daily_revenue = float(normalized["日营业额"])
                if existing_daily_revenue is not None and existing_daily_revenue >= incoming_daily_revenue:
                    logger.info(
                        "[FEISHU BITABLE] skipped record_id=%s existing_daily_revenue=%s incoming_daily_revenue=%s",
                        existed["record_id"],
                        existing_daily_revenue,
                        incoming_daily_revenue,
                    )
                    return {"action": "skipped", "record_id": existed["record_id"], "success": True}

                await self._real_update_record(existed["record_id"], writable_fields)
                logger.info("[FEISHU BITABLE] updated record_id=%s", existed["record_id"])
                return {"action": "updated", "record_id": existed["record_id"], "success": True}

            record_id = await self._real_create_record(writable_fields)
            logger.info("[FEISHU BITABLE] created record_id=%s", record_id)
            return {"action": "created", "record_id": record_id, "success": True}
        except Exception as exc:
            logger.exception("[FEISHU BITABLE] upsert failed: %s", str(exc))
            raise BitableServiceError(f"upsert_daily_record failed: {exc}") from exc

    async def list_select_options(self, field_name: str) -> list[str]:
        """读取多维表单选字段的选项名称。"""
        if field_name in self._select_options_cache:
            return self._select_options_cache[field_name]

        if self.use_mock:
            self._select_options_cache[field_name] = []
            return []

        try:
            fields = await self._feishu_client.list_bitable_fields()
        except FeishuAPIError as exc:
            logger.exception("[FEISHU BITABLE] list fields failed: %s", str(exc))
            raise BitableServiceError(f"list_select_options failed: {exc}") from exc

        for field in fields:
            if field.get("field_name") != field_name:
                continue

            raw_options = field.get("property", {}).get("options", [])
            options = [
                option["name"].strip()
                for option in raw_options
                if isinstance(option, dict) and isinstance(option.get("name"), str) and option["name"].strip()
            ]
            self._select_options_cache[field_name] = options
            return options

        self._select_options_cache[field_name] = []
        return []

    async def list_records_by_store_and_month(self, *, store_name: str, month: str) -> list[dict[str, Any]]:
        """查询某门店某月份下的全部日记录。"""
        if not self.use_mock:
            try:
                items = await self._feishu_client.list_bitable_records()
                records = []
                for item in items:
                    fields = item.get("fields", {})
                    if fields.get("门店") == store_name and fields.get("月份") == month:
                        records.append({"record_id": item.get("record_id"), **fields})
                records.sort(key=lambda x: x["日期"])
                return records
            except FeishuAPIError as exc:
                logger.exception("[FEISHU BITABLE] list by month failed: %s", str(exc))
                raise BitableServiceError(f"list_records_by_store_and_month failed: {exc}") from exc

        records = [
            record
            for record in self._records.values()
            if record["门店"] == store_name and record["月份"] == month
        ]
        records.sort(key=lambda x: x["日期"])
        return records

    async def recompute_monthly_fields(self, *, store_name: str, month: str) -> None:
        """
        重算某门店某月份的月字段，并确保该月份所有记录一致。

        - 月营业额 = 当月所有日营业额之和
        - 公司月实收金额 = 月营业额 * 实收系数
        """
        records = await self.list_records_by_store_and_month(store_name=store_name, month=month)
        if not records:
            return

        if not self.use_mock:
            logger.info(
                "[FEISHU BITABLE] skip monthly recompute because formula fields are owned by bitable: store=%s month=%s",
                store_name,
                month,
            )
            return

        monthly_revenue = round(sum(float(r["日营业额"]) for r in records), 2)
        receipt_ratio = float(records[0]["实收系数"])
        company_month_receipt = round(monthly_revenue * receipt_ratio, 2)

        for record in records:
            record["月营业额"] = monthly_revenue
            record["公司月实收金额"] = company_month_receipt

            # 兼容旧字段（供历史调用和测试）
            record["monthly_revenue"] = monthly_revenue
            record["company_month_receipt"] = company_month_receipt

        logger.info(
            "[MOCK BITABLE] recompute monthly fields store=%s month=%s monthly_revenue=%s company_month_receipt=%s",
            store_name,
            month,
            monthly_revenue,
            company_month_receipt,
        )

    async def _mock_upsert_daily_record(self, normalized: dict[str, Any]) -> dict[str, Any]:
        date_str = normalized["日期"]
        store_name = normalized["门店"]
        key = (date_str, store_name)

        existed = self._records.get(key)
        if existed:
            existing_daily_revenue = self._extract_daily_revenue(existed)
            incoming_daily_revenue = float(normalized["日营业额"])
            if existing_daily_revenue is not None and existing_daily_revenue >= incoming_daily_revenue:
                logger.info(
                    "[MOCK BITABLE] skipped record id=%s key=%s existing_daily_revenue=%s incoming_daily_revenue=%s",
                    existed["record_id"],
                    key,
                    existing_daily_revenue,
                    incoming_daily_revenue,
                )
                return {"action": "skipped", "record_id": existed["record_id"], "success": True}

            existed.update(normalized)
            action = "updated"
            record_id = existed["record_id"]
            logger.info("[MOCK BITABLE] updated record id=%s key=%s", record_id, key)
        else:
            record_id = f"mock_record_{uuid4().hex[:8]}"
            new_record = {"record_id": record_id, **normalized}
            self._records[key] = new_record
            action = "created"
            logger.info("[MOCK BITABLE] created record id=%s key=%s", record_id, key)

        await self.recompute_monthly_fields(store_name=store_name, month=normalized["月份"])
        return {"action": action, "record_id": record_id, "success": True}

    def _normalize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """将入参标准化为目标字段集合。"""
        date_str = str(payload.get("日期") or payload.get("date") or "").strip()
        store_name = str(payload.get("门店") or payload.get("store_name") or "").strip()
        subject = str(payload.get("营业额科目") or payload.get("revenue_subject") or "").strip()

        if not date_str or not store_name:
            raise BitableServiceError("payload missing required fields: 日期/date and 门店/store_name")

        weekday = str(payload.get("星期") or self._extract_weekday_cn(date_str)).strip()
        month = str(payload.get("月份") or self._extract_month(date_str)).strip()
        daily_revenue = round(float(payload.get("日营业额") or payload.get("daily_revenue") or 0.0), 2)
        receipt_ratio = float(payload.get("实收系数") or payload.get("receipt_coefficient") or 1.0)

        normalized = {
            "日期": date_str,
            "门店": store_name,
            "营业额科目": subject,
            "星期": weekday,
            "日营业额": daily_revenue,
            "月份": month,
            "月营业额": round(float(payload.get("月营业额") or 0.0), 2),
            "实收系数": receipt_ratio,
            "公司月实收金额": round(float(payload.get("公司月实收金额") or 0.0), 2),
            # 兼容旧字段（供现有调用）
            "date": date_str,
            "store_name": store_name,
            "daily_revenue": daily_revenue,
            "month": month,
            "receipt_coefficient": receipt_ratio,
            "revenue_subject": subject,
            "weekly_label": weekday,
            "monthly_revenue": round(float(payload.get("月营业额") or 0.0), 2),
            "company_month_receipt": round(float(payload.get("公司月实收金额") or 0.0), 2),
            "raw_store_name": payload.get("raw_store_name"),
        }
        return normalized

    def _to_feishu_record_fields(self, normalized: dict[str, Any]) -> dict[str, Any]:
        """
        真实多维表只写用户维护的字段。

        截图中的星期、月份、月营业额、实收系数、公司月实收金额是公式字段，
        不能通过记录接口直接写入。
        """
        fields = {name: normalized[name] for name in FEISHU_WRITABLE_FIELDS}
        fields["日期"] = self._date_to_feishu_timestamp_ms(str(normalized["日期"]))
        return fields

    async def _real_find_record_by_date_and_store(self, date_str: str, store_name: str) -> dict[str, Any] | None:
        """
        真实飞书接口占位：按日期+门店检索记录。

        后续在此调用飞书多维表查询 API，并返回匹配到的记录（含 record_id）。
        """
        items = await self._feishu_client.list_bitable_records()
        for item in items:
            fields = item.get("fields", {})
            record_date = self._normalize_feishu_date_for_compare(fields.get("日期"))
            record_store = self._normalize_feishu_text_for_compare(fields.get("门店"))
            if record_date == date_str and record_store == store_name:
                return {"record_id": item.get("record_id"), **fields}
        return None

    async def _real_create_record(self, fields: dict[str, Any]) -> str:
        """真实飞书接口占位：创建记录。"""
        return await self._feishu_client.create_bitable_record(fields)

    async def _real_update_record(self, record_id: str, fields: dict[str, Any]) -> None:
        """真实飞书接口占位：更新记录。"""
        await self._feishu_client.update_bitable_record(record_id=record_id, fields=fields)

    @staticmethod
    def _extract_month(date_text: str) -> str:
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return dt.strftime("%Y-%m")

    @staticmethod
    def _extract_weekday_cn(date_text: str) -> str:
        weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        dt = datetime.strptime(date_text, "%Y-%m-%d")
        return weekday_cn[dt.weekday()]

    @staticmethod
    def _date_to_feishu_timestamp_ms(date_text: str) -> int:
        dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=FEISHU_DATE_TIMEZONE)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def _normalize_feishu_date_for_compare(value: Any) -> str:
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value / 1000, tz=FEISHU_DATE_TIMEZONE).strftime("%Y-%m-%d")
        if isinstance(value, str):
            value = value.strip()
            if value.isdigit():
                return datetime.fromtimestamp(int(value) / 1000, tz=FEISHU_DATE_TIMEZONE).strftime("%Y-%m-%d")
            normalized = value.replace("/", "-").replace(".", "-")
            try:
                return datetime.strptime(normalized, "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                return value
        return ""

    @staticmethod
    def _normalize_feishu_text_for_compare(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first.strip()
            if isinstance(first, dict):
                text = first.get("text") or first.get("name") or first.get("value")
                if text is not None:
                    return str(text).strip()
        if isinstance(value, dict):
            text = value.get("text") or value.get("name") or value.get("value")
            if text is not None:
                return str(text).strip()
        return str(value).strip() if value is not None else ""

    @staticmethod
    def _extract_daily_revenue(record: dict[str, Any]) -> float | None:
        value = record.get("日营业额") or record.get("daily_revenue")
        if isinstance(value, dict):
            value = value.get("value") or value.get("text")
        if isinstance(value, list) and value:
            value = value[0]
            if isinstance(value, dict):
                value = value.get("value") or value.get("text")
        if value is None or value == "":
            return None
        try:
            return round(float(str(value).replace(",", "")), 2)
        except (TypeError, ValueError):
            return None
