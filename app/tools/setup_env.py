from app.config import reload_settings
from app.config.env_setup import ensure_env_interactive, missing_required_env_keys


def main() -> None:
    before = missing_required_env_keys()
    ensure_env_interactive(force=True)
    reload_settings()
    after = missing_required_env_keys()

    if after:
        print("仍缺少必要配置：" + ", ".join(after))
        raise SystemExit(1)

    if before:
        print("必要配置已补全。")
    else:
        print("配置已更新。")


if __name__ == "__main__":
    main()
