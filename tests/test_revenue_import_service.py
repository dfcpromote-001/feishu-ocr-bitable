import pytest

from app.services.bitable_service import BitableService
from app.services.revenue_import_service import RevenueImportService


class OptionBackedBitableService(BitableService):
    async def list_select_options(self, field_name: str) -> list[str]:
        if field_name == "门店":
            return ["示例门店A-业务类型"]
        if field_name == "营业额科目":
            return ["示例科目A"]
        return []


@pytest.mark.asyncio
async def test_import_aggregates_same_store_same_day_into_one_record() -> None:
    bitable_service = BitableService()
    service = RevenueImportService(bitable_service=bitable_service)

    ocr_result = {
        "full_text": "\n".join(
            [
                "日期：2026-04-23",
                "门店：示例门店X店",
                "营业金额(元)：100",
                "门店：示例门店X",
                "营业金额(元)：50",
                "门店：示例门店Y店",
                "营业金额(元)：80",
            ]
        ),
        "lines": [],
    }

    result = await service.import_from_ocr_result(ocr_result)

    assert result.imported_count == 2
    assert result.skipped_count == 0

    doll_records = await bitable_service.list_records_by_store_and_month(
        store_name="示例门店X店",
        month="2026-04",
    )
    handmade_records = await bitable_service.list_records_by_store_and_month(
        store_name="示例门店Y店",
        month="2026-04",
    )

    assert len(doll_records) == 1
    assert len(handmade_records) == 1
    assert doll_records[0]["daily_revenue"] == 150.0
    assert handmade_records[0]["daily_revenue"] == 80.0

    # 同月字段一致性
    assert doll_records[0]["monthly_revenue"] == 150.0
    assert handmade_records[0]["monthly_revenue"] == 80.0


@pytest.mark.asyncio
async def test_import_returns_store_mapping_failed_when_store_not_configured() -> None:
    bitable_service = BitableService()
    service = RevenueImportService(bitable_service=bitable_service)

    ocr_result = {
        "full_text": "\n".join(
            [
                "截止 2026.04.23 至 2026.04.23",
                "未知门店A店",
                "营业金额(元)：100",
            ]
        ),
        "lines": [],
    }

    result = await service.import_from_ocr_result(ocr_result)

    assert result.success_store_count == 0
    assert result.failed_store_count == 1
    assert len(result.store_results) == 1
    assert result.store_results[0]["success"] is False
    assert "STORE_MAPPING_FAILED" in result.store_results[0]["error"]
    assert any("STORE_MAPPING_FAILED" in err for err in result.errors)


@pytest.mark.asyncio
async def test_import_returns_ocr_failed_when_image_ref_empty() -> None:
    service = RevenueImportService()
    result = await service.import_from_image_ref(image_ref="", use_mock_ocr=True)

    assert result.success_store_count == 0
    assert result.failed_store_count == 1
    assert any("OCR_FAILED" in err for err in result.errors)


@pytest.mark.asyncio
async def test_import_maps_store_from_bitable_select_options() -> None:
    bitable_service = OptionBackedBitableService()
    service = RevenueImportService(bitable_service=bitable_service)

    ocr_result = {
        "full_text": "\n".join(
            [
                "截止 2026.04.18 至 2026.04.18",
                "示例门店A店",
                "营收金额（元）",
                "2,928.20",
            ]
        ),
        "lines": [],
    }

    result = await service.import_from_ocr_result(ocr_result)

    assert result.success_store_count == 1
    assert result.failed_store_count == 0
    assert result.store_results[0]["store_name"] == "示例门店A-业务类型"

    records = await bitable_service.list_records_by_store_and_month(
        store_name="示例门店A-业务类型",
        month="2026-04",
    )
    assert records[0]["daily_revenue"] == 2928.2
    assert records[0]["revenue_subject"] == "示例科目A"
