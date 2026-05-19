import logging
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env", override=True)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def is_present(value: Any) -> str:
    return "present" if bool(value) else "missing"


def mask_secret(value: Any, visible: int = 4) -> str:
    text = str(value or "")
    if not text:
        return "missing"
    if len(text) <= visible * 2:
        return "***"
    return f"{text[:visible]}...{text[-visible:]}"


def sanitize_log_text(value: Any) -> str:
    text = str(value or "")
    if not text:
        return text
    text = re.sub(r"(bot)([0-9]{6,12}:[A-Za-z0-9_-]{20,})", r"\1***", text)
    text = re.sub(r"([0-9]{6,12}:[A-Za-z0-9_-]{20,})", "***telegram-token***", text)
    text = re.sub(r"(sk-or-v1-[A-Za-z0-9_-]+)", "***openrouter-key***", text)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1***", text, flags=re.I)
    return text


def get_firebase_key_path() -> str:
    configured = (os.getenv("FIREBASE_KEY_PATH") or "").strip()
    if configured:
        return configured
    return str(BASE_DIR / "firebase_key.json")


def require_firebase_key_path() -> str:
    path = get_firebase_key_path()
    if not os.path.isfile(path):
        raise FileNotFoundError(
            "Firebase credential missing. Set FIREBASE_KEY_PATH to a valid service account JSON "
            "or provide Server_Local/firebase_key.json for local development."
        )
    return path


OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "")
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
FIREBASE_KEY_PATH = get_firebase_key_path()
ENABLE_DEBUG_ENDPOINTS = _env_bool("ENABLE_DEBUG_ENDPOINTS", False)
DEBUG_ENDPOINT_TOKEN = os.getenv("DEBUG_ENDPOINT_TOKEN")


def log_startup_config(logger: logging.Logger) -> None:
    logger.warning("[Config] OPENROUTER_API_KEY=%s", is_present(OPENROUTER_API_KEY))
    logger.warning("[Config] BASE_WEBHOOK_URL=%s", is_present(BASE_WEBHOOK_URL))
    logger.warning("[Config] RESEND_API_KEY=%s", is_present(RESEND_API_KEY))
    logger.warning("[Config] FIREBASE_KEY_PATH=%s", is_present(FIREBASE_KEY_PATH))
    logger.warning("[Config] ENABLE_DEBUG_ENDPOINTS=%s", ENABLE_DEBUG_ENDPOINTS)
    if ENABLE_DEBUG_ENDPOINTS:
        logger.warning("[Config] DEBUG_ENDPOINT_TOKEN=%s", is_present(DEBUG_ENDPOINT_TOKEN))
