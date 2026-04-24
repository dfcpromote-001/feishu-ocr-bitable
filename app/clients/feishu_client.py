from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class FeishuAPIError(RuntimeError):
    def __init__(self, message: str, *, code: int | None = None, log_id: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.log_id = log_id


class FeishuClient:
    BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self) -> None:
        self._token: str | None = None
        self._token_expire_at: float = 0

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        require_token: bool = True,
    ) -> dict[str, Any]:
        req_headers = headers.copy() if headers else {}
        req_headers["Content-Type"] = req_headers.get("Content-Type", "application/json")

        if require_token:
            req_headers["Authorization"] = f"Bearer {await self.get_tenant_access_token()}"

        url = f"{self.BASE_URL}{path}"
        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                headers=req_headers,
            )

        data: dict[str, Any] = {}
        try:
            data = resp.json()
        except Exception:
            data = {}

        if resp.status_code >= 400:
            code = data.get("code")
            log_id = data.get("error", {}).get("log_id")
            raise FeishuAPIError(
                f"Feishu HTTP error: {resp.status_code}, body={resp.text}",
                code=int(code) if isinstance(code, int) else None,
                log_id=log_id if isinstance(log_id, str) else None,
            )

        if data.get("code") not in (0, "0", None):
            code = data.get("code")
            log_id = data.get("error", {}).get("log_id")
            raise FeishuAPIError(
                f"Feishu API error: code={data.get('code')} msg={data.get('msg')}",
                code=int(code) if isinstance(code, int) else None,
                log_id=log_id if isinstance(log_id, str) else None,
            )
        return data

    async def get_tenant_access_token(self) -> str:
        if self._token and time.time() < self._token_expire_at:
            return self._token

        data = await self._request(
            "POST",
            "/auth/v3/tenant_access_token/internal",
            json_body={"app_id": settings.feishu_app_id, "app_secret": settings.feishu_app_secret},
            require_token=False,
        )

        token = data.get("tenant_access_token")
        if not token:
            raise FeishuAPIError("tenant_access_token missing")

        expire_seconds = int(data.get("expire", 7200))
        self._token = token
        self._token_expire_at = time.time() + max(expire_seconds - 60, 60)
        return token

    async def download_message_image(self, *, message_id: str, image_key: str) -> bytes:
        logger.info("download message image start: message_id=%s image_key=%s", message_id, image_key)
        token = await self.get_tenant_access_token()
        url = f"{self.BASE_URL}/im/v1/messages/{message_id}/resources/{image_key}"
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
            resp = await client.get(url=url, headers=headers, params={"type": "image"})

        if resp.status_code >= 400:
            raise FeishuAPIError(
                f"download image failed: status={resp.status_code}, message_id={message_id}, image_key={image_key}, body={resp.text}"
            )
        logger.info("download message image done: message_id=%s image_key=%s bytes=%s", message_id, image_key, len(resp.content))
        return resp.content

    async def ocr_basic_recognize(self, *, image_bytes: bytes) -> dict[str, Any]:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        data = await self._request(
            "POST",
            "/optical_char_recognition/v1/image/basic_recognize",
            json_body={"image": image_base64},
        )
        text_list = data.get("data", {}).get("text_list", [])
        lines = [line.strip() for line in text_list if isinstance(line, str) and line.strip()]
        return {"full_text": "\n".join(lines), "lines": lines}

    async def reply_text_message(self, *, message_id: str, text: str) -> None:
        path = f"/im/v1/messages/{message_id}/reply"
        await self._request(
            "POST",
            path,
            json_body={
                "msg_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
            },
        )

    async def create_bitable_record(self, fields: dict[str, Any]) -> str:
        path = f"/bitable/v1/apps/{settings.bitable_app_token}/tables/{settings.bitable_table_id}/records"
        data = await self._request("POST", path, json_body={"fields": fields})
        record_id = data.get("data", {}).get("record", {}).get("record_id")
        if not record_id:
            raise FeishuAPIError("create_bitable_record missing record_id")
        return record_id

    async def update_bitable_record(self, *, record_id: str, fields: dict[str, Any]) -> None:
        path = f"/bitable/v1/apps/{settings.bitable_app_token}/tables/{settings.bitable_table_id}/records/{record_id}"
        await self._request("PUT", path, json_body={"fields": fields})

    async def list_bitable_records(self) -> list[dict[str, Any]]:
        path = f"/bitable/v1/apps/{settings.bitable_app_token}/tables/{settings.bitable_table_id}/records"
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 500}
            if page_token:
                params["page_token"] = page_token

            data = await self._request("GET", path, params=params)
            block = data.get("data", {})
            all_items.extend(block.get("items", []))
            if not block.get("has_more"):
                break
            page_token = block.get("page_token")
            if not page_token:
                break

        return all_items

    async def list_bitable_fields(self) -> list[dict[str, Any]]:
        path = f"/bitable/v1/apps/{settings.bitable_app_token}/tables/{settings.bitable_table_id}/fields"
        all_items: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 100}
            if page_token:
                params["page_token"] = page_token

            data = await self._request("GET", path, params=params)
            block = data.get("data", {})
            all_items.extend(block.get("items", []))
            if not block.get("has_more"):
                break
            page_token = block.get("page_token")
            if not page_token:
                break

        return all_items
