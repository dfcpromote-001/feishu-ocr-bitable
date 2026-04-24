from __future__ import annotations

import re

from app.models.schemas import ExtractedFields


class FieldExtractor:
    FIELD_PATTERNS = {
        "mall_name": [r"商场名称[:：]\s*(.+)", r"商场[:：]\s*(.+)"],
        "visit_date": [r"看场日期[:：]\s*(.+)", r"日期[:：]\s*(.+)"],
        "traffic_comment": [r"客流评价[:：]\s*(.+)", r"客流[:：]\s*(.+)"],
        "competitor_status": [r"竞品情况[:：]\s*(.+)", r"竞品[:：]\s*(.+)"],
        "preliminary_conclusion": [r"初步结论[:：]\s*(.+)", r"结论[:：]\s*(.+)"],
    }

    def extract(self, ocr_text: str) -> ExtractedFields:
        normalized = self._normalize_text(ocr_text)
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]

        payload: dict[str, str | None] = {
            "mall_name": None,
            "visit_date": None,
            "traffic_comment": None,
            "competitor_status": None,
            "preliminary_conclusion": None,
        }

        for field, patterns in self.FIELD_PATTERNS.items():
            payload[field] = self._extract_from_lines(lines, patterns)

        return ExtractedFields(**payload)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return (
            text.replace("\r", "\n")
            .replace("；", "\n")
            .replace(";", "\n")
            .replace("。", "\n")
        )

    @staticmethod
    def _extract_from_lines(lines: list[str], patterns: list[str]) -> str | None:
        for line in lines:
            for pattern in patterns:
                m = re.search(pattern, line)
                if m:
                    value = m.group(1).strip()
                    if value:
                        return value
        return None
