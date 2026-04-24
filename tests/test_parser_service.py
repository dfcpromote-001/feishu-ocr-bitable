import pytest

from app.services.parser_service import ParserService


def test_parse_multiple_stores() -> None:
    text = """
    截止 2026.04.19 至 2026.04.19
    示例门店B店
    营业金额(元)：4100.10
    示例门店G店
    营业金额(元)：2300
    """

    result = ParserService().parse(text)

    assert result == [
        {"date": "2026-04-19", "store_raw": "示例门店B店", "daily_total": 4100.10},
        {"date": "2026-04-19", "store_raw": "示例门店G店", "daily_total": 2300.0},
    ]


def test_parse_single_store() -> None:
    text = """
    截止 2026-04-19 至 2026-04-19
    门店：示例门店B店
    营业金额(元)：1000
    """

    result = ParserService().parse(text)

    assert result == [{"date": "2026-04-19", "store_raw": "示例门店B店", "daily_total": 1000.0}]


def test_parse_with_slightly_disordered_lines() -> None:
    text = """
    截止 2026.04.19 至 2026.04.19
    营业金额(元)
    4100.10
    示例门店B店
    """

    result = ParserService().parse(text)

    assert result == [{"date": "2026-04-19", "store_raw": "示例门店B店", "daily_total": 4100.10}]


def test_parse_ignores_channel_fields_and_more_data_and_top_total() -> None:
    text = """
    截止 2026.04.19 至 2026.04.19
    总营业额(元)：99999
    更多数据
    示例门店B店
    小程序收款：100
    在线收款：200
    抖音核销：300
    美团核销：400
    现金收款：500
    营业金额(元)：4100.10
    """

    result = ParserService().parse(text)

    assert result == [{"date": "2026-04-19", "store_raw": "示例门店B店", "daily_total": 4100.10}]


def test_parse_raises_when_date_not_found() -> None:
    text = """
    示例门店B店
    营业金额(元)：4100.10
    """

    with pytest.raises(ValueError, match="无法识别日期"):
        ParserService().parse(text)


def test_parse_aggregates_same_store_in_one_day() -> None:
    text = """
    截止 2026.04.19 至 2026.04.19
    示例门店B店
    营业金额(元)：1000
    示例门店B店
    营业金额(元)：2000.5
    """

    result = ParserService().parse(text)

    assert result == [{"date": "2026-04-19", "store_raw": "示例门店B店", "daily_total": 3000.5}]


def test_parse_real_overview_ocr_text_with_revenue_label() -> None:
    text = """
    00:11
    5G 69
    概况
    营收概况
    礼品回收概况
    礼品兑换概况
    提售币根
    全部门店
    昨天
    今天
    本周
    本月
    今年
    截止2026.04.18至2026.04.18
    示例门店A店
    更多数据>
    营收金额（元）
    2,928.20
    抖音核销
    现金收款
    美团核销
    2,528.80
    120.00
    279.40
    示例门店B店
    更多数据>
    营收金额（元）
    3,129.50
    抖音核销
    美团核销
    2,770.40
    359.10
    示例门店F店
    更多数据>
    营收金额（元）
    2,828.30
    在线收款
    小程序收款
    抖音核销
    20.00
    170.00
    1,852.40
    美团核销
    营收总额（元）
    17,338.90
    """

    result = ParserService().parse(text)

    assert result == [
        {"date": "2026-04-18", "store_raw": "示例门店A店", "daily_total": 2928.20},
        {"date": "2026-04-18", "store_raw": "示例门店B店", "daily_total": 3129.50},
        {"date": "2026-04-18", "store_raw": "示例门店F店", "daily_total": 2828.30},
    ]
