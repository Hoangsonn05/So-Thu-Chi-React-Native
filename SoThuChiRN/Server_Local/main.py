import os
import re
import json
import tempfile
import traceback
import resend
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import firebase_admin
import pandas as pd
import uvicorn
import requests
from openpyxl.styles import Border, Font, Side
from openpyxl.utils import get_column_letter
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Response
from contextlib import asynccontextmanager
from firebase_admin import credentials, firestore, messaging
from pydantic import BaseModel, Field
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

# Load environment variables from .env file in the same directory (with override)
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# --- CẤU HÌNH RESEND (Gửi Email) ---
resend.api_key = os.getenv("RESEND_API_KEY")

# --- CẤU HÌNH WEBHOOK (Động cho từng User) ---
BASE_WEBHOOK_URL = os.getenv("BASE_WEBHOOK_URL", "")
print(f"🚀 [INIT] BASE_WEBHOOK_URL: {BASE_WEBHOOK_URL if BASE_WEBHOOK_URL else 'NOT FOUND'}")

# --- CẤU HÌNH AI (OPENROUTER - THAY THẾ GEMINI) ---
OPENROUTER_API_KEY = "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"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-super-120b-a12b:free"

# Multi transaction parsing is high-risk; keep disabled by default.
ENABLE_MULTI_TRANSACTION_PARSE = os.getenv("ENABLE_MULTI_TRANSACTION_PARSE", "false").strip().lower() in {"1", "true", "yes", "on"}
MAX_MULTI_TRANSACTIONS = 5

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
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()

@asynccontextmanager
async def lifespan(app: FastAPI):
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from agentic_ai import poll_scheduled_tasks_job, recurring_expenses_daily_job
    scheduler = AsyncIOScheduler()
    # Chạy polling mỗi 1 phút
    scheduler.add_job(poll_scheduled_tasks_job, 'interval', minutes=1)
    scheduler.add_job(recurring_expenses_daily_job, 'cron', hour=9, minute=0, timezone=VN_TZ)
    scheduler.start()
    print("[Scheduler] Đã khởi động Polling Job mỗi phút.")
    yield
    scheduler.shutdown()

app = FastAPI(title="Firestore Export & Telegram Bot API", lifespan=lifespan)

def process_agentic_query(bot_token: str, firebase_uid: str, chat_id: int, text: str):
    """ Xử lý Agentic AI Workflow cho các câu truy vấn báo cáo tài chính """
    from agentic_ai import chat_with_agentic_ai
    try:
        print(f"[Agentic] Bắt đầu xử lý truy vấn cho UID: {firebase_uid}")
        reply = chat_with_agentic_ai(text, firebase_uid)
        if reply:
            send_telegram_message(bot_token, chat_id, reply)
        else:
            send_telegram_message(bot_token, chat_id, "Xin lỗi, tôi không thể truy xuất thông tin lúc này.")
    except Exception as e:
        print(f"[Agentic Error] {e}")
        traceback.print_exc()
        send_telegram_message(bot_token, chat_id, "Đã có lỗi xảy ra khi xử lý yêu cầu của bạn.")


class ExportEmailRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    userEmail: str = Field(..., min_length=1)

class NotificationProcessRequest(BaseModel):
    firebase_uid: str
    title: str
    text: str
    package_name: str


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
        print(f"[SetupBot] Calling Telegram API: {tg_api}")
        
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
    
    print(f"\n[AI Request] Đang gửi yêu cầu phân tích văn bản cho AI:")
    print(f"--- TEXT: '{user_text}' ---")

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
        print(f"[AI Response Raw]: '{raw_text}'")
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
            print(f"[AI Parse Error] Không tìm thấy JSON hợp lệ trong phản hồi. Văn bản: '{cleaned}'")
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

    print(f"\n[AI Multi Request] Äang gá»­i yÃªu cáº§u phÃ¢n tÃ­ch nhiá»u giao dá»‹ch:")
    print(f"--- TEXT: '{user_text}' ---")

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

def _process_ai_and_save_multi(bot_token: Optional[str], firebase_uid: str, chat_id: Optional[int], text: str, is_auto_detect: bool = False):
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
            print(f"[AI Multi Item Result] {parsed}")
            firestore_data = _build_firestore_payload(parsed, firebase_uid)
            doc_id = _save_transaction_atomic(firebase_uid, firestore_data, id_prefix)
            saved_count += 1

            try:
                _send_fcm_notification(firebase_uid, doc_id, parsed)
            except Exception as fcm_err:
                print(f"[FCM] Non-critical error, ignoring: {fcm_err}")

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

def process_ai_and_save(bot_token: Optional[str], firebase_uid: str, chat_id: Optional[int], text: str, is_auto_detect: bool = False):
    """
    Background Task — KHÔNG có network call nào trong Firestore Transaction.
    Flow: AI parse (network) → Atomic Firestore write → Telegram reply (network).
    """
    try:
        print(f"[Process] chat_id={chat_id}, uid={firebase_uid}, text='{text[:50]}'")
        print(f"[MULTI_PARSE] enabled={ENABLE_MULTI_TRANSACTION_PARSE}")

        # 2. Gọi AI — NGOÀI transaction
        if ENABLE_MULTI_TRANSACTION_PARSE:
            print("[MULTI_PARSE] using multi flow")
            _process_ai_and_save_multi(bot_token, firebase_uid, chat_id, text, is_auto_detect)
            return

        print("[MULTI_PARSE] using legacy flow")
        parsed = analyze_text_with_gemini(text)
        
        if parsed == "ERROR_TIMEOUT":
            overload_msg = "❌ Xin lỗi bạn, hệ thống AI của Google hiện đang quá tải. Bạn vui lòng thử lại sau ít phút nhé!"
            if bot_token and chat_id:
                send_telegram_message(bot_token, chat_id, overload_msg)
            return

        print(f"[AI Result] {parsed}")

        # 3. Build payload — NGOÀI transaction
        firestore_data = _build_firestore_payload(parsed, firebase_uid)

        # 4. ATOMIC: counter + write trong 1 transaction duy nhất
        id_prefix = "at" if is_auto_detect else "reqtele"
        doc_id = _save_transaction_atomic(firebase_uid, firestore_data, id_prefix)

        # 4b. Gửi FCM silent notification — kích hoạt sync khi app bị kill/background
        # Không ảnh hưởng flow chính nếu FCM lỗi
        try:
            _send_fcm_notification(firebase_uid, doc_id, parsed)
        except Exception as fcm_err:
            print(f"[FCM] Non-critical error, ignoring: {fcm_err}")

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
            background_tasks.add_task(send_telegram_message, bot_token, chat_id, msg)
        elif text.lower() == "/help":
            background_tasks.add_task(_handle_help_command, bot_token, chat_id)
        else:
            # Phản hồi ngay lập tức để cải thiện UX
            waiting_msg = "⏳ Bot đã lắng nghe yêu cầu của bạn rồi ạ , vui lòng đợi 1 xíu nha..."
            send_telegram_message(bot_token, chat_id, waiting_msg)
            
            # Phân tích cơ bản để xem người dùng đang "ghi chép" hay "hỏi đáp/báo cáo"
            lower_text = text.lower()
            is_query = any(keyword in lower_text for keyword in ["?", "báo cáo", "tổng", "bao nhiêu", "thống kê", "đặt", "hạn mức", "ngân sách", "giới hạn"])
            
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
    print(f"\n[Backend API] Nhận thông báo từ {req.package_name}")
    print(f"[Backend API] Nội dung kết hợp: '{combined_text}'")
    
    # process_ai_and_save xử lý phân tích và lưu, nếu thành công sẽ gửi FCM push notification
    background_tasks.add_task(process_ai_and_save, None, req.firebase_uid, None, combined_text, True)
    
    return {"status": "processing"}


if __name__ == "__main__":
    # Render cấp biến PORT động, mặc định là 8000 nếu chạy local
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False if os.getenv("PORT") else True)
