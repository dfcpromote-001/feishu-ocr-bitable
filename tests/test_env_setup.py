from pathlib import Path

from app.config import env_setup


def test_read_env_treats_placeholders_as_missing(tmp_path: Path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FEISHU_VERIFICATION_TOKEN=your_feishu_verification_token",
                "FEISHU_APP_ID=cli_xxx",
                "FEISHU_APP_SECRET=your_feishu_app_secret",
                "BITABLE_APP_TOKEN=app_token",
                "BITABLE_TABLE_ID=table_id",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(env_setup, "ENV_PATH", env_path)

    missing = env_setup.missing_required_env_keys()

    assert "FEISHU_VERIFICATION_TOKEN" in missing
    assert "FEISHU_APP_SECRET" in missing
    assert "BITABLE_APP_TOKEN" not in missing
    assert "BITABLE_TABLE_ID" not in missing


def test_write_env_file_preserves_required_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    values = {
        **env_setup.DEFAULT_ENV,
        "FEISHU_VERIFICATION_TOKEN": "token",
        "FEISHU_APP_ID": "cli_123",
        "FEISHU_APP_SECRET": "secret",
        "BITABLE_APP_TOKEN": "base_token",
        "BITABLE_TABLE_ID": "tbl_123",
    }

    env_setup._write_env_file(env_path, values)

    written = env_path.read_text(encoding="utf-8")
    assert "FEISHU_VERIFICATION_TOKEN=token" in written
    assert "FEISHU_APP_ID=cli_123" in written
    assert "FEISHU_APP_SECRET=secret" in written
    assert "BITABLE_APP_TOKEN=base_token" in written
    assert "BITABLE_TABLE_ID=tbl_123" in written
    assert "USE_MOCK_OCR=false" in written
