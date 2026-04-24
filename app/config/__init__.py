from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "feishu-screenshot-ingestion"
    app_env: str = "dev"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000

    feishu_verification_token: str = ""
    feishu_app_id: str = ""
    feishu_app_secret: str = ""

    bitable_app_token: str = ""
    bitable_table_id: str = ""

    request_timeout_seconds: int = 20
    use_mock_ocr: bool = True
    use_mock_bitable: bool = True

    # 本地 OCR 降级配置
    use_local_ocr_fallback: bool = True
    local_ocr_provider: str = "rapidocr"
    local_ocr_fallback_on_any_feishu_ocr_error: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()


def reload_settings() -> Settings:
    global settings
    settings = Settings()
    return settings
