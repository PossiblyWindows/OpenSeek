import json
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class AppConfig:
    token: str
    system_prompt: str
    thinking_enabled: bool
    search_enabled: bool
    base_url: str = "https://chat.deepseek.com/api/v0"


def load_config() -> AppConfig:
    token = os.getenv("token", "").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()

    if not token or token in ("YOUR_TOKEN", "YOUR_DEEPSEEK_TOKEN_HERE", "ВАШ_ТОКЕН"):
        raise ValueError("DeepSeek token is not configured in the .env file.")

    system_prompt = ""
    thinking_enabled = False
    search_enabled = False

    config_path = ROOT_DIR / "config.json"
    if config_path.is_file():
        try:
            with open(config_path, "r", encoding="utf-8") as file_handle:
                config_json = json.load(file_handle)
                system_prompt = config_json.get("system-prompt", "")
                thinking_enabled = bool(config_json.get("thinking_enabled", False))
                search_enabled = bool(config_json.get("search_enabled", False))
        except (json.JSONDecodeError, OSError):
            pass

    return AppConfig(
        token=token,
        system_prompt=system_prompt,
        thinking_enabled=thinking_enabled,
        search_enabled=search_enabled,
    )


def get_default_headers(token: str) -> dict[str, str]:
    return {
        "accept": "*/*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://chat.deepseek.com",
        "referer": "https://chat.deepseek.com/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "x-client-bundle-id": "com.deepseek.chat",
        "x-client-locale": "en_US",
        "x-client-platform": "web",
        "x-client-timezone-offset": "10800",
        "x-client-version": "2.5.0",
    }
