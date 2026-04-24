from __future__ import annotations

from dataclasses import dataclass
from getpass import getpass
from pathlib import Path


ENV_PATH = Path(".env")


@dataclass(frozen=True)
class EnvPrompt:
    key: str
    label: str
    secret: bool = False


REQUIRED_PROMPTS = [
    EnvPrompt("FEISHU_VERIFICATION_TOKEN", "飞书事件 Verification Token"),
    EnvPrompt("FEISHU_APP_ID", "飞书应用 App ID，例如 cli_xxx"),
    EnvPrompt("FEISHU_APP_SECRET", "飞书应用 App Secret", secret=True),
    EnvPrompt("BITABLE_APP_TOKEN", "多维表 app_token"),
    EnvPrompt("BITABLE_TABLE_ID", "数据表 table_id"),
]

DEFAULT_ENV = {
    "APP_NAME": "feishu-screenshot-ingestion",
    "APP_ENV": "dev",
    "LOG_LEVEL": "INFO",
    "HOST": "0.0.0.0",
    "PORT": "8000",
    "FEISHU_VERIFICATION_TOKEN": "",
    "FEISHU_APP_ID": "",
    "FEISHU_APP_SECRET": "",
    "BITABLE_APP_TOKEN": "",
    "BITABLE_TABLE_ID": "",
    "REQUEST_TIMEOUT_SECONDS": "20",
    "USE_MOCK_OCR": "false",
    "USE_MOCK_BITABLE": "false",
    "USE_LOCAL_OCR_FALLBACK": "true",
    "LOCAL_OCR_PROVIDER": "rapidocr",
    "LOCAL_OCR_FALLBACK_ON_ANY_FEISHU_OCR_ERROR": "false",
}

ENV_ORDER = [
    "APP_NAME",
    "APP_ENV",
    "LOG_LEVEL",
    "HOST",
    "PORT",
    "FEISHU_VERIFICATION_TOKEN",
    "FEISHU_APP_ID",
    "FEISHU_APP_SECRET",
    "BITABLE_APP_TOKEN",
    "BITABLE_TABLE_ID",
    "REQUEST_TIMEOUT_SECONDS",
    "USE_MOCK_OCR",
    "USE_MOCK_BITABLE",
    "USE_LOCAL_OCR_FALLBACK",
    "LOCAL_OCR_PROVIDER",
    "LOCAL_OCR_FALLBACK_ON_ANY_FEISHU_OCR_ERROR",
]


def ensure_env_interactive(*, force: bool = False) -> bool:
    values = {**DEFAULT_ENV, **_read_env_file(ENV_PATH)}
    missing = [prompt for prompt in REQUIRED_PROMPTS if force or _is_missing(values.get(prompt.key, ""))]

    if not missing and ENV_PATH.exists():
        return False

    print("需要配置飞书和多维表参数。输入内容会写入本地 .env，不会提交到 Git。")
    for prompt in missing:
        current = values.get(prompt.key, "")
        value = _prompt_value(prompt, current=current if not _is_placeholder(current) else "")
        values[prompt.key] = value

    _write_env_file(ENV_PATH, values)
    print(f"配置已写入 {ENV_PATH}")
    return True


def missing_required_env_keys() -> list[str]:
    values = {**DEFAULT_ENV, **_read_env_file(ENV_PATH)}
    return [prompt.key for prompt in REQUIRED_PROMPTS if _is_missing(values.get(prompt.key, ""))]


def _prompt_value(prompt: EnvPrompt, *, current: str) -> str:
    while True:
        suffix = "，直接回车保留当前值" if current else ""
        question = f"{prompt.label}{suffix}: "
        raw = getpass(question) if prompt.secret else input(question)
        value = raw.strip() or current.strip()
        if value:
            return value
        print("该项不能为空。")


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = _unquote(value.strip())
    return values


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    lines = [
        "APP_NAME={APP_NAME}",
        "APP_ENV={APP_ENV}",
        "LOG_LEVEL={LOG_LEVEL}",
        "HOST={HOST}",
        "PORT={PORT}",
        "",
        "FEISHU_VERIFICATION_TOKEN={FEISHU_VERIFICATION_TOKEN}",
        "FEISHU_APP_ID={FEISHU_APP_ID}",
        "FEISHU_APP_SECRET={FEISHU_APP_SECRET}",
        "",
        "BITABLE_APP_TOKEN={BITABLE_APP_TOKEN}",
        "BITABLE_TABLE_ID={BITABLE_TABLE_ID}",
        "REQUEST_TIMEOUT_SECONDS={REQUEST_TIMEOUT_SECONDS}",
        "USE_MOCK_OCR={USE_MOCK_OCR}",
        "USE_MOCK_BITABLE={USE_MOCK_BITABLE}",
        "",
        "# 本地 OCR 降级配置",
        "USE_LOCAL_OCR_FALLBACK={USE_LOCAL_OCR_FALLBACK}",
        "LOCAL_OCR_PROVIDER={LOCAL_OCR_PROVIDER}",
        "# false: 仅在 Feishu OCR 限频(99991400)时降级",
        "# true : 任意 Feishu OCR 错误都降级",
        "LOCAL_OCR_FALLBACK_ON_ANY_FEISHU_OCR_ERROR={LOCAL_OCR_FALLBACK_ON_ANY_FEISHU_OCR_ERROR}",
        "",
    ]

    rendered = "\n".join(_render_line(line, values) for line in lines)
    path.write_text(rendered, encoding="utf-8")


def _render_line(line: str, values: dict[str, str]) -> str:
    rendered = line
    for key in ENV_ORDER:
        rendered = rendered.replace("{" + key + "}", _quote_if_needed(values.get(key, DEFAULT_ENV[key])))
    return rendered


def _is_missing(value: str | None) -> bool:
    if value is None:
        return True
    stripped = value.strip()
    return not stripped or _is_placeholder(stripped)


def _is_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return lowered.startswith("your_") or lowered in {"xxx", "changeme", "change_me"}


def _quote_if_needed(value: str) -> str:
    if any(ch.isspace() for ch in value) or "#" in value:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value
