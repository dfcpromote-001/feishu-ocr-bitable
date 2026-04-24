import pytest

from app.config.store_config import (
    STORE_CONFIG,
    StoreConfigNotFoundError,
    StoreMeta,
    _fuzzy_match_store_meta,
    get_store_meta,
)


def test_get_store_meta_exact_match() -> None:
    meta = get_store_meta("示例门店X店")

    assert isinstance(meta, StoreMeta)
    assert meta.store_name == "示例门店X店"
    assert meta.subject == "示例科目A"
    assert meta.receipt_ratio == 0.92


def test_get_store_meta_alias_maps_to_same_standard_store() -> None:
    alias_meta = get_store_meta("示例门店X")
    standard_meta = get_store_meta("示例门店X店")

    assert alias_meta.store_name == standard_meta.store_name
    assert alias_meta.subject == standard_meta.subject
    assert alias_meta.receipt_ratio == standard_meta.receipt_ratio


def test_get_store_meta_maps_real_store_alias_to_bitable_option() -> None:
    meta = get_store_meta("示例门店A店")

    assert meta.store_name == "示例门店A-业务类型"
    assert meta.subject == "示例科目A"
    assert meta.receipt_ratio == 0.54


def test_get_store_meta_maps_tiantai_shiji_alias_to_xiangsheng_option() -> None:
    meta = get_store_meta("示例门店D别名店")

    assert meta.store_name == "示例门店D-业务类型"
    assert meta.subject == "示例科目A"
    assert meta.receipt_ratio == 0.54


def test_get_store_meta_raises_when_not_found() -> None:
    with pytest.raises(StoreConfigNotFoundError, match="未找到门店映射"):
        get_store_meta("不存在的门店")


def test_store_config_value_type() -> None:
    for meta in STORE_CONFIG.values():
        assert isinstance(meta, StoreMeta)


def test_fuzzy_match_entrypoint_reserved_but_disabled_now() -> None:
    assert _fuzzy_match_store_meta("示例门店X店") is None
