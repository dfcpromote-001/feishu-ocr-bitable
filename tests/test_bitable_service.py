import pytest

from app.services.bitable_service import BitableService


@pytest.mark.asyncio
async def test_upsert_and_monthly_fields_consistent_for_same_store_month() -> None:
    service = BitableService()

    res1 = await service.upsert_daily_record(
        {
            "date": "2026-04-01",
            "raw_store_name": "示例门店X店",
            "store_name": "示例门店X店",
            "daily_revenue": 100.0,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.9,
        }
    )
    res2 = await service.upsert_daily_record(
        {
            "date": "2026-04-02",
            "raw_store_name": "示例门店X店",
            "store_name": "示例门店X店",
            "daily_revenue": 200.0,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.9,
        }
    )
    record_id_1 = res1["record_id"]
    record_id_2 = res2["record_id"]
    assert res1["action"] == "created"
    assert res2["action"] == "created"
    assert res1["success"] is True
    assert res2["success"] is True

    records = await service.list_records_by_store_and_month(store_name="示例门店X店", month="2026-04")

    assert len(records) == 2
    assert records[0]["月营业额"] == 300.0
    assert records[1]["月营业额"] == 300.0
    assert records[0]["公司月实收金额"] == 270.0
    assert records[1]["公司月实收金额"] == 270.0

    # 同一日期同一门店：新金额更高才更新，不新增新记录
    updated = await service.upsert_daily_record(
        {
            "date": "2026-04-01",
            "raw_store_name": "示例门店X店",
            "store_name": "示例门店X店",
            "daily_revenue": 150.0,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.9,
        }
    )
    assert updated["action"] == "updated"
    assert updated["record_id"] == record_id_1
    assert updated["record_id"] != record_id_2

    skipped_lower = await service.upsert_daily_record(
        {
            "date": "2026-04-01",
            "raw_store_name": "示例门店X店",
            "store_name": "示例门店X店",
            "daily_revenue": 120.0,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.9,
        }
    )
    skipped_same = await service.upsert_daily_record(
        {
            "date": "2026-04-01",
            "raw_store_name": "示例门店X店",
            "store_name": "示例门店X店",
            "daily_revenue": 150.0,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.9,
        }
    )
    assert skipped_lower["action"] == "skipped"
    assert skipped_same["action"] == "skipped"
    assert skipped_lower["record_id"] == record_id_1
    assert skipped_same["record_id"] == record_id_1

    records_after = await service.list_records_by_store_and_month(store_name="示例门店X店", month="2026-04")
    assert len(records_after) == 2
    assert records_after[0]["日营业额"] == 150.0
    assert records_after[0]["月营业额"] == 350.0
    assert records_after[1]["月营业额"] == 350.0
    assert records_after[0]["公司月实收金额"] == 315.0
    assert records_after[1]["公司月实收金额"] == 315.0


@pytest.mark.asyncio
async def test_find_record_by_date_and_store() -> None:
    service = BitableService()
    created = await service.upsert_daily_record(
        {
            "date": "2026-04-10",
            "store_name": "示例门店Y店",
            "daily_revenue": 123.45,
            "revenue_subject": "示例科目B",
            "receipt_coefficient": 0.88,
        }
    )

    found = await service.find_record_by_date_and_store("2026-04-10", "示例门店Y店")
    assert found is not None
    assert found["record_id"] == created["record_id"]
    assert found["日期"] == "2026-04-10"
    assert found["门店"] == "示例门店Y店"


def test_real_bitable_payload_only_contains_writable_fields() -> None:
    service = BitableService(use_mock=False)

    normalized = service._normalize_payload(
        {
            "date": "2026-04-18",
            "store_name": "示例门店A-业务类型",
            "daily_revenue": 2928.2,
            "revenue_subject": "示例科目A",
            "receipt_coefficient": 0.54,
        }
    )

    fields = service._to_feishu_record_fields(normalized)

    assert set(fields) == {"日期", "门店", "营业额科目", "日营业额"}
    assert fields["门店"] == "示例门店A-业务类型"
    assert fields["营业额科目"] == "示例科目A"
    assert fields["日营业额"] == 2928.2
    assert service._normalize_feishu_date_for_compare(fields["日期"]) == "2026-04-18"


@pytest.mark.asyncio
async def test_real_upsert_skips_when_existing_daily_revenue_is_same_or_higher() -> None:
    class FakeFeishuClient:
        update_calls: list[dict] = []

        async def list_bitable_records(self) -> list[dict]:
            return [
                {
                    "record_id": "rec_existing",
                    "fields": {
                        "日期": "2026-04-18",
                        "门店": "示例门店A-业务类型",
                        "日营业额": 3000.0,
                    },
                }
            ]

        async def update_bitable_record(self, *, record_id: str, fields: dict) -> None:
            self.update_calls.append({"record_id": record_id, "fields": fields})

    fake_client = FakeFeishuClient()
    service = BitableService(use_mock=False)
    service._feishu_client = fake_client

    result = await service.upsert_daily_record(
        {
            "date": "2026-04-18",
            "store_name": "示例门店A-业务类型",
            "daily_revenue": 2928.2,
            "revenue_subject": "示例科目A",
        }
    )

    assert result == {"action": "skipped", "record_id": "rec_existing", "success": True}
    assert fake_client.update_calls == []


@pytest.mark.asyncio
async def test_list_select_options_reads_field_property_options() -> None:
    class FakeFeishuClient:
        async def list_bitable_fields(self) -> list[dict]:
            return [
                {
                    "field_name": "门店",
                    "property": {
                        "options": [
                            {"name": "示例门店A-业务类型"},
                            {"name": "示例门店B-业务类型"},
                        ]
                    },
                }
            ]

    service = BitableService(use_mock=False)
    service._feishu_client = FakeFeishuClient()

    assert await service.list_select_options("门店") == [
        "示例门店A-业务类型",
        "示例门店B-业务类型",
    ]
