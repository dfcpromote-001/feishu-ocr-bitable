from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from app.models.schemas import ParsedScreenshotResult, StoreDailyRevenue


class ParserService:
    """将 OCR 文本解析为“门店每日总营业额”记录。"""

    DATE_RANGE_PATTERN = r"截止\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})\s*至\s*(\d{4}[./-]\d{1,2}[./-]\d{1,2})"
    DATE_FALLBACK_PATTERNS = [
        r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
    ]

    AMOUNT_LABEL_PATTERN = r"(?:营业|营收)金额\s*[（(]\s*元\s*[）)]"
    NUMBER_PATTERN = r"([0-9,]+(?:\.\d{1,2})?)"

    IGNORE_KEYWORDS = [
        "更多数据",
        "小程序收款",
        "在线收款",
        "抖音核销",
        "美团核销",
        "现金收款",
        "全部门店",
    ]

    NON_STORE_HINTS = [
        "营业金额",
        "总营业额",
        "营收总额",
        "截止",
        "更多数据",
        "收款",
        "核销",
        "合计",
        "总计",
        "本页",
    ]

    STORE_PREFIX_PATTERN = r"^(?:门店|店铺|店名)[:：]\s*(.+)$"

    def parse(self, ocr_text: str) -> list[dict[str, Any]]:
        """
        输出格式：
        [
          {
            "date": "2026-04-19",
            "store_raw": "示例门店B店",
            "daily_total": 4100.10
          }
        ]
        """
        lines = self._clean_lines(ocr_text)
        date_text = self._extract_date(lines)
        if not date_text:
            raise ValueError("无法识别日期")

        store_positions = self._extract_store_positions(lines)
        if not store_positions:
            return []

        aggregates: dict[str, float] = defaultdict(float)

        for idx, store_name in store_positions:
            next_idx = len(lines)
            for n_idx, _ in store_positions:
                if n_idx > idx:
                    next_idx = n_idx
                    break

            amount = self._extract_store_amount(lines, start=idx, end=next_idx)
            if amount is None:
                continue
            aggregates[store_name] += amount

        result = [
            {
                "date": date_text,
                "store_raw": store_name,
                "daily_total": round(total, 2),
            }
            for store_name, total in aggregates.items()
        ]
        return result

    def parse_to_result(self, ocr_text: str) -> ParsedScreenshotResult:
        """兼容旧调用方：将新格式转为 ParsedScreenshotResult。"""
        records = self.parse(ocr_text)
        if not records:
            return ParsedScreenshotResult(date=None, items=[])

        date_text = records[0]["date"]
        items = [
            StoreDailyRevenue(
                date=record["date"],
                raw_store_name=record["store_raw"],
                daily_revenue=record["daily_total"],
            )
            for record in records
        ]
        return ParsedScreenshotResult(date=date_text, items=items)

    def _extract_store_amount(self, lines: list[str], *, start: int, end: int) -> float | None:
        # 优先在当前门店块（本门店行到下一门店行之间）找营业金额(元)
        for i in range(start, end):
            amount = self._extract_amount_at_line(lines, i)
            if amount is not None:
                return amount

        # 容错：OCR 轻微错乱时，允许回看门店行之前 2 行
        for i in range(max(0, start - 2), start):
            amount = self._extract_amount_at_line(lines, i)
            if amount is not None:
                return amount

        return None

    def _extract_amount_at_line(self, lines: list[str], idx: int) -> float | None:
        line = lines[idx]
        if re.search(self.AMOUNT_LABEL_PATTERN, line) is None:
            return None

        same_line_value = self._extract_number(line)
        if same_line_value is not None:
            return same_line_value

        if idx + 1 < len(lines):
            next_line_value = self._extract_number(lines[idx + 1])
            if next_line_value is not None:
                return next_line_value

        return None

    def _extract_date(self, lines: list[str]) -> str | None:
        for line in lines:
            m = re.search(self.DATE_RANGE_PATTERN, line)
            if m:
                # 业务口径以截图顶部日期为准，区间首尾一致时取首个即可。
                return self._normalize_date(m.group(1))

        for line in lines:
            for pattern in self.DATE_FALLBACK_PATTERNS:
                m = re.search(pattern, line)
                if m:
                    return self._normalize_date(m.group(1))

        return None

    def _extract_store_positions(self, lines: list[str]) -> list[tuple[int, str]]:
        positions: list[tuple[int, str]] = []
        for idx, line in enumerate(lines):
            store_name = self._parse_store_name(line)
            if store_name:
                positions.append((idx, store_name))
        return positions

    def _parse_store_name(self, line: str) -> str | None:
        explicit = re.match(self.STORE_PREFIX_PATTERN, line)
        if explicit:
            candidate = explicit.group(1).strip()
            if self._is_explicit_store_candidate(candidate):
                return candidate
            return None

        if self._is_store_candidate(line):
            return line
        return None

    def _is_explicit_store_candidate(self, text: str) -> bool:
        """
        显式门店行（如“门店：xxx”）的校验。

        与普通行不同：不强制包含“店”，因为 OCR 原始门店名可能是别名
        （例如“示例门店X”），后续会交给 store_config 做标准映射。
        """
        if not text:
            return False
        for keyword in self.IGNORE_KEYWORDS:
            if keyword in text:
                return False
        for hint in self.NON_STORE_HINTS:
            if hint in text:
                return False
        return True

    def _is_store_candidate(self, text: str) -> bool:
        if not text:
            return False

        for keyword in self.IGNORE_KEYWORDS:
            if keyword in text:
                return False

        for hint in self.NON_STORE_HINTS:
            if hint in text:
                return False

        # 门店名通常包含“店”，避免把页面文案误判为门店。
        if "店" not in text:
            return False

        return True

    def _clean_lines(self, text: str) -> list[str]:
        raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
        cleaned: list[str] = []
        for line in raw_lines:
            if any(keyword in line for keyword in self.IGNORE_KEYWORDS):
                continue
            cleaned.append(line)
        return cleaned

    @staticmethod
    def _extract_number(text: str) -> float | None:
        m = re.search(ParserService.NUMBER_PATTERN, text)
        if not m:
            return None
        return float(m.group(1).replace(",", ""))

    @staticmethod
    def _normalize_date(date_text: str) -> str:
        normalized = date_text.replace("/", "-").replace(".", "-")
        year, month, day = normalized.split("-")
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
