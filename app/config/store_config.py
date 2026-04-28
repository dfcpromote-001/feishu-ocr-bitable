from __future__ import annotations

from dataclasses import dataclass


class StoreConfigNotFoundError(ValueError):
    """当 OCR 门店名无法映射到标准门店配置时抛出。"""


@dataclass(frozen=True)
class StoreMeta:
    store_name: str
    subject: str
    receipt_ratio: float


# key: OCR 原始门店名, value: 标准门店配置
STORE_CONFIG: dict[str, StoreMeta] = {
    "示例门店X店": StoreMeta(
        store_name="示例门店X店",
        subject="示例科目A",
        receipt_ratio=0.92,
    ),
    "示例门店X": StoreMeta(
        store_name="示例门店X店",
        subject="示例科目A",
        receipt_ratio=0.92,
    ),
    "示例门店Y店": StoreMeta(
        store_name="示例门店Y店",
        subject="示例科目B",
        receipt_ratio=0.88,
    ),
    "示例门店C店": StoreMeta(
        store_name="示例门店C-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店C": StoreMeta(
        store_name="示例门店C-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店B店": StoreMeta(
        store_name="示例门店B-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店B": StoreMeta(
        store_name="示例门店B-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店A店": StoreMeta(
        store_name="示例门店A-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店A": StoreMeta(
        store_name="示例门店A-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店D店": StoreMeta(
        store_name="示例门店D-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店D": StoreMeta(
        store_name="示例门店D-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店D别名店": StoreMeta(
        store_name="示例门店D-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店D别名": StoreMeta(
        store_name="示例门店D-业务类型",
        subject="示例科目A",
        receipt_ratio=0.54,
    ),
    "示例门店E店": StoreMeta(
        store_name="示例门店E-业务类型",
        subject="示例科目B",
        receipt_ratio=1.0,
    ),
    "示例门店E": StoreMeta(
        store_name="示例门店E-业务类型",
        subject="示例科目B",
        receipt_ratio=1.0,
    ),
}


def get_store_meta(store_raw: str) -> StoreMeta:
    """
    按 OCR 原始门店名获取标准门店配置。

    当前仅启用精确匹配；若未命中，抛出明确异常。
    预留了 fuzzy match 扩展入口，后续可开启。
    """
    normalized = store_raw.strip()
    exact = STORE_CONFIG.get(normalized)
    if exact:
        return exact

    # 预留扩展点：当前不启用模糊匹配，仅保留入口。
    fuzzy = _fuzzy_match_store_meta(normalized)
    if fuzzy:
        return fuzzy

    raise StoreConfigNotFoundError(f"未找到门店映射: {store_raw}")


def _fuzzy_match_store_meta(store_raw: str) -> StoreMeta | None:
    """
    模糊匹配扩展入口（占位）。

    后续可在此接入：
    - 别名词典
    - 编辑距离
    - 向量召回
    当前返回 None，表示仅支持精确匹配。
    """
    _ = store_raw
    return None
