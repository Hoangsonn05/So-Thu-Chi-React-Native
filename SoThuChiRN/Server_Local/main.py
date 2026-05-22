import os
import re
import unicodedata
import time
import json
import tempfile
import traceback
import logging
import resend
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import firebase_admin
import pandas as pd
import uvicorn
import requests
from openpyxl.styles import Border, Font, Side
from openpyxl.utils import get_column_letter
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Response, Header
from contextlib import asynccontextmanager
from firebase_admin import credentials, firestore, messaging
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from runtime_config import (
    BASE_WEBHOOK_URL,
    DEBUG_ENDPOINT_TOKEN,
    ENABLE_DEBUG_ENDPOINTS,
    FIREBASE_KEY_PATH,
    OPENROUTER_API_KEY,
    RESEND_API_KEY,
    is_present,
    log_startup_config,
    require_firebase_key_path,
    sanitize_log_text,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Load environment variables from .env file in the same directory (with override)
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("sothuchi.backend")

# --- CẤU HÌNH RESEND (Gửi Email) ---
resend.api_key = RESEND_API_KEY

# --- CẤU HÌNH WEBHOOK (Động cho từng User) ---
log_startup_config(logger)

# --- CẤU HÌNH AI (OPENROUTER - THAY THẾ GEMINI) ---
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-super-120b-a12b:free"

# Multi transaction parsing is high-risk; keep disabled by default.
ENABLE_MULTI_TRANSACTION_PARSE = os.getenv("ENABLE_MULTI_TRANSACTION_PARSE", "false").strip().lower() in {"1", "true", "yes", "on"}
MAX_MULTI_TRANSACTIONS = 5

# Merchant Learning System — giảm gọi AI cho merchant quen thuộc
# Mặc định false: behavior hiện tại không đổi khi chưa bật
ENABLE_MERCHANT_LEARNING = os.getenv("ENABLE_MERCHANT_LEARNING", "false").strip().lower() in {"1", "true", "yes", "on"}
# Bypass AI cho single-tx khi merchant rule đủ chắc (chỉ có hiệu lực khi ENABLE_MERCHANT_LEARNING=true)
# Mặc định false: chỉ học rule, không bypass AI
ENABLE_MERCHANT_BYPASS = os.getenv("ENABLE_MERCHANT_BYPASS", "false").strip().lower() in {"1", "true", "yes", "on"}

# --- TIMEZONE Việt Nam (UTC+7) ---
VN_TZ = timezone(timedelta(hours=7))

# --- IN-MEMORY CACHE: bot_token → firebase_uid ---
# Giúp xác định xem bot token nhận được thuộc về user nào
_bot_token_to_uid_cache: dict[str, str] = {}

# --- DANH MỤC HỢP LỆ (1:1 từ categories.ts trong app) ---
EXPENSE_CATEGORIES = [
    "Ăn uống", "Chi tiêu", "Quần áo", "Mỹ phẩm", "Giao lưu",
    "Y tế", "Giáo dục", "Tiền điện", "Du lịch", "Liên lạc", "Tiền nhà", "Khác",
]
INCOME_CATEGORIES = [
    "Tiền lương", "Tiền phụ cấp", "Tiền thưởng", "Thu nhập phụ",
    "Đầu tư", "Thu nhập tạm", "Khác",
]

CATEGORY_EMOJIS = {
    "Ăn uống": "🍜", "Chi tiêu": "🛒", "Quần áo": "👕", "Mỹ phẩm": "💄",
    "Giao lưu": "🍻", "Y tế": "🏥", "Giáo dục": "📚", "Tiền điện": "⚡",
    "Du lịch": "✈️", "Liên lạc": "📱", "Tiền nhà": "🏠",
    "Tiền lương": "💵", "Tiền phụ cấp": "💰", "Tiền thưởng": "🎁",
    "Thu nhập phụ": "➕", "Đầu tư": "📈", "Thu nhập tạm": "🔄",
    "Khác": "📦",
}

# --- SYSTEM PROMPT CHO AI (ENGLISH — enforces exact app schema) ---
AI_SYSTEM_PROMPT = """You are a strict financial data extraction engine for a Vietnamese personal finance app called "Sổ Thu Chi".
Your ONLY job is to parse the user's Vietnamese text message and extract financial transaction details into a JSON object.

## RULES — FOLLOW EXACTLY:
1. Output ONLY a single raw JSON object. No markdown, no code fences, no explanation, no extra text.
2. The JSON must have EXACTLY these fields:
   - "type": integer. 0 for expense (chi), 1 for income (thu). Default to 0 if ambiguous.
   - "amount": integer. The monetary amount in VND. Parse Vietnamese shorthand: "k" or "K" = multiply by 1,000; "tr" or "triệu" = multiply by 1,000,000; "tỷ" = multiply by 1,000,000,000. The amount must always be a positive integer.
   - "category": string. Must be EXACTLY one of the allowed categories listed below. Choose the most appropriate one based on context.
   - "note": string. A concise Vietnamese description of the transaction, summarizing what the user said. Maximum 50 characters.
   - "date": string. Format "dd/MM/yyyy". If the user specifies a date, use it. If they say "hôm nay" or "nay", use today's date. If they say "hôm qua", use yesterday. If no date is mentioned, use today's date. Today's date is: {current_date}.
   - "source": string. The origin of the transaction. Extract from context or package name (e.g., "Momo", "ZaloPay", "Techcombank", "Vietcombank"). If it's a manual message and no specific bank/wallet is mentioned, output "Tiền mặt".

## ALLOWED EXPENSE CATEGORIES (type=0):
"Ăn uống", "Chi tiêu", "Quần áo", "Mỹ phẩm", "Giao lưu", "Y tế", "Giáo dục", "Tiền điện", "Du lịch", "Liên lạc", "Tiền nhà", "Khác"

## ALLOWED INCOME CATEGORIES (type=1):
"Tiền lương", "Tiền phụ cấp", "Tiền thưởng", "Thu nhập phụ", "Đầu tư", "Thu nhập tạm", "Khác"

## CATEGORY SELECTION GUIDELINES:
- Food, drinks, meals, snacks, coffee → "Ăn uống"
- Shopping, groceries, daily necessities → "Chi tiêu"
- Clothing, shoes, accessories → "Quần áo"
- Cosmetics, skincare, beauty → "Mỹ phẩm"
- Socializing, parties, hangouts, gifts for friends → "Giao lưu"
- Medicine, hospital, doctor, health → "Y tế"
- Books, courses, tuition, school fees → "Giáo dục"
- Electricity, water, internet, utility bills → "Tiền điện"
- Travel, vacation, transportation, gas, fuel, taxi, grab → "Du lịch"
- Phone bills, mobile top-up → "Liên lạc"
- Rent, housing costs → "Tiền nhà"
- Salary, wages → "Tiền lương"
- Allowance, stipend → "Tiền phụ cấp"
- Bonus → "Tiền thưởng"
- Side income, freelance → "Thu nhập phụ"
- Investment returns → "Đầu tư"
- Temporary income, refunds → "Thu nhập tạm"
- Anything else → "Khác"

## IMPORTANT:
- Always respond in Vietnamese for the "note" and "category" fields.
- Today is {current_date}.
"""


if not firebase_admin._apps:
    cred = credentials.Certificate(require_firebase_key_path())
    firebase_admin.initialize_app(cred)

db = firestore.client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from agentic_ai import (
        ensure_default_scheduled_tasks_job,
        poll_scheduled_tasks_job,
        recurring_expenses_daily_job,
    )
    scheduler = AsyncIOScheduler()
    # Chạy polling mỗi 1 phút
    scheduler.add_job(poll_scheduled_tasks_job, 'interval', minutes=1)
    scheduler.add_job(
        ensure_default_scheduled_tasks_job,
        'interval',
        minutes=5,
        next_run_time=datetime.now(tz=VN_TZ),
    )
    scheduler.add_job(recurring_expenses_daily_job, 'cron', hour=9, minute=0, timezone=VN_TZ)
    scheduler.start()
    logger.info("[Scheduler] startup status=started poll_interval=60s timezone=Asia/Saigon")
    yield
    scheduler.shutdown()

app = FastAPI(title="Firestore Export & Telegram Bot API", lifespan=lifespan)


SENSITIVE_FIELD_NAMES = {
    "bottoken",
    "fcmtoken",
    "fcm_token",
    "api_key",
    "apikey",
    "authorization",
    "token",
    "access_token",
    "refresh_token",
    "debug_endpoint_token",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _sanitize_debug_value(value: Any, key: str = "") -> Any:
    normalized_key = re.sub(r"[^a-z0-9_]+", "", str(key).lower())
    if normalized_key in SENSITIVE_FIELD_NAMES or normalized_key.endswith("token"):
        return "[REDACTED]" if value else None
    if isinstance(value, dict):
        return {str(k): _sanitize_debug_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_debug_value(item, key) for item in value]
    if isinstance(value, str):
        if "api.telegram.org/bot" in value.lower():
            return sanitize_log_text(value)
        return sanitize_log_text(value)
    return _json_safe(value)


def _require_debug_token(x_debug_token: Optional[str]) -> None:
    if not DEBUG_ENDPOINT_TOKEN:
        raise HTTPException(status_code=503, detail="debug_not_configured")
    if not x_debug_token or x_debug_token != DEBUG_ENDPOINT_TOKEN:
        raise HTTPException(status_code=401, detail="invalid_debug_token")


if ENABLE_DEBUG_ENDPOINTS:
    @app.post("/api/debug/run-scheduler-once")
    async def debug_run_scheduler_once(
        request: Request,
        x_debug_token: Optional[str] = Header(default=None, alias="X-Debug-Token"),
    ):
        _require_debug_token(x_debug_token)
        raw_body = await request.body()
        body = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        uid_filter = (body or {}).get("uid")
        task_id_filter = (body or {}).get("task_id")
        from agentic_ai import _collect_due_scheduled_tasks, _scheduler_now_utc, execute_scheduled_task

        now_utc = _scheduler_now_utc()
        outcomes = []
        if task_id_filter:
            snap = db.collection("scheduled_tasks").document(str(task_id_filter)).get()
            if not snap.exists:
                return {"status": "ok", "due_count": 0, "outcomes": [{"task_id": task_id_filter, "status": "skipped", "reason": "not_found"}]}
            task_data = snap.to_dict() or {}
            if uid_filter and task_data.get("uid") != uid_filter:
                return {"status": "ok", "due_count": 0, "outcomes": [{"task_id": task_id_filter, "status": "skipped", "reason": "uid_mismatch"}]}
            outcomes.append({"task_id": task_id_filter, **execute_scheduled_task(str(task_id_filter), task_data)})
        else:
            due_tasks = _collect_due_scheduled_tasks(db, now_utc)
            if uid_filter:
                due_tasks = [(task_id, task) for task_id, task in due_tasks if task.get("uid") == uid_filter]
            for task_id, task_data in due_tasks:
                outcomes.append({"task_id": task_id, **execute_scheduled_task(task_id, task_data)})
        return _sanitize_debug_value({"status": "ok", "due_count": len(outcomes), "outcomes": outcomes})

    @app.post("/api/debug/create-test-task")
    async def debug_create_test_task(
        request: Request,
        x_debug_token: Optional[str] = Header(default=None, alias="X-Debug-Token"),
    ):
        _require_debug_token(x_debug_token)
        body = await request.json()
        uid = str((body or {}).get("uid") or "").strip()
        task_type = str((body or {}).get("task_type") or "daily_finance_report").strip()
        schedule_type = str((body or {}).get("schedule_type") or "daily").strip()
        time_value = str((body or {}).get("time") or "20:00").strip()
        if not uid:
            raise HTTPException(status_code=400, detail="uid_required")

        from agentic_ai import (
            DEFAULT_TIMEZONE,
            FINANCE_REPORT_TASK_TYPES,
            EXTERNAL_BRIEF_TASK_TYPES,
            calculate_next_run_at,
        )

        allowed_types = FINANCE_REPORT_TASK_TYPES | EXTERNAL_BRIEF_TASK_TYPES
        if task_type not in allowed_types:
            raise HTTPException(status_code=400, detail="unsupported_task_type")
        if schedule_type not in {"default_daily", "daily", "weekly", "monthly", "once"}:
            raise HTTPException(status_code=400, detail="unsupported_schedule_type")

        now_utc = datetime.now(timezone.utc)
        task_id = f"debug_{uid}_{task_type}_{int(now_utc.timestamp())}"
        task = {
            "uid": uid,
            "task_type": task_type,
            "schedule_type": schedule_type,
            "status": "active" if schedule_type != "once" else "pending",
            "timezone": str((body or {}).get("timezone") or DEFAULT_TIMEZONE),
            "time": time_value,
            "last_run_at": None,
            "last_success_at": None,
            "retry_count": 0,
            "payload": dict((body or {}).get("payload") or {}),
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
            "debug": True,
        }
        if (body or {}).get("next_run_now", True):
            task["next_run_at"] = now_utc
        else:
            task["next_run_at"] = calculate_next_run_at(task, now_utc)
        db.collection("scheduled_tasks").document(task_id).set(task, merge=False)
        return _sanitize_debug_value({"status": "ok", "task_id": task_id, "task": task})

    @app.get("/api/debug/user-report-state/{uid}")
    async def debug_user_report_state(
        uid: str,
        x_debug_token: Optional[str] = Header(default=None, alias="X-Debug-Token"),
    ):
        _require_debug_token(x_debug_token)
        from agentic_ai import DEFAULT_TIMEZONE, EXTERNAL_BRIEF_TASK_TYPES, FINANCE_REPORT_TASK_TYPES, get_date_key, get_vn_now
        from external_cache import EXTERNAL_SNAPSHOTS_COLLECTION

        date_key = get_date_key(get_vn_now(), DEFAULT_TIMEZONE)
        scheduled_tasks = []
        for snap in db.collection("scheduled_tasks").where("uid", "==", uid).stream():
            scheduled_tasks.append({"id": snap.id, **(snap.to_dict() or {})})

        delivery_state = []
        for snap in db.collection("users").document(uid).collection("delivery_state").stream():
            data = snap.to_dict() or {}
            if data.get("date_key") == date_key:
                delivery_state.append({"id": snap.id, **data})

        finance_reports = []
        for snap in db.collection("users").document(uid).collection("finance_reports").limit(10).stream():
            finance_reports.append({"id": snap.id, **(snap.to_dict() or {})})

        external_reports = []
        for snap in db.collection("users").document(uid).collection("external_reports").limit(10).stream():
            external_reports.append({"id": snap.id, **(snap.to_dict() or {})})

        external_snapshots = []
        for topic in {"gold", "fuel", "usd_vnd", "ai_pricing"}:
            snap = db.collection(EXTERNAL_SNAPSHOTS_COLLECTION).document(f"{topic}_{date_key}").get()
            if snap.exists:
                external_snapshots.append({"id": snap.id, **(snap.to_dict() or {})})

        payload = {
            "uid": uid,
            "date_key": date_key,
            "scheduled_tasks": scheduled_tasks,
            "delivery_state": delivery_state,
            "finance_reports": finance_reports,
            "external_reports": external_reports,
            "external_snapshots": external_snapshots,
            "known_task_types": sorted(FINANCE_REPORT_TASK_TYPES | EXTERNAL_BRIEF_TASK_TYPES),
        }
        return _sanitize_debug_value(payload)

def process_agentic_query(bot_token: str, firebase_uid: str, chat_id: int, text: str):
    """ Xử lý Agentic AI Workflow cho các câu truy vấn báo cáo tài chính """
    from agentic_ai import (
        chat_with_agentic_ai,
        create_custom_finance_report_task,
        disable_finance_reports,
        handle_manual_external_report_request,
        list_finance_report_tasks,
        send_manual_report,
        stop_custom_finance_reports,
        EXTERNAL_BRIEF_TASK_TYPES,
    )
    try:
        print(f"[Agentic] Bắt đầu xử lý truy vấn cho UID: {firebase_uid}")
        intent_text = _normalize_intent_text(text)
        if _is_disable_report_schedule_request(intent_text):
            scope = "all" if any(k in intent_text for k in ["tat bao cao tu dong", "tat lich bao cao"]) else "custom_only"
            send_telegram_message(bot_token, chat_id, disable_finance_reports(firebase_uid, scope))
            return
        if _is_list_report_schedule_request(intent_text):
            send_telegram_message(bot_token, chat_id, list_finance_report_tasks(firebase_uid))
            return
        deterministic_schedule_match = re.search(r"(?:luc|lúc)\s*(\d{1,2})(?::?([0-5]\d))?\s*h?", intent_text)
        if deterministic_schedule_match and _is_finance_report_schedule_request(intent_text):
            hour = int(deterministic_schedule_match.group(1))
            minute = int(deterministic_schedule_match.group(2) or 0)
            report_type = "expense_report" if "chi tieu" in intent_text else "daily_finance_report"
            if any(k in intent_text for k in ["moi thang", "hang thang", "thang", "monthly"]):
                schedule_type = "monthly"
                timeframe = "current_month"
            elif any(k in intent_text for k in ["moi tuan", "hang tuan", "tuan", "weekly"]):
                schedule_type = "weekly"
                timeframe = "current_week"
            else:
                schedule_type = "daily"
                timeframe = "today"
            result = create_custom_finance_report_task(firebase_uid, f"{hour:02d}:{minute:02d}", schedule_type, report_type, timeframe)
            send_telegram_message(bot_token, chat_id, json.loads(result).get("message", "Da len lich bao cao."))
            return
        manual_external_type = _detect_manual_report_task_type(text)
        if manual_external_type in EXTERNAL_BRIEF_TASK_TYPES:
            force_refresh = any(k in intent_text for k in ["refresh", "cap nhat moi", "lay moi", "moi nhat"])
            handle_manual_external_report_request(firebase_uid, manual_external_type, source="telegram", force_refresh=force_refresh)
            return
        schedule_match = re.search(r"(?:luc|lúc)\s*(\d{1,2})(?::?([0-5]\d))?\s*h?", intent_text)
        if any(k in intent_text for k in ["huy lich bao cao", "hủy lịch báo cáo", "stopreport"]):
            send_telegram_message(bot_token, chat_id, stop_custom_finance_reports(firebase_uid))
            return
        if any(k in intent_text for k in ["xem lich bao cao", "lich bao cao", "myreports"]):
            send_telegram_message(bot_token, chat_id, list_finance_report_tasks(firebase_uid))
            return
        if schedule_match and "bao cao" in intent_text and any(k in intent_text for k in ["tai chinh", "chi tieu"]):
            hour = int(schedule_match.group(1))
            minute = int(schedule_match.group(2) or 0)
            report_type = "expense_report" if "chi tieu" in intent_text else "daily_finance_report"
            if any(k in intent_text for k in ["moi thang", "hang thang", "thang", "monthly"]):
                schedule_type = "monthly"
                timeframe = "current_month"
            elif any(k in intent_text for k in ["moi tuan", "hang tuan", "tuan", "weekly"]):
                schedule_type = "weekly"
                timeframe = "current_week"
            else:
                schedule_type = "daily"
                timeframe = "today"
            result = create_custom_finance_report_task(firebase_uid, f"{hour:02d}:{minute:02d}", schedule_type, report_type, timeframe)
            send_telegram_message(bot_token, chat_id, json.loads(result).get("message", "Da len lich bao cao."))
            return
        manual_task_type = _detect_manual_report_task_type(text)
        if manual_task_type:
            print(f"[Agentic] Manual report task detected: uid={firebase_uid}, task={manual_task_type}")
            if manual_task_type in EXTERNAL_BRIEF_TASK_TYPES:
                handle_manual_external_report_request(firebase_uid, manual_task_type, source="telegram")
            else:
                send_manual_report(firebase_uid, manual_task_type)
            return
        reply = chat_with_agentic_ai(text, firebase_uid)
        if reply:
            send_telegram_message(bot_token, chat_id, reply)
        else:
            send_telegram_message(bot_token, chat_id, "Xin lỗi, tôi không thể truy xuất thông tin lúc này.")
    except Exception as e:
        print(f"[Agentic Error] {e}")
        traceback.print_exc()
        send_telegram_message(bot_token, chat_id, "Đã có lỗi xảy ra khi xử lý yêu cầu của bạn.")


def _detect_manual_report_task_type_legacy(text: str) -> Optional[str]:
    lower_text = (text or "").strip().lower()
    if not lower_text:
        return None
    wants_report = any(k in lower_text for k in ["báo cáo", "bao cao", "bản tin", "ban tin", "tóm tắt", "tom tat"])
    if any(k in lower_text for k in ["giá vàng", "gia vang", "vàng hôm nay", "vang hom nay"]):
        return "gold_price_brief"
    if any(k in lower_text for k in ["giá xăng", "gia xang", "xăng dầu", "xang dau", "nhiên liệu", "nhien lieu"]):
        return "fuel_price_brief"
    if wants_report and any(k in lower_text for k in ["giá ai", "gia ai", "openai", "chatgpt", "claude", "gemini"]):
        return "ai_price_brief"
    if wants_report and any(k in lower_text for k in ["buổi sáng", "buoi sang", "morning", "dữ liệu ngoài", "du lieu ngoai"]):
        return "morning_external_brief"
    if wants_report and any(k in lower_text for k in ["tuần", "tuan", "weekly"]):
        return "weekly_finance_report"
    if wants_report and any(k in lower_text for k in ["tháng", "thang", "monthly"]):
        return "monthly_finance_report"
    if wants_report and any(k in lower_text for k in ["hôm nay", "hom nay", "ngày", "ngay", "daily", "chi tiêu", "chi tieu", "tài chính", "tai chinh"]):
        return "daily_finance_report"
    return None


def _normalize_intent_text(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text or "")
    without_accents = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", without_accents.lower()).strip()


def _detect_manual_report_task_type(text: str) -> Optional[str]:
    lower_text = _normalize_intent_text(text)
    if not lower_text:
        return None
    wants_report = any(k in lower_text for k in ["bao cao", "ban tin", "tom tat", "brief"])
    if any(k in lower_text for k in ["gia vang", "vang hom nay", "sjc", "pnj"]):
        return "gold_price_brief"
    if any(k in lower_text for k in ["gia xang", "xang dau"]):
        return "fuel_price_brief"
    if any(k in lower_text for k in ["gia ai", "goi ai", "gia gpt", "gpt", "openai", "chatgpt", "gemini", "deepseek"]):
        return "ai_price_brief"
    if any(k in lower_text for k in [
        "bao cao sang", "sang nay", "morning", "morning brief",
        "du lieu ngoai", "tai chinh ngoai", "thi truong",
    ]) and wants_report:
        return "morning_external_brief"
    if wants_report and any(k in lower_text for k in ["tuan", "weekly"]):
        return "weekly_finance_report"
    if wants_report and any(k in lower_text for k in ["thang", "monthly"]):
        return "monthly_finance_report"
    if wants_report and any(k in lower_text for k in ["hom nay", "ngay", "daily", "chi tieu", "tai chinh"]):
        return "daily_finance_report"
    return None


def _is_disable_report_schedule_request(lower_text: str) -> bool:
    return any(k in lower_text for k in [
        "huy lich bao cao", "tat bao cao tu dong", "dung bao cao tu dong",
        "stopreport", "tat lich bao cao", "bo lich bao cao",
    ])


def _is_list_report_schedule_request(lower_text: str) -> bool:
    return any(k in lower_text for k in [
        "xem lich bao cao", "lich bao cao", "myreports", "danh sach lich",
    ]) and not _is_disable_report_schedule_request(lower_text)


def _is_finance_report_schedule_request(lower_text: str) -> bool:
    has_report = "bao cao" in lower_text
    has_schedule = any(k in lower_text for k in [
        "len lich", "dat lich", "moi ngay luc", "hang ngay luc", "hang ngay",
        "cuoi ngay", "moi tuan", "hang tuan", "moi thang", "hang thang",
    ])
    return has_report and has_schedule and not _is_disable_report_schedule_request(lower_text)


def _is_budget_alert_request(lower_text: str) -> bool:
    return any(k in lower_text for k in [
        "dat ngan sach", "dat han muc", "han muc chi tieu", "gioi han chi tieu",
        "canh bao ngan sach", "bao khi tieu qua", "nguong canh bao",
    ])


def _is_finance_query_request(lower_text: str) -> bool:
    return any(k in lower_text for k in [
        "bao cao tai chinh", "hom nay tieu bao nhieu", "thang nay chi bao nhieu",
        "thang nay tieu bao nhieu", "tuan nay tieu bao nhieu", "tong chi",
        "tong thu", "bao nhieu", "thong ke", "top giao dich", "giao dich lon",
        "so voi thang truoc", "so voi tuan truoc", "xu huong danh muc",
    ])


def _is_simple_ai_greeting(text: str) -> bool:
    normalized = _normalize_intent_text(text)
    return normalized in {"xin chao", "chao", "hello", "hi", "hey", "helo"}


def _looks_like_transaction_text(text: str) -> bool:
    normalized = _normalize_intent_text(text)
    if extract_amount_vnd(text) is not None:
        return True
    money_pattern = r"\b\d+(?:[.,]\d+)?\s*(?:k|nghin|ngan|tr|trieu|ty|vnd|d|dong)\b"
    if re.search(money_pattern, normalized, re.I):
        return True
    transaction_words = {
        "mua", "an", "uong", "tra", "thanh toan", "chuyen khoan", "nhan",
        "luong", "thuong", "nap", "rut", "xang", "grab", "coffee", "cafe",
    }
    has_action = any(word in normalized for word in transaction_words)
    has_digit = bool(re.search(r"\d", normalized))
    return has_action and has_digit


def _app_transaction_response(parsed: dict, doc_id: Optional[str]) -> dict:
    tx_type = int(parsed.get("type", 0) or 0)
    amount = int(parsed.get("amount", 0) or 0)
    category = str(parsed.get("category", "Khác"))
    note = str(parsed.get("note", ""))
    date_str = str(parsed.get("date", ""))
    type_label = "thu" if tx_type == 1 else "chi"
    return {
        "success": True,
        "message": f"Đã ghi nhận {type_label} {amount:,}đ cho {category}.".replace(",", "."),
        "intent": "transaction",
        "transaction": {
            "type": tx_type,
            "amount": amount,
            "category": category,
            "note": note,
            "date": date_str,
            "source": str(parsed.get("source", "Tiền mặt")),
        },
        "transaction_id": doc_id,
    }


def parse_and_save_transaction_for_app(firebase_uid: str, message: str) -> dict:
    if not firebase_uid:
        return {
            "success": False,
            "message": "Bạn cần đăng nhập để dùng Trợ Lý AI.",
            "intent": "transaction",
            "transaction": None,
            "transaction_id": None,
        }
    parsed = analyze_text_with_gemini(message)
    if parsed == "ERROR_TIMEOUT":
        raise RuntimeError("openrouter_timeout")
    firestore_data = _build_firestore_payload(parsed, firebase_uid)
    doc_id = _save_transaction_atomic(firebase_uid, firestore_data, "appai")

    try:
        _send_fcm_notification(firebase_uid, doc_id, parsed)
    except Exception as fcm_err:
        print(f"[AI Assistant] FCM non-critical error uid={firebase_uid}: {sanitize_log_text(fcm_err)}")

    if parsed.get("type") == 0:
        try:
            from agentic_ai import check_budget_thresholds
            check_budget_thresholds(firebase_uid, parsed.get("category", "Khác"), float(parsed.get("amount", 0)))
        except Exception as budget_err:
            print(f"[AI Assistant] Budget check non-critical error uid={firebase_uid}: {sanitize_log_text(budget_err)}")

    return _app_transaction_response(parsed, doc_id)


class ExportEmailRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    userEmail: str = Field(..., min_length=1)

class NotificationProcessRequest(BaseModel):
    firebase_uid: str
    title: str
    text: str
    package_name: str


class AIAssistantRequest(BaseModel):
    firebase_uid: Optional[str] = None
    message: str = ""
    mode: str = "auto"


def map_package_to_source(package_name: str) -> str:
    normalized = str(package_name or "").strip().lower()
    package_sources = {
        "com.mservice.momotransfer": "Momo",
        "vn.com.vng.zalopay": "ZaloPay",
        "com.mbmobile": "MB Bank",
        "com.tecb.smartbanking": "Techcombank",
        "vn.com.techcombank.bb.app": "Techcombank",
        "com.bidv.smartbanking": "BIDV",
        "com.vnpay.bidv": "BIDV",
        "com.vnpay.wallet": "VNPay",
        "com.vietcombank.smartbanking": "Vietcombank",
        "com.vtb.smartbanking": "VietinBank",
        "com.tpb.mb.gprsandroid": "TPBank",
        "com.ftg.vims": "Viettel Money",
    }
    return package_sources.get(normalized, "")


def _apply_auto_notification_source(parsed: dict, package_name: Optional[str]) -> dict:
    current_source = str(parsed.get("source") or "").strip()
    generic_sources = {"tiền mặt", "tien mat", "cash"}
    if current_source and current_source.lower() not in generic_sources:
        return parsed

    fallback_source = map_package_to_source(package_name or "") or str(package_name or "").strip()
    if fallback_source:
        return {**parsed, "source": fallback_source}
    return parsed


_AUTO_GD_MONEY_RE = re.compile(
    r"\bgd\s*:\s*([+-])\s*([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)\s*(?:vnd|đ|₫|d)",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_SIGNED_MONEY_RE = re.compile(
    r"(?<![A-Za-z0-9])([+-])\s*([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)\s*(?:vnd|đ|₫|d)",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_MONEY_RE = re.compile(
    r"(?<![A-Za-z0-9])([0-9]{1,3}(?:[.,][0-9]{3})+|[0-9]+)\s*(?:vnd|đ|₫|d)",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_NOTE_MARKER_RE = re.compile(
    r"(?:\bnd\b|noi\s*dung|nội\s*dung|message|remark|description)\s*:\s*(.+)",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_MESSAGE_MARKER_RE = re.compile(
    r"(?:k[eè]m\s+)?l[ờơ]i\s+nh[ắa]n\s*:\s*(.+)",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_MOMO_SENDER_RE = re.compile(
    r"nh[ậa]n\s+ti[ềe]n(?:\s+chuy[ểe]n\s+kho[ảa]n)?\s+t[ừu]\s+(.+)$",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_MB_SENDER_RE = re.compile(r"\btu\s*:\s*([^|]+)", re.IGNORECASE)
_AUTO_FT_REF_RE = re.compile(r"\bFT\d{6,}\b", re.IGNORECASE)
_AUTO_TRAILING_REF_RE = re.compile(r"\s+\b[A-Za-z][A-Za-z0-9]{4,}/\d{4,}\b\s*$")
_AUTO_BALANCE_RE = re.compile(
    r"(?:\bsd\b|số\s*dư|so\s*du)\s*:\s*[^|.;]*(?:vnd|đ|d)?",
    re.IGNORECASE | re.UNICODE,
)
_AUTO_MASKED_ACCOUNT_RE = re.compile(r"\b(?:tk\s*)?\d{1,5}x{2,}\d{0,5}\b", re.IGNORECASE)
_AUTO_LONG_NUMBER_RE = re.compile(r"\b\d{6,}\b")


def _auto_today_str() -> str:
    return datetime.now(tz=VN_TZ).strftime("%d/%m/%Y")


def _money_token_to_int(value: str) -> Optional[int]:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    amount = int(digits)
    return amount if amount > 0 else None


def _parse_auto_amount_and_type(text: str) -> tuple[Optional[int], Optional[int], set[str]]:
    gd_match = _AUTO_GD_MONEY_RE.search(text or "")
    if gd_match:
        return _money_token_to_int(gd_match.group(2)), 1 if gd_match.group(1) == "+" else 0, {"amount", "type"}

    signed_match = _AUTO_SIGNED_MONEY_RE.search(text or "")
    if signed_match:
        return (
            _money_token_to_int(signed_match.group(2)),
            1 if signed_match.group(1) == "+" else 0,
            {"amount", "type"},
        )

    money_match = _AUTO_MONEY_RE.search(text or "")
    amount = _money_token_to_int(money_match.group(1)) if money_match else None
    normalized = _normalize_intent_text(text or "")
    expense_keywords = (
        "bi tru", "ghi no", "thanh toan", "da chuyen", "chuyen tien",
        "chuyen khoan den", " den:", "den:", "gd:-",
    )
    income_keywords = (
        "nhan tien", "chuyen khoan tu", "ghi co", "cong tien",
        " nhan", " tu:", " tu ", "gd:+",
    )
    tx_type: Optional[int] = None
    if any(keyword in normalized for keyword in expense_keywords):
        tx_type = 0
    elif any(keyword in normalized for keyword in income_keywords):
        tx_type = 1
    return amount, tx_type, set()


def sanitize_transaction_note(note: str) -> str:
    clean = str(note or "")
    clean = _AUTO_BALANCE_RE.sub(" ", clean)
    clean = _AUTO_FT_REF_RE.sub(" ", clean)
    clean = _AUTO_TRAILING_REF_RE.sub(" ", clean)
    clean = _AUTO_MASKED_ACCOUNT_RE.sub(" ", clean)
    clean = _AUTO_LONG_NUMBER_RE.sub(" ", clean)
    clean = re.sub(r"\b(?:tk|sd|tu|den)\s*:\s*", " ", clean, flags=re.IGNORECASE)
    clean = clean.strip(" \"'|,.;:-")
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean[:80].rstrip(" -")


def _sanitize_transaction_party(value: str) -> str:
    party = str(value or "").strip()
    has_trailing_ellipsis = party.endswith("...")
    clean = sanitize_transaction_note(party).strip(" -")
    return f"{clean}..." if has_trailing_ellipsis and clean and not clean.endswith("...") else clean


def _extract_momo_sender(title: str) -> str:
    sender_match = _AUTO_MOMO_SENDER_RE.search(title or "")
    return _sanitize_transaction_party(sender_match.group(1)) if sender_match else ""


def _extract_mb_sender(text: str) -> str:
    sender_match = _AUTO_MB_SENDER_RE.search(text or "")
    return _sanitize_transaction_party(sender_match.group(1)) if sender_match else ""


def _extract_auto_merchant(text: str) -> str:
    merchant_match = re.search(r"(?:tại|tai)\s+(.+)$", text or "", re.IGNORECASE | re.UNICODE)
    return sanitize_transaction_note(merchant_match.group(1)) if merchant_match else ""


def _extract_auto_note_candidate(text: str) -> str:
    message_match = _AUTO_MESSAGE_MARKER_RE.search(text or "")
    if message_match:
        raw_message = message_match.group(1).split("|", 1)[0].strip()
        quoted = re.search(r"[\"“](.+?)[\"”]", raw_message)
        return quoted.group(1) if quoted else raw_message

    marker_match = _AUTO_NOTE_MARKER_RE.search(text or "")
    if marker_match:
        return marker_match.group(1).split("|", 1)[0].strip()

    merchant = _extract_auto_merchant(text)
    if merchant:
        return merchant
    return ""


def _extract_auto_notification_note(source: str, tx_type: Optional[int], title: str, text: str) -> str:
    candidate = sanitize_transaction_note(_extract_auto_note_candidate(text))
    combined = f"{title} {text}"
    normalized = _normalize_intent_text(combined)

    if source == "Momo" and tx_type == 1:
        sender = _extract_momo_sender(title)
        sender_note = f"Nhận tiền MoMo từ {sender}" if sender else "Nhận tiền MoMo"
        return sanitize_transaction_note(f"{sender_note} - {candidate}" if candidate else sender_note)
    if source == "Momo" and tx_type == 0:
        merchant = _extract_auto_merchant(text)
        spend_detail = merchant or candidate
        return sanitize_transaction_note(f"Thanh toán MoMo - {spend_detail}" if spend_detail else "Thanh toán MoMo")
    if source == "MB Bank" and tx_type == 1 and candidate:
        sender = _extract_mb_sender(text)
        sender_note = f"Nhận chuyển khoản từ {sender}" if sender else "Nhận chuyển khoản"
        return sanitize_transaction_note(f"{sender_note} - {candidate}")
    if candidate:
        return candidate
    if "thanh toan" in normalized:
        merchant = sanitize_transaction_note(re.sub(_AUTO_MONEY_RE, " ", text or ""))
        if merchant:
            return merchant
    if tx_type == 1:
        return "Nhận tiền"
    if tx_type == 0:
        return "Giao dịch chi"
    return ""


def classify_category_from_transaction(tx_type: Optional[int], note: str, text: str) -> str:
    if tx_type == 1:
        return INCOME_CATEGORIES[-1]

    normalized = _normalize_intent_text(f"{note} {text}")
    food_words = (
        "jollibee", "kfc", "lotteria", "highlands", "phuc long", "starbucks",
        "cafe", "ca phe", "tra sua", "restaurant", "food", "an uong", "quan an",
    )
    shopping_words = (
        "circle k", "cirkle k", "winmart", "vinmart", "bach hoa xanh",
        "sieu thi", "cua hang tien loi", "grocery", "supermarket",
        "shopee", "lazada", "tiki", "tiktok shop",
    )
    transport_words = ("grab", "gojek", "xanh sm", "taxi", "bus", "ve xe")
    phone_words = ("internet", "viettel", "vnpt", "fpt", "mobifone", "vinaphone")
    electric_words = ("tien dien", "tien nuoc", " dien", " nuoc")
    if any(word in normalized for word in food_words):
        return EXPENSE_CATEGORIES[0]
    if any(word in normalized for word in shopping_words):
        return EXPENSE_CATEGORIES[1]
    if any(word in normalized for word in transport_words):
        return EXPENSE_CATEGORIES[8]
    if any(word in normalized for word in phone_words):
        return EXPENSE_CATEGORIES[9]
    if any(word in normalized for word in electric_words):
        return EXPENSE_CATEGORIES[7]
    return EXPENSE_CATEGORIES[-1]


def _has_clear_financial_notification_signal(package_name: str, text: str) -> bool:
    if map_package_to_source(package_name):
        return True
    if _AUTO_GD_MONEY_RE.search(text or ""):
        return True
    signed_money = bool(_AUTO_SIGNED_MONEY_RE.search(text or ""))
    normalized = _normalize_intent_text(text or "")
    return signed_money and any(
        keyword in normalized
        for keyword in ("thanh toan", "chuyen tien", "ghi co", "ghi no", "bien dong so du", "nhan tien")
    )


def parse_auto_notification_deterministic(title: str, text: str, package_name: str) -> Optional[dict]:
    combined = f"{title or ''} {text or ''}".strip()
    if not _has_clear_financial_notification_signal(package_name, combined):
        print("[Auto Notification] skip: unsupported package without clear financial signal")
        return None

    source = map_package_to_source(package_name) or str(package_name or "").strip()
    amount, tx_type, locked_fields = _parse_auto_amount_and_type(combined)
    if map_package_to_source(package_name):
        locked_fields.add("source")
    note = _extract_auto_notification_note(source, tx_type, title or "", text or "")
    if source == "Momo" and amount and tx_type in (0, 1) and note:
        locked_fields.update({"amount", "type", "note"})
    category = classify_category_from_transaction(tx_type, note, combined) if tx_type in (0, 1) else ""
    sanitized_note = sanitize_transaction_note(note)
    return {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "note": sanitized_note,
        "date": _auto_today_str(),
        "source": source,
        "_locked_fields": locked_fields,
        "_needs_ai": sanitized_note in {"Nhận tiền", "Giao dịch chi"},
    }


def _auto_deterministic_complete(parsed: Optional[dict]) -> bool:
    return bool(
        parsed
        and parsed.get("amount")
        and parsed.get("type") in (0, 1)
        and str(parsed.get("source") or "").strip()
        and str(parsed.get("note") or "").strip()
        and str(parsed.get("category") or "").strip()
    )


def _auto_deterministic_ready(parsed: Optional[dict]) -> bool:
    return bool(_auto_deterministic_complete(parsed) and not parsed.get("_needs_ai"))


def _auto_parser_note_preview(parsed: Optional[dict]) -> str:
    return sanitize_transaction_note((parsed or {}).get("note", ""))[:200]


def _auto_parser_missing_reason(parsed: Optional[dict]) -> str:
    if not parsed or not parsed.get("amount") or parsed.get("type") not in (0, 1):
        return "missing_amount_or_type_or_note"
    if not str(parsed.get("source") or "").strip() or not str(parsed.get("note") or "").strip():
        return "missing_amount_or_type_or_note"
    return "weak_note"


def _merge_auto_notification_parse(deterministic: dict, ai_parsed: Optional[dict]) -> dict:
    merged = {**deterministic}
    for field, value in (ai_parsed or {}).items():
        if field in {"amount", "type", "source"}:
            merged[field] = value
        elif field == "category" and merged.get("category"):
            continue
        elif value:
            merged[field] = value
    locked_fields = set(deterministic.get("_locked_fields") or set())
    for field in ("amount", "type", "source", "note"):
        if field in locked_fields:
            merged[field] = deterministic.get(field)
    if not merged.get("amount"):
        merged["amount"] = deterministic.get("amount")
    if merged.get("type") not in (0, 1):
        merged["type"] = deterministic.get("type")
    merged["source"] = str(merged.get("source") or deterministic.get("source") or "").strip()
    merged["note"] = sanitize_transaction_note(merged.get("note") or deterministic.get("note") or "")
    tx_type = merged.get("type")
    valid_categories = INCOME_CATEGORIES if tx_type == 1 else EXPENSE_CATEGORIES
    if merged.get("category") not in valid_categories:
        merged["category"] = deterministic.get("category") or valid_categories[-1]
    merged.pop("_locked_fields", None)
    merged.pop("_needs_ai", None)
    return merged


@app.post("/api/ai/assistant")
def ai_assistant(body: AIAssistantRequest):
    message = (body.message or "").strip()
    mode = (body.mode or "auto").strip().lower()
    if not message:
        return {
            "success": False,
            "message": "Vui lòng nhập nội dung chi tiêu.",
            "intent": "unknown",
            "transaction": None,
            "transaction_id": None,
        }

    if _is_simple_ai_greeting(message) and mode != "transaction":
        return {
            "success": True,
            "message": "Xin chào. Bạn có thể nhập nội dung như: ăn sáng 30k, nhận lương 5 triệu, mua xăng 100k.",
            "intent": "greeting",
            "transaction": None,
            "transaction_id": None,
        }

    should_parse_transaction = mode == "transaction" or (mode == "auto" and _looks_like_transaction_text(message))
    if not should_parse_transaction:
        return {
            "success": True,
            "message": "Bạn có thể nhập nội dung như: ăn sáng 30k, nhận lương 5 triệu, mua xăng 100k.",
            "intent": "help",
            "transaction": None,
            "transaction_id": None,
        }

    try:
        return parse_and_save_transaction_for_app((body.firebase_uid or "").strip(), message)
    except Exception as exc:
        print(f"[AI Assistant] request failed uid_present={is_present(body.firebase_uid)} reason={sanitize_log_text(exc)}")
        return {
            "success": False,
            "message": "AI backend chưa được cấu hình hoặc đang bận. Vui lòng thử lại sau.",
            "intent": "transaction",
            "transaction": None,
            "transaction_id": None,
        }


# ==========================================
# CÁC HÀM XỬ LÝ DỮ LIỆU VÀ XUẤT EXCEL (CŨ)
# ==========================================

def _normalize_type(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return 1 if value == 1 else 0 if value == 0 else None
    if isinstance(value, str):
        s = value.strip()
        if s in ("1", "income"):
            return 1
        if s in ("0", "expense"):
            return 0
    return None

def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

def _format_date(value: Any) -> str:
    if value is None:
        return ""
    if hasattr(value, "timestamp"):
        try:
            return datetime.fromtimestamp(value.timestamp()).strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)

def _doc_to_row(doc_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": doc_id,
        "date": _format_date(
            data.get("date")
            or data.get("createdAt")
            or data.get("created_at")
            or data.get("timestamp")
        ),
        "category": data.get("category") or data.get("categoryName") or "",
        "note": data.get("note") or data.get("description") or data.get("memo") or "",
        "amount": _to_float(data.get("amount")),
        "type": _normalize_type(data.get("type")),
    }

def _fetch_transactions(user_id: str) -> list[dict[str, Any]]:
    col = (
        db.collection("users")
        .document(user_id)
        .collection("transactions")
    )
    rows: list[dict[str, Any]] = []
    for snap in col.stream():
        rows.append(_doc_to_row(snap.id, snap.to_dict() or {}))
    return rows

def _apply_table_border(
    ws: Any, min_row: int, max_row: int, min_col: int, max_col: int
) -> None:
    thin = Side(style="thin")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    for r in range(min_row, max_row + 1):
        for c in range(min_col, max_col + 1):
            ws.cell(row=r, column=c).border = border

def _build_excel(path: str, rows: list[dict[str, Any]]) -> None:
    total_income = sum(r["amount"] for r in rows if r["type"] == 1)
    total_expense = sum(r["amount"] for r in rows if r["type"] == 0)
    balance = total_income - total_expense

    summary_df = pd.DataFrame(
        {
            "Chỉ số": ["Tổng thu (type=1)", "Tổng chi (type=0)", "Số dư"],
            "Giá trị": [total_income, total_expense, balance],
        }
    )

    detail_rows = [
        {
            "Ngày": r["date"],
            "Danh mục": r["category"],
            "Ghi chú": r["note"],
            "Số tiền": r["amount"],
        }
        for r in rows
    ]
    details_df = pd.DataFrame(detail_rows)

    expenses = [r for r in rows if r["type"] == 0]
    expenses_sorted = sorted(expenses, key=lambda x: x["amount"], reverse=True)[:5]
    top5_df = pd.DataFrame(
        [
            {
                "Ngày": r["date"],
                "Danh mục": r["category"],
                "Ghi chú": r["note"],
                "Số tiền": r["amount"],
            }
            for r in expenses_sorted
        ]
    )

    sheet_name = "Báo Cáo"
    bold_font = Font(bold=True)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name=sheet_name, startrow=1, index=False)
        ws = writer.sheets[sheet_name]
        ws.cell(row=1, column=1, value="TỔNG QUAN").font = bold_font

        row_details = len(summary_df) + 3
        ws.cell(row=row_details + 1, column=1, value="CHI TIẾT TẤT CẢ GIAO DỊCH").font = (
            bold_font
        )
        details_df.to_excel(
            writer, sheet_name=sheet_name, startrow=row_details + 1, index=False
        )

        row_top5 = row_details + len(details_df) + 3
        ws.cell(row=row_top5 + 1, column=1, value="TOP 5 KHOẢN CHI LỚN NHẤT").font = (
            bold_font
        )
        top5_df.to_excel(
            writer, sheet_name=sheet_name, startrow=row_top5 + 1, index=False
        )

        sum_header_excel = 2
        sum_max_excel = sum_header_excel + len(summary_df)
        _apply_table_border(
            ws, sum_header_excel, sum_max_excel, 1, len(summary_df.columns)
        )

        det_header_excel = row_details + 2
        det_max_excel = det_header_excel + len(details_df)
        _apply_table_border(
            ws, det_header_excel, det_max_excel, 1, len(details_df.columns)
        )

        top_header_excel = row_top5 + 2
        top_max_excel = top_header_excel + len(top5_df)
        _apply_table_border(ws, top_header_excel, top_max_excel, 1, len(top5_df.columns))

        for col_idx, col_name in enumerate(details_df.columns, start=1):
            max_len = len(str(col_name))
            for v in details_df[col_name]:
                max_len = max(max_len, len(str(v)))
            letter = get_column_letter(col_idx)
            ws.column_dimensions[letter].width = min(max(max_len + 2, 10), 60)

def _send_email_with_attachment(to_email: str, attachment_path: str, filename: str) -> None:
    # 1. Đọc nội dung file báo cáo (chuyển sang list số nguyên cho Resend)
    with open(attachment_path, "rb") as f:
        file_content = list(f.read())

    # 2. Cấu hình tham số gửi mail qua Resend HTTP API
    params = {
        "from": "Sổ Thu Chi <onboarding@resend.dev>",
        "to": [to_email],
        "subject": "Báo cáo dữ liệu Thu Chi",
        "html": "<strong>Đính kèm file báo cáo Excel theo yêu cầu.</strong>",
        "attachments": [
            {
                "filename": filename,
                "content": file_content,
            }
        ],
    }

    # 3. Thực hiện gửi
    resend.Emails.send(params)


@app.post("/api/export-email")
def export_email(body: ExportEmailRequest):
    try:
        if not os.path.isfile(FIREBASE_KEY_PATH):
            raise Exception("Thiếu firebase_key.json")

        # Logic lấy dữ liệu
        rows = _fetch_transactions(body.userId)

        fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(fd)
        filename = f"bao_cao_{body.userId}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

        try:
            _build_excel(tmp_path, rows)
            # Gửi email (nghiệp vụ chính)
            _send_email_with_attachment(body.userEmail, tmp_path, filename)
        finally:
            if os.path.isfile(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

        return {
            "success": True,
            "message": "Đã tạo file Excel và gửi email thành công.",
            "userId": body.userId,
            "recipient": body.userEmail,
            "transactionCount": len(rows),
        }
    except Exception as e:
        # In chi tiết lỗi ra server console
        print("!!! ERROR IN /api/export-email !!!")
        traceback.print_exc()
        # Trả về Plain Text cho client
        return Response(
            content=f"INTERNAL SERVER ERROR: {str(e)}",
            status_code=500,
            media_type="text/plain"
        )


# ==========================================
# CÁC HÀM XỬ LÝ TELEGRAM BOT VÀ AI (MỚI)
# ==========================================

def send_telegram_message(bot_token: str, chat_id: int, text: str, reply_markup: Optional[dict] = None):
    """Hàm hỗ trợ gửi tin nhắn lại cho người dùng qua Telegram.
    Sử dụng token động của từng user."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
        print("[Telegram Reply Markup]", reply_markup)
        print("[Telegram Payload]", payload)
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram Send Error] Status {resp.status_code}: {resp.text}")
        else:
            print(f"[Telegram] Message sent to {chat_id} via custom bot")
    except Exception as e:
        print(f"[Telegram] Lỗi gửi tin nhắn: {e}")
        traceback.print_exc()


def _build_transaction_action_keyboard(doc_id: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": "✅ Đúng", "callback_data": f"confirm:{doc_id}"}],
            [{"text": "🏷️ Sửa danh mục", "callback_data": f"edit_category:{doc_id}"}],
            [{"text": "🗑️ Xóa", "callback_data": f"delete:{doc_id}"}],
        ]
    }


def _is_safe_transaction_doc_id(doc_id: str) -> bool:
    return bool(re.fullmatch(r"(reqtele|at|ocr)_\d+", doc_id or ""))


def encode_category_slug(category: str) -> Optional[str]:
    if category in EXPENSE_CATEGORIES:
        return f"exp_{EXPENSE_CATEGORIES.index(category)}"
    if category in INCOME_CATEGORIES:
        return f"inc_{INCOME_CATEGORIES.index(category)}"
    return None


def decode_category_slug(slug: str) -> Optional[str]:
    exp_match = re.fullmatch(r"exp_(\d+)", slug or "")
    if exp_match:
        idx = int(exp_match.group(1))
        return EXPENSE_CATEGORIES[idx] if 0 <= idx < len(EXPENSE_CATEGORIES) else None

    inc_match = re.fullmatch(r"inc_(\d+)", slug or "")
    if inc_match:
        idx = int(inc_match.group(1))
        return INCOME_CATEGORIES[idx] if 0 <= idx < len(INCOME_CATEGORIES) else None

    return None


def _build_category_keyboard(doc_id: str, tx_type: int) -> dict:
    categories = INCOME_CATEGORIES if tx_type == 1 else EXPENSE_CATEGORIES
    rows = []
    for category in categories:
        slug = encode_category_slug(category)
        if not slug:
            continue
        icon = CATEGORY_EMOJIS.get(category, "")
        text = f"{icon} {category}".strip()
        rows.append([{"text": text, "callback_data": f"set_cat:{doc_id}:{slug}"}])
    return {"inline_keyboard": rows}


def _answer_telegram_callback(bot_token: str, callback_query_id: str, text: Optional[str] = None):
    url = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    payload = {"callback_query_id": callback_query_id}
    if text:
        payload["text"] = text
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram Callback Error] Status {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Lá»—i tráº£ lá»i callback: {e}")
        traceback.print_exc()


def _is_safe_pending_action_id(action_id: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{32}", action_id or ""))


def _pending_action_ref(firebase_uid: str, action_id: str):
    return db.collection("users").document(firebase_uid).collection("pending_actions").document(action_id)


def _parse_pending_timestamp(value: Any) -> Any:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            return value
    return value


def _rehydrate_pending_ocr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    restored = dict(payload or {})
    restored.pop("id", None)
    restored["timestamp"] = _parse_pending_timestamp(restored.get("timestamp"))
    restored["lastUpdated"] = firestore.SERVER_TIMESTAMP
    return restored


@firestore.transactional
def _claim_pending_ocr_action(transaction, action_ref, now_utc: datetime):
    snap = action_ref.get(transaction=transaction)
    if not snap.exists:
        return None, "not_found"

    data = snap.to_dict() or {}
    if data.get("action_type") != "ocr_confirm":
        return None, "invalid"

    status = data.get("status")
    if status != "pending":
        return None, status or "invalid"

    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime):
        expires_at = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
        if expires_at < now_utc:
            transaction.update(action_ref, {
                "status": "cancelled",
                "cancel_reason": "expired",
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
            return None, "expired"

    transaction.update(action_ref, {
        "status": "processing",
        "processing_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    })
    return data, None


def _handle_pending_ocr_callback(bot_token: str, firebase_uid: str, chat_id: int, callback_query_id: str, callback_data: str):
    try:
        action, action_id = callback_data.split(":", 1)
    except ValueError:
        _answer_telegram_callback(bot_token, callback_query_id, "Thao tác không hợp lệ.")
        return

    if action not in {"save_pending_ocr", "cancel_pending_ocr"} or not _is_safe_pending_action_id(action_id):
        _answer_telegram_callback(bot_token, callback_query_id, "Thao tác không hợp lệ.")
        return

    action_ref = _pending_action_ref(firebase_uid, action_id)

    if action == "cancel_pending_ocr":
        snap = action_ref.get()
        if not snap.exists:
            _answer_telegram_callback(bot_token, callback_query_id, "Yêu cầu không còn tồn tại.")
            send_telegram_message(bot_token, chat_id, "⚠️ Không tìm thấy yêu cầu OCR cần xử lý.")
            return

        data = snap.to_dict() or {}
        status = data.get("status")
        if status == "completed":
            _answer_telegram_callback(bot_token, callback_query_id, "Yêu cầu đã được lưu trước đó.")
            send_telegram_message(bot_token, chat_id, "ℹ️ Hóa đơn này đã được lưu trước đó.")
            return
        if status == "processing":
            _answer_telegram_callback(bot_token, callback_query_id, "Yêu cầu đang được xử lý.")
            send_telegram_message(bot_token, chat_id, "⏳ Yêu cầu OCR đang được xử lý, vui lòng chờ một chút.")
            return

        action_ref.set({
            "status": "cancelled",
            "cancelled_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        _answer_telegram_callback(bot_token, callback_query_id, "Đã bỏ qua.")
        send_telegram_message(bot_token, chat_id, "Đã bỏ qua hóa đơn này. Không có giao dịch nào được lưu.")
        return

    transaction = db.transaction()
    pending_data, claim_error = _claim_pending_ocr_action(transaction, action_ref, datetime.now(timezone.utc))
    if claim_error:
        messages = {
            "not_found": "Yêu cầu không còn tồn tại.",
            "expired": "Yêu cầu đã hết hạn.",
            "completed": "Yêu cầu đã được lưu trước đó.",
            "cancelled": "Yêu cầu đã bị bỏ qua.",
            "processing": "Yêu cầu đang được xử lý.",
        }
        msg = messages.get(claim_error, "Yêu cầu không hợp lệ.")
        _answer_telegram_callback(bot_token, callback_query_id, msg)
        send_telegram_message(bot_token, chat_id, msg)
        return

    try:
        payload = _rehydrate_pending_ocr_payload(pending_data.get("payload", {}))
        doc_id = _save_transaction_atomic(firebase_uid, payload, "ocr")

        try:
            _send_fcm_notification(firebase_uid, doc_id, {
                "amount": payload.get("amount", 0),
                "category": payload.get("category", "Khác"),
                "note": payload.get("note", ""),
                "date": payload.get("date", ""),
                "source": payload.get("source", ""),
            })
        except Exception as fcm_err:
            print(f"[Pending OCR] FCM error (non-critical): {fcm_err}")

        # [MERCHANT LEARNING] Hoc rule tu OCR transaction da confirm va luu thanh cong
        if ENABLE_MERCHANT_LEARNING:
            try:
                update_merchant_rule_from_transaction(firebase_uid, payload)
            except Exception as rule_err:
                print(f"[MerchantRule] Non-critical OCR rule error: {rule_err}")

        action_ref.set({
            "status": "completed",
            "completed_at": firestore.SERVER_TIMESTAMP,
            "transaction_id": doc_id,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        _answer_telegram_callback(bot_token, callback_query_id, "Đã lưu hóa đơn.")
        send_telegram_message(bot_token, chat_id, f"✅ Đã lưu hóa đơn thành giao dịch {doc_id}.")
    except Exception as e:
        err = str(e)[:180]
        print(f"[Pending OCR Save Error] {e}")
        traceback.print_exc()
        action_ref.set({
            "status": "failed",
            "error": err,
            "failed_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        _answer_telegram_callback(bot_token, callback_query_id, "Không thể lưu hóa đơn.")
        send_telegram_message(bot_token, chat_id, "⚠️ Không thể lưu hóa đơn lúc này. Vui lòng thử lại sau.")


def _handle_transaction_callback(bot_token: str, firebase_uid: str, chat_id: int, callback_query_id: str, callback_data: str):
    if callback_data.startswith(("save_pending_ocr:", "cancel_pending_ocr:")):
        _handle_pending_ocr_callback(bot_token, firebase_uid, chat_id, callback_query_id, callback_data)
        return

    if callback_data.startswith("set_cat:"):
        parts = callback_data.split(":", 2)
        if len(parts) != 3:
            _answer_telegram_callback(bot_token, callback_query_id, "Thao tác không hợp lệ.")
            return

        _, doc_id, category_slug = parts
        if not _is_safe_transaction_doc_id(doc_id):
            _answer_telegram_callback(bot_token, callback_query_id, "Giao dịch không hợp lệ.")
            return

        tx_ref = db.collection("users").document(firebase_uid).collection("transactions").document(doc_id)
        tx_snap = tx_ref.get()
        if not tx_snap.exists:
            _answer_telegram_callback(bot_token, callback_query_id, "Không tìm thấy giao dịch.")
            send_telegram_message(bot_token, chat_id, f"⚠️ Không tìm thấy giao dịch {doc_id}.")
            return

        tx_data = tx_snap.to_dict() or {}
        if tx_data.get("isDeleted") is True:
            _answer_telegram_callback(bot_token, callback_query_id, "Giao dịch đã được xóa trước đó.")
            send_telegram_message(bot_token, chat_id, f"ℹ️ Giao dịch {doc_id} đã được xóa trước đó.")
            return

        new_category = decode_category_slug(category_slug)
        tx_type = 1 if tx_data.get("type") == 1 else 0
        valid_categories = INCOME_CATEGORIES if tx_type == 1 else EXPENSE_CATEGORIES
        if not new_category or new_category not in valid_categories:
            _answer_telegram_callback(bot_token, callback_query_id, "Danh mục không hợp lệ.")
            return

        try:
            tx_ref.update({
                "category": new_category,
                "lastUpdated": firestore.SERVER_TIMESTAMP,
            })
        except Exception as e:
            print(f"[Telegram Category Update Error] {e}")
            traceback.print_exc()
            _answer_telegram_callback(bot_token, callback_query_id, "Không thể cập nhật danh mục.")
            send_telegram_message(bot_token, chat_id, "⚠️ Không thể cập nhật danh mục lúc này. Vui lòng thử lại sau.")
            return

        _answer_telegram_callback(bot_token, callback_query_id, "Đã cập nhật danh mục.")
        send_telegram_message(bot_token, chat_id, f"✅ Đã cập nhật danh mục giao dịch {doc_id} thành: {new_category}")

        # [MERCHANT LEARNING] Hoc tu user correction
        if ENABLE_MERCHANT_LEARNING:
            try:
                source_text = tx_data.get("source", "") or tx_data.get("note", "")
                update_merchant_rule_from_correction(firebase_uid, source_text, new_category, tx_type)
            except Exception as rule_err:
                print(f"[MerchantRule] Non-critical correction error: {rule_err}")
        return

    try:
        action, doc_id = callback_data.split(":", 1)
    except ValueError:
        _answer_telegram_callback(bot_token, callback_query_id, "Thao tác không hợp lệ.")
        return

    if action not in {"confirm", "edit_category", "delete"} or not _is_safe_transaction_doc_id(doc_id):
        _answer_telegram_callback(bot_token, callback_query_id, "Giao dịch không hợp lệ.")
        return

    if action == "confirm":
        _answer_telegram_callback(bot_token, callback_query_id, "Đã xác nhận.")
        send_telegram_message(bot_token, chat_id, f"✅ Đã xác nhận giao dịch {doc_id}.")
        return

    if action == "edit_category":
        tx_ref = db.collection("users").document(firebase_uid).collection("transactions").document(doc_id)
        tx_snap = tx_ref.get()
        if not tx_snap.exists:
            _answer_telegram_callback(bot_token, callback_query_id, "Không tìm thấy giao dịch.")
            send_telegram_message(bot_token, chat_id, f"⚠️ Không tìm thấy giao dịch {doc_id}.")
            return

        tx_data = tx_snap.to_dict() or {}
        if tx_data.get("isDeleted") is True:
            _answer_telegram_callback(bot_token, callback_query_id, "Giao dịch đã được xóa trước đó.")
            send_telegram_message(bot_token, chat_id, f"ℹ️ Giao dịch {doc_id} đã được xóa trước đó.")
            return

        tx_type = 1 if tx_data.get("type") == 1 else 0
        _answer_telegram_callback(bot_token, callback_query_id, "Chọn danh mục mới.")
        send_telegram_message(
            bot_token,
            chat_id,
            f"🏷️ Chọn danh mục mới cho giao dịch {doc_id}:",
            reply_markup=_build_category_keyboard(doc_id, tx_type)
        )
        return

    tx_ref = db.collection("users").document(firebase_uid).collection("transactions").document(doc_id)
    tx_snap = tx_ref.get()
    if not tx_snap.exists:
        _answer_telegram_callback(bot_token, callback_query_id, "Không tìm thấy giao dịch.")
        send_telegram_message(bot_token, chat_id, f"⚠️ Không tìm thấy giao dịch {doc_id}, nên bot chưa xóa gì cả.")
        return

    tx_data = tx_snap.to_dict() or {}
    if tx_data.get("isDeleted") is True:
        _answer_telegram_callback(bot_token, callback_query_id, "Giao dịch đã được xóa trước đó.")
        send_telegram_message(bot_token, chat_id, f"ℹ️ Giao dịch {doc_id} đã được xóa trước đó.")
        return

    tx_ref.update({
        "isDeleted": True,
        "lastUpdated": firestore.SERVER_TIMESTAMP,
    })
    _answer_telegram_callback(bot_token, callback_query_id, "Đã xóa giao dịch.")
    send_telegram_message(bot_token, chat_id, f"🗑️ Đã xóa giao dịch {doc_id}.")


def _get_uid_from_bot_token(bot_token: str) -> Optional[str]:
    """
    Tra cứu Firebase UID từ Telegram bot_token do người dùng thiết lập.
    Sử dụng in-memory cache để tránh query lặp lại.
    """
    if bot_token in _bot_token_to_uid_cache:
        return _bot_token_to_uid_cache[bot_token]

    query = (
        db.collection("users")
        .where("telegramConfig.botToken", "==", bot_token)
        .limit(1)
        .stream()
    )
    for doc in query:
        uid = doc.id
        _bot_token_to_uid_cache[bot_token] = uid
        return uid

    return None

class TelegramSetupRequest(BaseModel):
    bot_token: str
    firebase_uid: str

@app.post("/api/telegram/setup-bot")
async def setup_telegram_bot(request: TelegramSetupRequest):
    """
    Endpoint nhận bot_token từ React Native app.
    Đã được củng cố (fortified) để tránh lỗi 500 và log chi tiết nguyên nhân.
    """
    try:
        bot_token = request.bot_token.strip()
        uid = request.firebase_uid.strip()

        print(f"[SetupBot] Processing request for UID: {uid}")

        if not BASE_WEBHOOK_URL:
            return {
                "status": "error", 
                "message": "BASE_WEBHOOK_URL chưa được cấu hình (.env). Hãy kiểm tra file cấu hình trên server."
            }

        webhook_url = f"{BASE_WEBHOOK_URL}/webhook/telegram/{bot_token}"
        
        # 1. Gọi Telegram API để setWebhook
        tg_api = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        print(f"[SetupBot] Calling Telegram API: token={is_present(bot_token)}")
        
        try:
            resp = requests.post(tg_api, json={"url": webhook_url}, timeout=15)
            resp.raise_for_status() # Kiểm tra lỗi HTTP (4xx, 5xx)
            resp_data = resp.json()
            
            if not resp_data.get("ok"):
                return {
                    "status": "error", 
                    "message": f"Telegram rejected webhook: {resp_data.get('description', 'Unknown error')}"
                }
        except requests.exceptions.RequestException as e:
            print(f"[SetupBot] Telegram API Network Error: {e}")
            return {"status": "error", "message": f"Không thể kết nối tới Telegram: {str(e)}"}

        # 2. Lưu vào Firestore (telegramConfig)
        print(f"[SetupBot] Saving config to Firestore for UID: {uid}")
        try:
            db.collection("users").document(uid).set({
                "telegramConfig": {
                    "botToken": bot_token,
                    "webhookUrl": webhook_url,
                    "linkedAt": datetime.now(tz=VN_TZ).isoformat()
                }
            }, merge=True)
            
            # Cập nhật cache ngay lập tức
            _bot_token_to_uid_cache[bot_token] = uid
            try:
                from agentic_ai import ensure_default_external_brief_task_for_user, ensure_default_finance_report_task_for_user
                ensure_default_external_brief_task_for_user(uid)
                ensure_default_finance_report_task_for_user(uid)
            except Exception as task_error:
                print(f"[SetupBot] Cannot ensure external brief task for {uid}: {task_error}")
            print(f"[SetupBot] Successfully linked token to UID: {uid}")
            
        except Exception as e:
            print(f"[SetupBot] Firestore Write Error: {e}")
            traceback.print_exc()
            return {"status": "error", "message": f"Lỗi khi lưu vào Database: {str(e)}"}

        return {"status": "ok", "message": "Bot connected successfully!"}

    except Exception as e:
        # Bắt toàn bộ lỗi còn lại để tránh trả về 500
        print("[SETUP_BOT_CRITICAL_ERROR] Fatal failure:")
        traceback.print_exc()
        return {
            "status": "error", 
            "message": f"Lỗi hệ thống nghiêm trọng: {str(e)}"
        }


def analyze_text_with_gemini(user_text: str) -> dict:
    """
    Gọi trực tiếp OpenRouter API (Thay thế Gemini).
    """
    now_vn = datetime.now(tz=VN_TZ)
    today_str = now_vn.strftime("%d/%m/%Y")

    # Tạo prompt từ template
    system_prompt = AI_SYSTEM_PROMPT.format(current_date=today_str)
    
    full_prompt = f"{system_prompt}\n\nUSER INPUT: \"{user_text}\"\n\nJSON OUTPUT:"
    
    if not OPENROUTER_API_KEY:
        logger.warning("[OpenRouter] OPENROUTER_API_KEY=missing feature=text_parse")
        raise RuntimeError("OPENROUTER_API_KEY missing")

    print(f"\n[AI Request] Đang gửi yêu cầu phân tích văn bản cho AI:")
    print(f"--- TEXT PREVIEW: '{sanitize_log_text(user_text[:200])}' ---")

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    }

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/Hoangsonn05/So-Thu-Chi-React-Native",
                "X-Title": "So Thu Chi App"
            },
            timeout=60,
        )
    except requests.exceptions.ReadTimeout:
        print("[OpenRouter Timeout] AI không phản hồi kịp trong 60s")
        return "ERROR_TIMEOUT"
    except Exception as e:
        print(f"[OpenRouter Request Error] {e}")
        raise e
    
    if response.status_code != 200:
        print(f"\n====== OPENROUTER API ERROR ({response.status_code}) ======")
        print(f"Details: {response.text}")
        print("==========================================================\n")
        raise Exception(f"OpenRouter API rejected the request. Error: {response.text}")

    result = response.json()
    
    try:
        # OpenAI style response: choices[0].message.content
        raw_text = result['choices'][0]['message']['content'].strip()
        print(f"[AI Response Raw Preview]: '{sanitize_log_text(raw_text[:200])}'")
    except (KeyError, IndexError) as e:
        print(f"[OpenRouter Response Error] Could not extract text: {e}")
        raise ValueError("AI trả về định dạng không mong muốn.")

    if not raw_text:
        raise ValueError("AI trả về rỗng, không thể parse.")

    # Clean potential markdown code fences
    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    # Nếu không phải JSON thuần, thử tìm cặp ngoặc nhọn
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        first = cleaned.find('{')
        last = cleaned.rfind('}')
        if first >= 0 and last > first:
            parsed = json.loads(cleaned[first:last+1])
        else:
            print(
                "[AI Parse Error] Không tìm thấy JSON hợp lệ trong phản hồi. "
                f"Preview: '{sanitize_log_text(cleaned[:200])}'"
            )
            raise

    # ---- Map Gemini Response (trả về schema cũ: type, amount, category, note, date) ----
    tx_type = int(parsed.get("type", 0))
    if tx_type not in (0, 1):
        tx_type = 0

    amount = int(parsed.get("amount", 0))
    if amount <= 0:
        try:
            amount = int(float(parsed.get("amount", 0)))
        except:
            amount = 0
            
    if amount <= 0:
        raise ValueError(f"Số tiền không hợp lệ: {amount}")

    category = parsed.get("category", "Khác")
    valid_cats = EXPENSE_CATEGORIES if tx_type == 0 else INCOME_CATEGORIES
    if category not in valid_cats:
        category = "Khác"

    note = str(parsed.get("note", user_text))[:50]

    date_str = parsed.get("date", today_str)
    try:
        datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        date_str = today_str

    return {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "note": note,
        "date": date_str,
        "source": str(parsed.get("source") or "Tiền mặt").strip(),
    }


def _normalize_ai_transaction_item(parsed: dict, user_text: str, today_str: str) -> dict:
    tx_type = int(parsed.get("type", 0))
    if tx_type not in (0, 1):
        tx_type = 0

    try:
        amount = int(parsed.get("amount", 0))
    except (TypeError, ValueError):
        try:
            amount = int(float(parsed.get("amount", 0)))
        except (TypeError, ValueError):
            amount = 0

    if amount <= 0:
        raise ValueError(f"Invalid amount: {amount}")

    category = parsed.get("category", "Kh\u00e1c")
    valid_cats = EXPENSE_CATEGORIES if tx_type == 0 else INCOME_CATEGORIES
    if category not in valid_cats:
        category = "Kh\u00e1c"

    note = str(parsed.get("note", user_text))[:50]

    date_str = parsed.get("date", today_str)
    try:
        datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        date_str = today_str

    return {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "note": note,
        "date": date_str,
        "source": str(parsed.get("source", "Ti\u1ec1n m\u1eb7t")),
    }

def analyze_text_multi_transactions(user_text: str) -> list[dict]:
    """
    High-risk multi transaction parser. Returns a normalized list of transaction dicts.
    Legacy analyze_text_with_gemini() remains the fallback and is not modified.
    """
    now_vn = datetime.now(tz=VN_TZ)
    today_str = now_vn.strftime("%d/%m/%Y")

    multi_prompt = f"""{AI_SYSTEM_PROMPT.format(current_date=today_str)}

## MULTI-TRANSACTION OUTPUT RULES:
1. Output ONLY a raw JSON array. No markdown, no code fences, no explanation, no extra text.
2. Each array item must be one transaction object with EXACTLY these fields:
   - "type"
   - "amount"
   - "category"
   - "note"
   - "date"
   - "source"
3. If the user's message contains only one transaction, still output an array with exactly one item.
4. Split clearly separate spending/income entries into separate array items.
5. Do not invent transactions that are not present in the user's text.
6. If a message contains multiple clauses separated by commas, semicolons, "va", "và",
   or separate time markers such as "sang", "sáng", "trua", "trưa", "toi", "tối",
   and each clause has its own amount, each clause MUST become a separate JSON object.
7. The input "Sáng cafe 25k, trưa ăn cơm gà 35k, gửi xe 3k" MUST be split into
   exactly 3 JSON objects with amounts 25000, 35000, and 3000. Never combine it
   into one 63000 transaction.
"""

    full_prompt = f"{multi_prompt}\n\nUSER INPUT: \"{user_text}\"\n\nJSON ARRAY OUTPUT:"

    if not OPENROUTER_API_KEY:
        logger.warning("[OpenRouter] OPENROUTER_API_KEY=missing feature=multi_text_parse")
        raise RuntimeError("OPENROUTER_API_KEY missing")

    print(f"\n[AI Multi Request] Đang gửi yêu cầu phân tích nhiều giao dịch:")
    print(f"--- TEXT PREVIEW: '{sanitize_log_text(user_text[:200])}' ---")

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "user",
                "content": full_prompt
            }
        ]
    }

    try:
        response = requests.post(
            OPENROUTER_API_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "HTTP-Referer": "https://github.com/Hoangsonn05/So-Thu-Chi-React-Native",
                "X-Title": "So Thu Chi App"
            },
            timeout=60,
        )
    except requests.exceptions.ReadTimeout:
        print("[OpenRouter Timeout] AI khÃ´ng pháº£n há»“i ká»‹p trong 60s")
        return "ERROR_TIMEOUT"
    except Exception as e:
        print(f"[OpenRouter Multi Request Error] {e}")
        raise e

    if response.status_code != 200:
        print(f"\n====== OPENROUTER MULTI API ERROR ({response.status_code}) ======")
        print(f"Details: {response.text}")
        print("===============================================================\n")
        raise Exception(f"OpenRouter API rejected the request. Error: {response.text}")

    result = response.json()

    try:
        raw_text = result['choices'][0]['message']['content'].strip()
        print(f"[AI Multi Response Raw]: '{raw_text}'")
    except (KeyError, IndexError) as e:
        print(f"[OpenRouter Multi Response Error] Could not extract text: {e}")
        raise ValueError("AI tráº£ vá» Ä‘á»‹nh dáº¡ng khÃ´ng mong muá»‘n.")

    if not raw_text:
        raise ValueError("AI tráº£ vá» rá»—ng, khÃ´ng thá»ƒ parse.")

    cleaned = raw_text
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        first_array = cleaned.find('[')
        last_array = cleaned.rfind(']')
        if first_array >= 0 and last_array > first_array:
            parsed = json.loads(cleaned[first_array:last_array+1])
        else:
            first_obj = cleaned.find('{')
            last_obj = cleaned.rfind('}')
            if first_obj >= 0 and last_obj > first_obj:
                parsed = json.loads(cleaned[first_obj:last_obj+1])
            else:
                print(f"[AI Multi Parse Error] KhÃ´ng tÃ¬m tháº¥y JSON há»£p lá»‡. VÄƒn báº£n: '{cleaned}'")
                raise

    if isinstance(parsed, dict):
        parsed_items = [parsed]
    elif isinstance(parsed, list):
        parsed_items = parsed
    else:
        raise ValueError("AI multi tráº£ vá» JSON khÃ´ng pháº£i object hoáº·c array.")

    normalized_items = []
    for item in parsed_items:
        if not isinstance(item, dict):
            raise ValueError("AI multi tráº£ vá» item khÃ´ng pháº£i object.")
        normalized_items.append(_normalize_ai_transaction_item(item, user_text, today_str))

    if not normalized_items:
        raise ValueError("AI multi khÃ´ng tráº£ vá» giao dá»‹ch nÃ o.")

    return normalized_items


@firestore.transactional
def _atomic_counter_and_write(transaction, counter_ref, tx_doc_ref, firestore_data):
    """
    ATOMIC: Đọc counter + tăng counter + ghi transaction trong 1 transaction duy nhất.
    Nếu Firestore retry transaction, cả counter lẫn data đều rollback → không bị duplicate.
    """
    # Đọc counter hiện tại
    snapshot = counter_ref.get(transaction=transaction)
    current = snapshot.to_dict().get("last_number", 0) if snapshot.exists else 0
    next_number = current + 1

    # Ghi counter MỚI
    transaction.set(counter_ref, {"last_number": next_number}, merge=True)

    # Ghi transaction data vào document reqtele_{N} (kèm luôn ID vào payload)
    firestore_data["id"] = tx_doc_ref.id
    transaction.set(tx_doc_ref, firestore_data)

    return next_number


def _send_fcm_notification(firebase_uid: str, doc_id: str, parsed: dict) -> None:
    """
    Gửi FCM notification đến token của user (nếu có).
    Thông báo này SẼ HIỆN POPUP (visible push notification) cho user.
    Chứa trạng thái thành công, Amount, Category, Note, và Timestamp.
    """
    try:
        # Lấy FCM token đã được lưu bởi app (trong Firestore user doc)
        user_doc = db.collection("users").document(firebase_uid).get()
        if not user_doc.exists:
            return
        
        user_data = user_doc.to_dict() or {}
        fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")
        
        if not fcm_token:
            # User chưa lưu FCM token — bỏ qua, không được lỗi
            print(f"[FCM] No token found for uid={firebase_uid}, skipping.")
            return
        
        # Chuẩn bị nội dung hiển thị
        cat = str(parsed.get("category", "Khác"))
        amt = parsed.get("amount", 0)
        amt_str = f"{amt:,}đ" if isinstance(amt, (int, float)) else f"{amt}đ"
        note = parsed.get("note", "")
        note_str = f"\nGhi chú: {note}" if note else ""
        date_str = parsed.get("date", "")
        date_display = f"\nLúc: {date_str}" if date_str else ""
        source = parsed.get("source", "Tiền mặt")
        source_display = f"\nNguồn: {source}"
        
        body_text = f"{cat}: {amt_str}{source_display}{note_str}{date_display}"

        # Tạo message có `notification` để hiện popup
        message = messaging.Message(
            notification=messaging.Notification(
                title="✅ Ghi nhận thành công",
                body=body_text
            ),
            data={
                "type": "TRANSACTION_ADDED",
                "docId": str(doc_id),
                "category": cat,
                "amount": str(amt),
            },
            android=messaging.AndroidConfig(
                priority="high",
            ),
            token=fcm_token,
        )
        
        response = messaging.send(message)
        print(f"[FCM] Silent notification sent to uid={firebase_uid}: {response}")
        
    except messaging.UnregisteredError:
        # Token hết hạn — xóa token khỏi Firestore để không gửi nữa
        print(f"[FCM] Token expired for uid={firebase_uid}, removing from Firestore.")
        try:
            db.collection("users").document(firebase_uid).update({"fcmToken": firestore.DELETE_FIELD})
        except Exception:
            pass
    except Exception as e:
        # Lỗi FCM không được làm sập flow chính
        print(f"[FCM] Send error for uid={firebase_uid}: {e}")


def _save_transaction_atomic(firebase_uid: str, firestore_data: dict, id_prefix: str = "reqtele") -> str:
    """
    Lưu transaction + tăng counter trong 1 Firestore Transaction duy nhất.
    Trả về document ID (reqtele_N hoặc at_N).
    Không có network call nào khác bên trong → không bị triplication khi retry.
    """
    counter_ref = (
        db.collection("users")
        .document(firebase_uid)
        .collection("metadata")
        .document("telegram_counter")
    )

    # Đọc counter trước để biết trước doc_id cho transaction
    # (transaction sẽ verify lại bên trong)
    counter_snap = counter_ref.get()
    predicted_next = (counter_snap.to_dict().get("last_number", 0) if counter_snap.exists else 0) + 1

    tx_doc_ref = (
        db.collection("users")
        .document(firebase_uid)
        .collection("transactions")
        .document(f"{id_prefix}_{predicted_next}")
    )

    transaction = db.transaction()
    actual_number = _atomic_counter_and_write(transaction, counter_ref, tx_doc_ref, firestore_data)

    doc_id = f"{id_prefix}_{actual_number}"
    print(f"[Firestore] Saved {doc_id} to users/{firebase_uid}/transactions")
    return doc_id


def _build_firestore_payload(parsed: dict, firebase_uid: str) -> dict:
    """
    Chuyển đổi kết quả AI parse thành Firestore document payload.
    Schema CHÍNH XÁC 1:1 với FirebaseSyncService.ts pushSingleTransaction().

    CRITICAL: Các field timestamp và lastUpdated phải là UTC-aware datetime
    để Firestore Python SDK serialize thành Firestore Timestamp type,
    khớp với JS `new Date()` -> Firestore Timestamp trong app.
    App gọi `data.timestamp.toDate()` nên bắt buộc phải là Timestamp.

    Firestore fields:
      amount      (int)       — Số tiền
      note        (str)       — Ghi chú
      category    (str)       — Danh mục (Vietnamese)
      type        (int)       — 0=Chi, 1=Thu
      timestamp   (Timestamp) — UTC-aware datetime from dd/MM/yyyy
      yearMonth   (str)       — "YYYY-MM"
      year        (int)       — 4-digit year
      lastUpdated (Timestamp) — Server time
      createdBy   (str)       — Firebase UID
      deviceName  (str)       — "Telegram Bot"
      deviceId    (str)       — "telegram_bot"
    """
    date_str = parsed["date"]  # dd/MM/yyyy
    parts = date_str.split("/")
    dd, mm, yyyy = int(parts[0]), int(parts[1]), int(parts[2])

    # FIXED: Dùng UTC timezone để Firestore serialize thành Timestamp type
    # Khớp với JS: new Date(yyyy, mm - 1, dd) → Firestore Timestamp
    timestamp_dt = datetime(yyyy, mm, dd, tzinfo=timezone.utc)

    # Ép kiểu (cast) chặt chẽ để đảm bảo Android app nhận đúng Type (không bị parse lỗi ngầm)
    # THÊM CÁC TRƯỜNG MẶC ĐỊNH (date, isDeleted, is_synced) để tránh Kotlin Non-Null crash
    return {
        "amount": int(parsed["amount"]),
        "note": str(parsed["note"]),
        "category": str(parsed["category"]),
        "type": int(parsed["type"]),
        "date": date_str,  # BẮT BUỘC: app Android đọc trường này hoặc timestamp
        "timestamp": timestamp_dt,
        "yearMonth": f"{yyyy}-{mm:02d}",
        "year": int(yyyy),
        "lastUpdated": firestore.SERVER_TIMESTAMP,
        "createdBy": str(firebase_uid),
        "deviceName": "Telegram Bot",
        "deviceId": "telegram_bot",
        "source": str(parsed.get("source", "Tiền mặt")),
        "isDeleted": False,
        "is_synced": 1,
        "syncStatus": 1
    }


def _handle_start_command(bot_token: str, chat_id: int):
    """Xử lý lệnh /start khi người dùng lần đầu chat với bot."""
    send_telegram_message(
        bot_token,
        chat_id,
        "👋 *Chào mừng bạn đến với Sổ Thu Chi Bot!*\n\n"
        "Bot sẽ tự động phân tích và lưu các giao dịch bạn nhập.\n\n"
        "Bây giờ bạn có thể gửi giao dịch trực tiếp.\n"
        "📝 Ví dụ: `Ăn trưa 50k`"
    )

def _handle_help_command(bot_token: str, chat_id: int):
    """Xử lý lệnh /help — hiển thị hướng dẫn sử dụng."""
    send_telegram_message(
        bot_token,
        chat_id,
        "📖 *Hướng dẫn sử dụng Sổ Thu Chi Bot*\n\n"
        "*Lệnh:*\n"
        "• `/start` — Bắt đầu\n"
        "• `/help` — Hiển thị hướng dẫn này\n\n"
        "*Ghi giao dịch:*\n"
        "Chỉ cần nhắn tin bình thường bằng tiếng Việt:\n"
        "• `Ăn sáng 30k` → Chi 30,000đ, Ăn uống\n"
        "• `Nhận lương 15tr` → Thu 15,000,000đ\n"
        "🤖 Bot sẽ tự động nhận diện loại thu/chi, "
        "danh mục, số tiền và ngày tháng."
    )


def _send_saved_transaction_telegram_message(bot_token: str, chat_id: int, parsed: dict, doc_id: str):
    type_label = "Thu nhap" if parsed["type"] == 1 else "Chi tieu"
    amt = f"{parsed['amount']:,}d"
    cat_emoji = CATEGORY_EMOJIS.get(parsed["category"], "")
    source = parsed.get("source", "Ti\u1ec1n m\u1eb7t")
    msg = (
        f"Da ghi nhan thanh cong!\n\n"
        f"Loai: {type_label}\n"
        f"So tien: {amt}\n"
        f"Nguon: {source}\n"
        f"{cat_emoji} Danh muc: {parsed['category']}\n"
        f"Ghi chu: {parsed['note']}\n"
        f"Ngay: {parsed['date']}\n"
        f"ID: {doc_id}"
    )
    send_telegram_message(bot_token, chat_id, msg, reply_markup=_build_transaction_action_keyboard(doc_id))


def _send_auto_detect_telegram_notification(firebase_uid: str, parsed: dict) -> bool:
    try:
        user_doc = db.collection("users").document(firebase_uid).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        telegram_config = (user_data or {}).get("telegramConfig") or {}
        bot_token = telegram_config.get("botToken")
        chat_id = telegram_config.get("chatId")

        if not bot_token or not chat_id:
            print("[Telegram Auto Notify] Telegram config missing, skip auto notify")
            return False

        type_label = "Thu nhập" if int(parsed.get("type", 0) or 0) == 1 else "Chi tiêu"
        amount = int(parsed.get("amount", 0) or 0)
        amount_display = f"{amount:,}".replace(",", ".")
        source = str(parsed.get("source") or "Không rõ")
        note = str(parsed.get("note") or "").strip()[:120] or "Không có nội dung"
        msg = (
            "Đã ghi nhận giao dịch tự động:\n"
            f"- Loại: {type_label}\n"
            f"- Số tiền: {amount_display}đ\n"
            f"- Nguồn: {source}\n"
            f"- Nội dung: {note}"
        )
        send_telegram_message(bot_token, chat_id, msg)
        print("[Telegram Auto Notify] success")
        return True
    except Exception as notify_err:
        print(f"[Telegram Auto Notify] fail: {sanitize_log_text(notify_err)}")
        return False


# ==========================================
# MERCHANT LEARNING SYSTEM HELPERS
# ==========================================

# In-memory cache: key = "{uid}:__all__", value = {"rules": list, "cached_at": float}
_merchant_rule_cache: dict[str, dict] = {}
MERCHANT_CACHE_TTL_SECONDS = 300  # 5 phút


# --- Merchant Learning: noise constants ---
_NOISE_AMOUNT_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:tỷ|ty|triệu|trieu|tr|k|K|nghìn|nghin|ngàn|ngan|đ|d|vnd)\b"
    r"|\b\d{3,}\b",
    re.IGNORECASE | re.UNICODE,
)
_CURRENCY_TOKENS = frozenset({"k", "d", "vnd", "nghin", "ngan", "tr", "trieu", "ty", "dong"})
_ACTION_WORDS = frozenset({
    "mua", "ban", "thanh", "toan", "chuyen", "khoan", "tra",
    "nap", "rut", "gui", "chi", "thu", "ghi", "vay",
})
_SERVICE_GENERIC_PHRASES = (
    "cuoc dien thoai",
    "nap the dien thoai",
    "phi dich vu",
    "tien dien nuoc",
    "tien dien",
    "tien nuoc",
    "tien nha",
    "nap tien",
    "nap the",
    "dien thoai",
)  # Ordered: longer phrases first for greedy matching
_GENERIC_CATEGORY_WORDS = frozenset({
    "ca", "phe", "ca phe", "cafe", "an", "com", "uong", "tra", "sua",
    "nuoc", "hang", "sang", "trua", "toi", "chieu", "do",
    "thoai", "dien",  # fragments sau khi strip service phrases
})
_WALLET_PREFIXES = frozenset({
    "momo", "zalopay", "zalo", "vnpay", "tcb", "vcb", "mbbank",
    "mb", "techcombank", "vietcombank", "bidv", "vib", "acb", "vpbank",
    "tpbank", "ocb",
})
_MERCHANT_KEY_BLACKLIST = frozenset({
    "ca", "phe", "ca phe", "cafe", "an", "com", "uong", "tra", "sua",
    "hang", "nuoc", "do", "sang", "trua", "toi", "chieu",
    "an sang", "an trua", "an toi", "an com",  # generic meal phrases
    "tien", "tien mat", "cash", "thanh toan", "chuyen khoan",
    "mua", "ban", "nap", "rut", "gui",
    "dien", "thoai", "dien thoai",  # service fragments
})
_MIN_MERCHANT_KEY_LENGTH = 3


def normalize_merchant_key(text: str) -> str:
    """
    Chuẩn hóa text thành merchant key sạch.
    Pipeline: strip amounts → lowercase → remove accents → remove noise tokens.
    Ví dụ: "mua ca phe Highlands 65k" → "highlands"
    """
    if not text or not text.strip():
        return ""

    # Step 1: Strip amount patterns (BEFORE lowercase)
    s = _NOISE_AMOUNT_RE.sub(" ", text)

    # Step 2: Lowercase
    s = s.lower().strip()

    # Step 3: Remove accents
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")

    # Step 4: Remove non-letter chars
    s = re.sub(r"[^a-z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        return ""

    # Step 5: Remove service generic phrases (multi-word)
    for phrase in _SERVICE_GENERIC_PHRASES:
        s = re.sub(r"\b" + re.escape(phrase) + r"\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()

    # Step 6: Token-level filtering
    tokens = s.split()
    tokens = [t for t in tokens if t not in _CURRENCY_TOKENS]
    tokens = [t for t in tokens if t not in _ACTION_WORDS]

    # Strip wallet prefixes ONLY if other tokens remain
    non_prefix = [t for t in tokens if t not in _WALLET_PREFIXES]
    if non_prefix:
        tokens = non_prefix

    # Strip generic category words; nếu tất cả là generic → trả về "" (key không hợp lệ)
    non_generic = [t for t in tokens if t not in _GENERIC_CATEGORY_WORDS]
    tokens = non_generic  # Nếu rỗng → key rỗng → bị reject ở _MIN_MERCHANT_KEY_LENGTH check

    if not tokens:
        return ""

    result = " ".join(tokens).strip()
    return result[:50]


def extract_amount_vnd(text: str) -> Optional[int]:
    """
    Tìm số tiền VND trong text.
    Trả về int nếu tìm được đúng 1 amount rõ ràng, None nếu không tìm được hoặc ambiguous.
    """
    if not text:
        return None

    matches: list[int] = []

    # tỷ
    for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(?:tỷ|ty)\b', text, re.IGNORECASE):
        try:
            matches.append(int(float(m.group(1).replace(",", ".")) * 1_000_000_000))
        except ValueError:
            pass

    # triệu/tr
    for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(?:triệu|trieu|tr)\b', text, re.IGNORECASE):
        try:
            matches.append(int(float(m.group(1).replace(",", ".")) * 1_000_000))
        except ValueError:
            pass

    # k/K/nghìn/ngàn (chỉ nếu chưa có match tr/tỷ)
    if not matches:
        for m in re.finditer(r'(\d+(?:[.,]\d+)?)\s*(?:k|K|nghìn|nghin|ngàn|ngan)\b', text, re.IGNORECASE):
            try:
                matches.append(int(float(m.group(1).replace(",", ".")) * 1_000))
            except ValueError:
                pass

    # số nguyên >= 4 chữ số (fallback khi không có đơn vị)
    if not matches:
        for m in re.finditer(r'\b(\d{4,})\b', text):
            try:
                matches.append(int(m.group(1)))
            except ValueError:
                pass

    if len(matches) == 1 and matches[0] > 0:
        return matches[0]
    return None  # 0 hoặc >1 match → ambiguous


def _is_likely_multi_transaction_text(text: str) -> bool:
    """
    True nếu text có khả năng chứa nhiều giao dịch riêng biệt.
    Tiêu chí 1: >= 2 amounts với đơn vị tiền rõ ràng (k, tr, tỷ, đ, vnd).
    Tiêu chí 2: >= 2 bare numbers (>= 4 chữ số) + dấu ngắt câu có nghĩa.
    """
    # Criterion 1: >= 2 amounts có đơn vị rõ ràng
    explicit_amounts = re.findall(
        r'\d+(?:[.,]\d+)?\s*(?:tỷ|ty|triệu|trieu|tr|k|K|nghìn|nghin|ngàn|ngan|đ|vnd)\b',
        text, re.IGNORECASE,
    )
    if len(explicit_amounts) >= 2:
        return True

    # Criterion 2: >= 2 bare numbers + separator
    bare_amounts = re.findall(r'\b\d{4,}\b', text)
    if len(bare_amounts) >= 2:
        has_separator = bool(re.search(
            r'[,;]|\bvà\b|\band\b|\bsáng\b|\btrưa\b|\btối\b|\bchiều\b',
            text, re.IGNORECASE,
        ))
        if has_separator:
            return True

    return False


def _invalidate_merchant_cache(firebase_uid: str) -> None:
    """Xóa cache của user để force reload từ Firestore lần sau."""
    keys_to_delete = [k for k in _merchant_rule_cache if k.startswith(f"{firebase_uid}:")]
    for k in keys_to_delete:
        _merchant_rule_cache.pop(k, None)


def _load_merchant_rules_for_user(firebase_uid: str) -> list[dict]:
    """Load tất cả merchant rules của user từ cache hoặc Firestore."""
    cache_key = f"{firebase_uid}:__all__"
    now = time.time()
    cached = _merchant_rule_cache.get(cache_key)
    if cached and (now - cached["cached_at"]) < MERCHANT_CACHE_TTL_SECONDS:
        return cached["rules"]
    try:
        rules_ref = (
            db.collection("users")
            .document(firebase_uid)
            .collection("merchant_rules")
        )
        rules = [doc.to_dict() for doc in rules_ref.stream() if doc.to_dict()]
        _merchant_rule_cache[cache_key] = {"rules": rules, "cached_at": now}
        return rules
    except Exception as e:
        print(f"[MerchantRule] Load error: {e}")
        return []


def find_matching_merchant_rule(firebase_uid: str, user_text: str) -> Optional[dict]:
    """
    Tìm merchant rule phù hợp nhất với user_text dựa trên token subset matching.
    Có blacklist để loại key quá generic. Ưu tiên rule confidence cao + key dài hơn.
    """
    if not user_text or not firebase_uid:
        return None
    normalized_input = normalize_merchant_key(user_text)
    print(f"[MerchantLearning] normalized_user_text='{normalized_input}'")
    if not normalized_input or len(normalized_input) < _MIN_MERCHANT_KEY_LENGTH:
        print("[MerchantLearning] skip_reason=normalized_too_short")
        return None
    if normalized_input in _MERCHANT_KEY_BLACKLIST:
        print("[MerchantLearning] skip_reason=blacklisted_input")
        return None

    input_tokens = set(normalized_input.split())
    if not input_tokens:
        return None

    rules = _load_merchant_rules_for_user(firebase_uid)
    candidates = []

    for rule in rules:
        merchant_key = rule.get("merchant_key", "")
        if not merchant_key or len(merchant_key) < _MIN_MERCHANT_KEY_LENGTH:
            continue
        if merchant_key in _MERCHANT_KEY_BLACKLIST:
            continue
        key_tokens = set(merchant_key.split())
        if not key_tokens:
            continue
        # Tất cả token của rule phải nằm trong input
        if not key_tokens.issubset(input_tokens):
            continue
        overlap_ratio = len(key_tokens) / max(len(input_tokens), 1)
        confidence = float(rule.get("confidence", 0.5))
        score = overlap_ratio * confidence
        # Tie-break: ưu tiên key dài hơn (cụ thể hơn) khi score bằng nhau
        candidates.append((score, len(key_tokens), rule))

    if not candidates:
        print("[MerchantLearning] candidate_rules=none")
        return None

    print(f"[MerchantLearning] candidate_rules={len(candidates)}")
    # Sort: score cao nhất trước; cùng score → key dài hơn trước (more specific)
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    best_score, _, best_rule = candidates[0]
    print(f"[MerchantLearning] matched_rule='{best_rule.get('merchant_key')}' score={best_score:.3f}")

    if best_score >= 0.3:
        return best_rule
    print(f"[MerchantLearning] skip_reason=score_too_low({best_score:.3f})")
    return None


def update_merchant_rule_from_transaction(firebase_uid: str, transaction: dict) -> None:
    """
    Tự động học merchant rule sau khi transaction lưu thành công.
    Guards: category != 'Khác' (trừ user_corrected), amount > 0, source/note đủ rõ.
    """
    if not ENABLE_MERCHANT_LEARNING:
        return

    category = transaction.get("category", "")
    amount = transaction.get("amount", 0)
    source = str(transaction.get("source", "")).strip()
    note = str(transaction.get("note", "")).strip()
    tx_type = int(transaction.get("type", 0))
    is_user_corrected = transaction.get("_source_type") == "user_corrected"

    # Guards
    if not category:
        return
    if category == "Khác" and not is_user_corrected:
        return
    if not isinstance(amount, (int, float)) or amount <= 0:
        return

    # Chọn merchant text: ưu tiên source (Momo, bank...), fallback note
    _generic = {"tiền mặt", "tien mat", "cash", "telegram bot", "telegram", ""}
    merchant_text = source if source.lower() not in _generic else note
    if not merchant_text or len(merchant_text) < 3:
        return

    merchant_key = normalize_merchant_key(merchant_text)
    if not merchant_key or len(merchant_key) < 3:
        return

    try:
        rule_ref = (
            db.collection("users")
            .document(firebase_uid)
            .collection("merchant_rules")
            .document(merchant_key[:50])
        )
        now_ts = firestore.SERVER_TIMESTAMP
        rule_snap = rule_ref.get()

        if rule_snap.exists:
            current_conf = float((rule_snap.to_dict() or {}).get("confidence", 0.5))
            rule_ref.update({
                "category": category,
                "type": tx_type,
                "usage_count": firestore.Increment(1),
                "confidence": min(0.95, current_conf + 0.05),
                "last_used_at": now_ts,
                "updated_at": now_ts,
            })
        else:
            rule_ref.set({
                "merchant": merchant_text[:100],
                "merchant_key": merchant_key[:50],
                "category": category,
                "type": tx_type,
                "source": "ai_learned",
                "usage_count": 1,
                "confidence": 0.5,
                "created_at": now_ts,
                "last_used_at": now_ts,
                "last_corrected_at": None,
                "updated_at": now_ts,
            })

        _invalidate_merchant_cache(firebase_uid)
        print(f"[MerchantRule] Learned '{merchant_key}' → '{category}' for uid={firebase_uid}")
    except Exception as e:
        print(f"[MerchantRule] update_from_transaction error: {e}")


def update_merchant_rule_from_correction(
    firebase_uid: str, source_text: str, new_category: str, tx_type: int
) -> None:
    """
    Cập nhật merchant rule khi user manually sửa category qua Telegram button.
    Tăng confidence + 0.2, set last_corrected_at, source = 'user_corrected'.
    """
    if not ENABLE_MERCHANT_LEARNING:
        return
    if not source_text or len(source_text.strip()) < 3:
        return
    if not new_category:
        return

    merchant_key = normalize_merchant_key(source_text)
    if not merchant_key or len(merchant_key) < 3:
        return

    try:
        rule_ref = (
            db.collection("users")
            .document(firebase_uid)
            .collection("merchant_rules")
            .document(merchant_key[:50])
        )
        now_ts = firestore.SERVER_TIMESTAMP
        rule_snap = rule_ref.get()

        if rule_snap.exists:
            current_conf = float((rule_snap.to_dict() or {}).get("confidence", 0.5))
            rule_ref.update({
                "category": new_category,
                "type": tx_type,
                "source": "user_corrected",
                "confidence": min(1.0, current_conf + 0.2),
                "usage_count": firestore.Increment(1),
                "last_corrected_at": now_ts,
                "last_used_at": now_ts,
                "updated_at": now_ts,
            })
        else:
            # Tạo mới với confidence cao hơn (user đã confirm)
            rule_ref.set({
                "merchant": source_text[:100],
                "merchant_key": merchant_key[:50],
                "category": new_category,
                "type": tx_type,
                "source": "user_corrected",
                "usage_count": 1,
                "confidence": 0.7,
                "created_at": now_ts,
                "last_used_at": now_ts,
                "last_corrected_at": now_ts,
                "updated_at": now_ts,
            })

        _invalidate_merchant_cache(firebase_uid)
        print(f"[MerchantRule] Correction '{merchant_key}' → '{new_category}' for uid={firebase_uid}")
    except Exception as e:
        print(f"[MerchantRule] update_from_correction error: {e}")


def _try_merchant_bypass(firebase_uid: str, text: str, is_auto_detect: bool) -> Optional[dict]:
    """
    Thử bypass AI parser dựa trên merchant rule.
    Chỉ được gọi khi ENABLE_MERCHANT_LEARNING=True AND ENABLE_MERCHANT_BYPASS=True.
    Multi-tx guard đã được xử lý ở process_ai_and_save() trước khi gọi hàm này.
    Trả về parsed dict nếu bypass thành công, None nếu cần fallback AI.
    """
    if is_auto_detect:
        print("[MerchantLearning] skip_reason=is_auto_detect")
        return None

    rule = find_matching_merchant_rule(firebase_uid, text)
    if not rule:
        print("[MerchantLearning] skip_reason=no_rule_match")
        return None

    usage_count = int(rule.get("usage_count", 0))
    confidence = float(rule.get("confidence", 0.0))
    if usage_count < 2 and confidence < 0.8:
        print(
            f"[MerchantLearning] skip_reason=low_confidence "
            f"(count={usage_count}, conf={confidence:.2f})"
        )
        return None

    # Validate category hợp lệ theo tx_type
    category = rule.get("category", "")
    tx_type = int(rule.get("type", 0))
    valid_cats = INCOME_CATEGORIES if tx_type == 1 else EXPENSE_CATEGORIES
    if not category or category not in valid_cats:
        print(f"[MerchantLearning] skip_reason=invalid_category('{category}')")
        return None

    amount = extract_amount_vnd(text)
    if not amount or amount <= 0:
        print("[MerchantLearning] skip_reason=no_unambiguous_amount")
        return None

    now_vn = datetime.now(tz=VN_TZ)
    today_str = now_vn.strftime("%d/%m/%Y")
    merchant_name = rule.get("merchant", "Tiền mặt")

    print(
        f"[MerchantLearning] BYPASS merchant='{rule.get('merchant_key')}' "
        f"category='{category}' amount={amount} type={tx_type}"
    )
    return {
        "type": tx_type,
        "amount": amount,
        "category": category,
        "note": text[:50],
        "date": today_str,
        "source": merchant_name,
    }


def _process_ai_and_save_multi(
    bot_token: Optional[str],
    firebase_uid: str,
    chat_id: Optional[int],
    text: str,
    is_auto_detect: bool = False,
    package_name: Optional[str] = None,
):
    omitted_count = 0
    try:
        parsed_items = analyze_text_multi_transactions(text)
    except Exception as multi_err:
        print(f"[MULTI_PARSE] fallback legacy reason: {multi_err}")
        parsed_items = [analyze_text_with_gemini(text)]

    if parsed_items == "ERROR_TIMEOUT" or any(item == "ERROR_TIMEOUT" for item in parsed_items):
        overload_msg = "AI is overloaded. Please try again later."
        if bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, overload_msg)
        return

    print(f"[MULTI_PARSE] item count: {len(parsed_items)}")

    if len(parsed_items) > MAX_MULTI_TRANSACTIONS:
        omitted_count = len(parsed_items) - MAX_MULTI_TRANSACTIONS
        parsed_items = parsed_items[:MAX_MULTI_TRANSACTIONS]

    id_prefix = "at" if is_auto_detect else "reqtele"
    saved_count = 0
    skipped_count = 0

    for parsed in parsed_items:
        try:
            if is_auto_detect:
                parsed = _apply_auto_notification_source(parsed, package_name)
            print(
                f"[AI Multi Item Result] type={parsed.get('type')}, amount={parsed.get('amount')}, "
                f"source={parsed.get('source', '')}"
            )
            firestore_data = _build_firestore_payload(parsed, firebase_uid)
            try:
                doc_id = _save_transaction_atomic(firebase_uid, firestore_data, id_prefix)
                print("[Auto Notification] Firestore save success" if is_auto_detect else "[Firestore] Save success")
            except Exception as firestore_err:
                print(f"[Auto Notification] Firestore save fail: {sanitize_log_text(firestore_err)}")
                raise
            saved_count += 1

            try:
                _send_fcm_notification(firebase_uid, doc_id, parsed)
            except Exception as fcm_err:
                print(f"[FCM] Non-critical error, ignoring: {fcm_err}")

            if is_auto_detect:
                _send_auto_detect_telegram_notification(firebase_uid, parsed)

            # [MERCHANT LEARNING] Học rule từ từng item trong batch sau khi lưu thành công
            if ENABLE_MERCHANT_LEARNING:
                try:
                    update_merchant_rule_from_transaction(firebase_uid, parsed)
                except Exception as rule_err:
                    print(f"[MerchantRule] Non-critical multi-tx rule error: {rule_err}")


            if parsed.get("type") == 0:
                try:
                    from agentic_ai import check_budget_thresholds
                    check_budget_thresholds(firebase_uid, parsed.get("category", "Kh\u00e1c"), float(parsed.get("amount", 0)))
                except Exception as budget_err:
                    print(f"[Budget Check] Non-critical error, ignoring: {budget_err}")

            if bot_token and chat_id:
                _send_saved_transaction_telegram_message(bot_token, chat_id, parsed, doc_id)
        except Exception as item_err:
            skipped_count += 1
            print(f"[AI Multi Item Error] Skipping item due to error: {item_err}")
            traceback.print_exc()

    if bot_token and chat_id and (len(parsed_items) > 1 or skipped_count > 0 or omitted_count > 0):
        summary_msg = f"Tong ket: da luu {saved_count} giao dich."
        if skipped_count > 0:
            summary_msg += f"\nBo qua {skipped_count} giao dich do loi du lieu/luu tru."
        if omitted_count > 0:
            summary_msg += f"\nBo qua {omitted_count} giao dich vi vuot gioi han an toan {MAX_MULTI_TRANSACTIONS} giao dich/lan."
        send_telegram_message(bot_token, chat_id, summary_msg)

    if saved_count == 0:
        raise ValueError("No transaction was saved.")

def process_ai_and_save(
    bot_token: Optional[str],
    firebase_uid: str,
    chat_id: Optional[int],
    text: str,
    is_auto_detect: bool = False,
    package_name: Optional[str] = None,
    notification_title: Optional[str] = None,
    notification_text: Optional[str] = None,
):
    """
    Background Task — KHÔNG có network call nào trong Firestore Transaction.
    Flow: AI parse (network) → Atomic Firestore write → Telegram reply (network).
    """
    try:
        print(
            f"[Process] chat_id_present={bool(chat_id)}, uid_present={bool(firebase_uid)}, "
            f"text_length={len(text)}"
        )
        print(f"[MULTI_PARSE] enabled={ENABLE_MULTI_TRANSACTION_PARSE}")

        parsed = None
        deterministic_auto = None
        if is_auto_detect:
            mapped_source = map_package_to_source(package_name or "") or str(package_name or "").strip()
            print(f"[AutoParser] package={package_name or ''} source={mapped_source}")
            print("[AutoParser] deterministic_attempt=True")
            deterministic_auto = parse_auto_notification_deterministic(
                notification_title or "",
                notification_text or text,
                package_name or "",
            )
            if deterministic_auto is None:
                print("[AutoParser] deterministic_success=False")
                print("[AutoParser] ai_fallback=False")
                return
            if _auto_deterministic_ready(deterministic_auto):
                parsed = _merge_auto_notification_parse(deterministic_auto, None)
                locked_fields = ",".join(
                    field
                    for field in ("amount", "type", "source", "note")
                    if field in set(deterministic_auto.get("_locked_fields") or set())
                )
                print("[AutoParser] deterministic_success=True")
                print(f"[AutoParser] locked_fields={locked_fields}")
                print("[AutoParser] ai_fallback=False")
                print(f"[AutoParser] note_preview={_auto_parser_note_preview(parsed)}")
                print("[Auto Notification] deterministic parse ready, skipping AI")
            else:
                print("[AutoParser] deterministic_success=False")
                print("[AutoParser] ai_fallback=True")
                print(f"[AutoParser] reason={_auto_parser_missing_reason(deterministic_auto)}")

        # 2. Phân loại text → route thích hợp
        is_multi = _is_likely_multi_transaction_text(text)
        print(
            f"[MerchantLearning] text_type={'multi' if is_multi else 'single'} "
            f"multi_parse={ENABLE_MULTI_TRANSACTION_PARSE} bypass={ENABLE_MERCHANT_BYPASS}"
        )

        if parsed is None and is_multi and ENABLE_MULTI_TRANSACTION_PARSE:
            print("[MULTI_PARSE] using multi flow")
            _process_ai_and_save_multi(bot_token, firebase_uid, chat_id, text, is_auto_detect, package_name)
            return

        # Single-transaction path (hoặc multi text với MULTI_PARSE=false → legacy AI)
        if parsed is None and not is_multi and ENABLE_MERCHANT_LEARNING and ENABLE_MERCHANT_BYPASS:
            parsed = _try_merchant_bypass(firebase_uid, text, is_auto_detect)

        if parsed is None:
            if is_multi:
                print("[MerchantLearning] multi text + MULTI_PARSE disabled → FALLBACK_AI")
            else:
                print("[MerchantLearning] FALLBACK_AI")
            try:
                parsed = analyze_text_with_gemini(text)
                if is_auto_detect and deterministic_auto:
                    parsed = _merge_auto_notification_parse(deterministic_auto, parsed)
                print("[Auto Notification] AI parse success" if is_auto_detect else "[AI Parse] success")
            except Exception as ai_err:
                print(f"[Auto Notification] AI parse fail: {sanitize_log_text(ai_err)}")
                if is_auto_detect and _auto_deterministic_complete(deterministic_auto):
                    parsed = _merge_auto_notification_parse(deterministic_auto or {}, None)
                    print("[Auto Notification] deterministic parse retained after AI failure")
                elif is_auto_detect:
                    print("[Auto Notification] skip: AI failed and deterministic amount/type is incomplete")
                    return
                else:
                    raise
        else:
            print("[MerchantLearning] BYPASS success, skipping AI call")
        if parsed == "ERROR_TIMEOUT":
            overload_msg = "❌ Xin lỗi bạn, hệ thống AI của Google hiện đang quá tải. Bạn vui lòng thử lại sau ít phút nhé!"
            if bot_token and chat_id:
                send_telegram_message(bot_token, chat_id, overload_msg)
            return

        if is_auto_detect:
            parsed = _apply_auto_notification_source(parsed, package_name)
            parsed["note"] = sanitize_transaction_note(parsed.get("note", ""))
            if not parsed.get("amount") or parsed.get("type") not in (0, 1):
                print("[Auto Notification] skip: amount/type unavailable after parser merge")
                return

        print(
            f"[AI Result] type={parsed.get('type')}, amount={parsed.get('amount')}, "
            f"source={parsed.get('source', '')}"
        )

        # 3. Build payload — NGOÀI transaction
        firestore_data = _build_firestore_payload(parsed, firebase_uid)

        # 4. ATOMIC: counter + write trong 1 transaction duy nhất
        id_prefix = "at" if is_auto_detect else "reqtele"
        try:
            doc_id = _save_transaction_atomic(firebase_uid, firestore_data, id_prefix)
            print("[Auto Notification] Firestore save success" if is_auto_detect else "[Firestore] Save success")
        except Exception as firestore_err:
            print(f"[Auto Notification] Firestore save fail: {sanitize_log_text(firestore_err)}")
            raise

        # 4b. Gửi FCM silent notification — kích hoạt sync khi app bị kill/background
        # Không ảnh hưởng flow chính nếu FCM lỗi
        try:
            _send_fcm_notification(firebase_uid, doc_id, parsed)
        except Exception as fcm_err:
            print(f"[FCM] Non-critical error, ignoring: {fcm_err}")

        if is_auto_detect:
            _send_auto_detect_telegram_notification(firebase_uid, parsed)

        # [MERCHANT LEARNING] Hoc rule tu transaction da luu thanh cong
        if ENABLE_MERCHANT_LEARNING:
            try:
                rule_data = {**parsed, "source": firestore_data.get("source", parsed.get("source", "Tien mat"))}
                update_merchant_rule_from_transaction(firebase_uid, rule_data)
            except Exception as rule_err:
                print(f"[MerchantRule] Non-critical post-save error: {rule_err}")


        # 4c. KIỂM TRA NGÂN SÁCH (Phase 3 - Dynamic Budgeting)
        # Chỉ kiểm tra cho các khoản CHI TIÊU (type == 0)
        if parsed.get("type") == 0:
            try:
                from agentic_ai import check_budget_thresholds
                check_budget_thresholds(firebase_uid, parsed.get("category", "Khác"), float(parsed.get("amount", 0)))
            except Exception as budget_err:
                print(f"[Budget Check] Non-critical error, ignoring: {budget_err}")

        # 5. Telegram reply — NGOÀI transaction (chỉ gửi nếu đến từ Telegram)
        if bot_token and chat_id:
            type_label = "Thu nhập" if parsed["type"] == 1 else "Chi tiêu"
            amt = f"{parsed['amount']:,}đ"
            cat_emoji = CATEGORY_EMOJIS.get(parsed["category"], "")
            source = parsed.get("source", "Tiền mặt")
            msg = (
                f"✅Đã ghi nhận thành công!\n\n"
                f"Loại: {type_label}\n"
                f"Số tiền: {amt}\n"
                f"Nguồn: {source}\n"
                f"{cat_emoji} Danh mục: {parsed['category']}\n"
                f"Ghi chú: {parsed['note']}\n"
                f"Ngày: {parsed['date']}\n"
                f"ID: {doc_id}"
            )
            send_telegram_message(bot_token, chat_id, msg, reply_markup=_build_transaction_action_keyboard(doc_id))

    except json.JSONDecodeError as e:
        print(f"[AI Parse Error] {e}")
        traceback.print_exc()
        if bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, "Khong the hieu noi dung. Vi du: An trua 50k")
    except requests.exceptions.RequestException as e:
        print(f"[AI API Error] {e}")
        traceback.print_exc()
        if bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, "Loi ket noi AI. Vui long thu lai sau.")
    except Exception as e:
        print(f"[Error] process_ai_and_save: {e}")
        traceback.print_exc()
        if bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, f"Da co loi xay ra: {str(e)[:150]}")


@app.post("/webhook/telegram/{bot_token}")
async def telegram_webhook(bot_token: str, request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint động — Xử lý cho nhiều bot khác nhau.
    """
    try:
        data = await request.json()
    except Exception as e:
        print(f"[Webhook] Failed to parse JSON: {e}")
        return {"status": "ok"}  

    if "callback_query" in data:
        callback_query = data.get("callback_query") or {}
        callback_query_id = callback_query.get("id")
        callback_data = callback_query.get("data", "")
        message = callback_query.get("message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if not callback_query_id:
            return {"status": "ok"}

        firebase_uid = _get_uid_from_bot_token(bot_token)
        if not firebase_uid:
            _answer_telegram_callback(bot_token, callback_query_id, "Bot chưa được liên kết.")
            if chat_id:
                send_telegram_message(bot_token, chat_id, "⚠️ Bot chưa được liên kết trên app Sổ Thu Chi.")
            return {"status": "ok"}

        if not chat_id:
            _answer_telegram_callback(bot_token, callback_query_id, "Không tìm thấy chat để phản hồi.")
            return {"status": "ok"}

        _handle_transaction_callback(bot_token, firebase_uid, chat_id, callback_query_id, callback_data)
        return {"status": "ok"}

    if "message" in data and "text" in data.get("message", {}):
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"].strip()

        # Dùng bot_token để tìm chủ nhân
        firebase_uid = _get_uid_from_bot_token(bot_token)
        if not firebase_uid:
            send_telegram_message(bot_token, chat_id, "⚠️ Bot chua duoc lien ket tren app So Thu Chi.")
            return {"status": "ok"}
            
        # Lưu chat_id vào Firestore để Cron Job có thể gửi báo cáo chủ động
        try:
            db.collection("users").document(firebase_uid).set({
                "telegramConfig": {
                    "chatId": chat_id
                }
            }, merge=True)
        except Exception as e:
            print(f"[Webhook] Lỗi khi lưu chatId: {e}")

        if text.lower() == "/start":
            msg = "✅ Bot da ket noi voi So Thu Chi!\nBan co the nhan tin nhu: 'An sang 30k'"
            try:
                from agentic_ai import ensure_default_external_brief_task_for_user, ensure_default_finance_report_task_for_user
                ensure_default_external_brief_task_for_user(firebase_uid)
                ensure_default_finance_report_task_for_user(firebase_uid)
            except Exception as task_error:
                print(f"[Webhook] Cannot ensure external brief task for {firebase_uid}: {task_error}")
            background_tasks.add_task(send_telegram_message, bot_token, chat_id, msg)
        elif text.lower().startswith("/setreport"):
            parts = text.split(maxsplit=1)
            user_time = parts[1].strip() if len(parts) > 1 else "20:00"
            from agentic_ai import create_custom_finance_report_task
            result = create_custom_finance_report_task(firebase_uid, user_time, "daily", "daily_finance_report", "today")
            send_telegram_message(bot_token, chat_id, json.loads(result).get("message", "Da len lich bao cao."))
        elif text.lower() == "/myreports":
            from agentic_ai import list_finance_report_tasks
            send_telegram_message(bot_token, chat_id, list_finance_report_tasks(firebase_uid))
        elif text.lower() == "/stopreport":
            from agentic_ai import stop_custom_finance_reports
            send_telegram_message(bot_token, chat_id, stop_custom_finance_reports(firebase_uid))
        elif text.lower() == "/help":
            background_tasks.add_task(_handle_help_command, bot_token, chat_id)
        else:
            # Phản hồi ngay lập tức để cải thiện UX
            waiting_msg = "⏳ Bot đã lắng nghe yêu cầu của bạn rồi ạ , vui lòng đợi 1 xíu nha..."
            send_telegram_message(bot_token, chat_id, waiting_msg)
            
            # Phân tích cơ bản để xem người dùng đang "ghi chép" hay "hỏi đáp/báo cáo"
            lower_text = _normalize_intent_text(text)
            manual_report_type = _detect_manual_report_task_type(text)
            is_query = manual_report_type is not None or any(keyword in lower_text for keyword in [
                "?", "bao cao", "ban tin", "tong", "bao nhieu", "thong ke", "dat", "han muc", "ngan sach", "gioi han",
                "báo cáo", "bản tin", "tổng", "bao nhiêu",
                "thống kê", "đặt", "hạn mức", "ngân sách", "giới hạn", "giá vàng",
                "gia vang", "giá xăng", "gia xang", "xăng dầu", "xang dau", "openai",
                "chatgpt", "claude", "gemini", "deepseek", "gpt", "sjc", "pnj",
                "gia ai", "goi ai", "morning brief", "tai chinh ngoai", "du lieu ngoai", "thi truong",
                "lich bao cao", "huy lich", "xem lich"
            ])
            
            is_query = (
                manual_report_type is not None
                or _is_finance_report_schedule_request(lower_text)
                or _is_disable_report_schedule_request(lower_text)
                or _is_list_report_schedule_request(lower_text)
                or _is_budget_alert_request(lower_text)
                or _is_finance_query_request(lower_text)
                or "?" in lower_text
            )

            if is_query:
                background_tasks.add_task(process_agentic_query, bot_token, firebase_uid, chat_id, text)
            else:
                background_tasks.add_task(process_ai_and_save, bot_token, firebase_uid, chat_id, text)

    # --- DISPATCHER: Xử lý ảnh hóa đơn (Photo Handler) ---
    # Tách biệt hoàn toàn khỏi luồng text phía trên
    elif "message" in data and "photo" in data.get("message", {}):
        message = data["message"]
        chat_id = message["chat"]["id"]
        caption = message.get("caption", "")

        # Xác định chủ nhân của bot
        firebase_uid = _get_uid_from_bot_token(bot_token)
        if not firebase_uid:
            send_telegram_message(bot_token, chat_id, "⚠️ Bot chưa được liên kết trên app Sổ Thu Chi.")
            return {"status": "ok"}

        # Lấy ảnh resolution cao nhất (photo[-1] là kích thước lớn nhất)
        photos = message["photo"]
        file_id = photos[-1]["file_id"]

        # Lấy thời gian hiện tại (VN_TZ) để AI biết "hôm nay" là ngày nào
        now_vn = datetime.now(tz=VN_TZ)
        current_time_str = now_vn.strftime("%Y-%m-%dT%H:%M:%S%z")

        print(f"[Webhook] Nhận ảnh hóa đơn từ chat_id={chat_id}, uid={firebase_uid}, file_id={file_id}, caption='{caption}'")

        # Phản hồi ngay để người dùng biết bot đang xử lý
        send_telegram_message(bot_token, chat_id, "🔍 Đang đọc hóa đơn, vui lòng chờ tớ một tí ...")

        # Đẩy vào background để không block webhook response
        from vision_parser import parse_receipt_image
        background_tasks.add_task(parse_receipt_image, bot_token, file_id, firebase_uid, chat_id, caption, current_time_str)

    return {"status": "ok"}


@app.post("/api/notification/process")
async def process_notification(req: NotificationProcessRequest, background_tasks: BackgroundTasks):
    """
    Endpoint nhận raw text từ Android NotificationListenerService.
    Chỉ dùng background_tasks để gọi process_ai_and_save (cùng logic với Telegram),
    nhưng không cần Telegram bot_token hay chat_id (truyền None).
    """
    # Gộp title và text để AI dễ phân tích
    combined_text = f"Thông báo từ ứng dụng {req.package_name}: {req.title} - {req.text}"
    print("[Notification API] /api/notification/process received")
    print(f"[Notification API] firebase_uid_present={bool(req.firebase_uid.strip())}")
    print(f"[Notification API] package_name={req.package_name}")
    print(f"[Notification API] text_length={len(combined_text)}")
    
    # process_ai_and_save xử lý phân tích và lưu, nếu thành công sẽ gửi FCM push notification
    background_tasks.add_task(
        process_ai_and_save,
        None,
        req.firebase_uid,
        None,
        combined_text,
        True,
        req.package_name,
        req.title,
        req.text,
    )
    
    return {"status": "processing"}


if __name__ == "__main__":
    # Render cấp biến PORT động, mặc định là 8000 nếu chạy local
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False if os.getenv("PORT") else True)
