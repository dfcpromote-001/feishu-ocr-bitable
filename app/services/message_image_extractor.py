from __future__ import annotations

import json
from typing import Any


def extract_image_keys_from_message_content(message_type: str | None, content: str | None) -> list[str]:
    if not content:
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    if message_type == "image":
        image_key = data.get("image_key")
        return [image_key] if isinstance(image_key, str) and image_key else []

    if message_type == "post":
        return _extract_image_keys_from_post(data)

    return []


def _extract_image_keys_from_post(data: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    blocks = data.get("content", [])
    if not isinstance(blocks, list):
        return keys

    for block in blocks:
        if not isinstance(block, list):
            continue
        for item in block:
            if not isinstance(item, dict):
                continue
            if item.get("tag") != "img":
                continue
            image_key = item.get("image_key")
            if isinstance(image_key, str) and image_key:
                keys.append(image_key)
    return keys
