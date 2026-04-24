from __future__ import annotations

from pydantic import BaseModel, Field


class FeishuHeader(BaseModel):
    event_type: str | None = None


class FeishuMessage(BaseModel):
    message_id: str | None = None
    message_type: str | None = None
    chat_id: str | None = None
    content: str | None = None


class FeishuEvent(BaseModel):
    message: FeishuMessage | None = None


class FeishuWebhookPayload(BaseModel):
    type: str | None = None
    challenge: str | None = None
    token: str | None = None
    header: FeishuHeader | None = None
    event: FeishuEvent | None = None


class StoreDailyRevenue(BaseModel):
    date: str = Field(description="营业日期，格式 YYYY-MM-DD")
    raw_store_name: str = Field(description="OCR 提取到的原始门店名")
    daily_revenue: float = Field(ge=0, description="该门店当日营业金额(元)")


class ParsedScreenshotResult(BaseModel):
    date: str | None = Field(default=None, description="截图主日期")
    items: list[StoreDailyRevenue] = Field(default_factory=list, description="门店日营业额列表")


class RevenueImportResult(BaseModel):
    imported_count: int = 0
    skipped_count: int = 0
    upserted_record_ids: list[str] = Field(default_factory=list)
    success_store_count: int = 0
    failed_store_count: int = 0
    store_results: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
