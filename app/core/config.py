from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "screenshot-ingestion"
    app_env: str = "dev"
    log_level: str = "INFO"

    feishu_app_id: str
    feishu_app_secret: str
    feishu_verification_token: str

    feishu_bitable_app_token: str
    feishu_bitable_table_id: str

    # 可选：用于过滤只处理某个群
    target_chat_id: str | None = None

    request_timeout_seconds: int = 20

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
