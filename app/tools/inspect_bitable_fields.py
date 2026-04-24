import asyncio
import json

from app.clients.feishu_client import FeishuClient
from app.config import settings


async def main() -> None:
    client = FeishuClient()
    fields = await client.list_bitable_fields()

    print(f"app_token={settings.bitable_app_token}")
    print(f"table_id={settings.bitable_table_id}")
    print("fields:")
    for field in fields:
        print(
            json.dumps(
                {
                    "field_name": field.get("field_name"),
                    "field_id": field.get("field_id"),
                    "type": field.get("type"),
                    "is_primary": field.get("is_primary"),
                    "options": [
                        option.get("name")
                        for option in field.get("property", {}).get("options", [])
                        if isinstance(option, dict)
                    ],
                },
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
