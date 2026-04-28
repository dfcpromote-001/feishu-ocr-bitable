from app.longconn_runner import _build_multi_image_reply
from app.models.schemas import RevenueImportResult


def test_build_multi_image_reply_keeps_image_order() -> None:
    first = RevenueImportResult(success_store_count=2, failed_store_count=0)
    third = RevenueImportResult(
        success_store_count=1,
        failed_store_count=1,
        errors=["STORE_MAPPING_FAILED: 未找到门店映射: 示例门店"],
    )

    reply = _build_multi_image_reply(
        [(1, first), (3, third)],
        [(2, "OCR_FAILED")],
        image_count=3,
    )

    assert reply.splitlines() == [
        "全部处理完成",
        "第 1/3 张：成功 2，失败 0",
        "第 2/3 张：处理失败",
        "错误：OCR_FAILED",
        "第 3/3 张：成功 1，失败 1",
        "错误：STORE_MAPPING_FAILED: 未找到门店映射: 示例门店",
        "合计：成功 3，失败 2",
    ]


def test_build_multi_image_reply_limits_error_lines() -> None:
    result = RevenueImportResult(
        success_store_count=0,
        failed_store_count=4,
        errors=["错误1", "错误2", "错误3", "错误4"],
    )

    reply = _build_multi_image_reply([(1, result)], [], image_count=1)

    assert reply.splitlines() == [
        "全部处理完成",
        "第 1/1 张：成功 0，失败 4",
        "错误：错误1",
        "错误：错误2",
        "错误：错误3",
        "另有 1 条错误，详见日志。",
        "合计：成功 0，失败 4",
    ]
