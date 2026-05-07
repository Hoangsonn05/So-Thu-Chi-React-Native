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
from firebase_admin import credentials, firestore
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

# --- CẤU HÌNH AI (GEMINI - KHỚP VỚI APP) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AIzaSyBk2tRqMVasNvZP13P9O5eymUiD-rSc31A")
GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent"

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

# --- SYSTEM PROMPT CHO GEMINI (ENGLISH — enforces exact app schema) ---
GEMINI_SYSTEM_PROMPT = """You are a strict financial data extraction engine for a Vietnamese personal finance app called "Sổ Thu Chi".
Your ONLY job is to parse the user's Vietnamese text message and extract financial transaction details into a JSON object.

## RULES — FOLLOW EXACTLY:
1. Output ONLY a single raw JSON object. No markdown, no code fences, no explanation, no extra text.
2. The JSON must have EXACTLY these fields:
   - "type": integer. 0 for expense (chi), 1 for income (thu). Default to 0 if ambiguous.
   - "amount": integer. The monetary amount in VND. Parse Vietnamese shorthand: "k" or "K" = multiply by 1,000; "tr" or "triệu" = multiply by 1,000,000; "tỷ" = multiply by 1,000,000,000. The amount must always be a positive integer.
   - "category": string. Must be EXACTLY one of the allowed categories listed below. Choose the most appropriate one based on context.
   - "note": string. A concise Vietnamese description of the transaction, summarizing what the user said. Maximum 50 characters.
   - "date": string. Format "dd/MM/yyyy". If the user specifies a date, use it. If they say "hôm nay" or "nay", use today's date. If they say "hôm qua", use yesterday. If no date is mentioned, use today's date. Today's date is: {current_date}.

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
app = FastAPI(title="Firestore Export & Telegram Bot API")


class ExportEmailRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    userEmail: str = Field(..., min_length=1)


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

def send_telegram_message(bot_token: str, chat_id: int, text: str):
    """Hàm hỗ trợ gửi tin nhắn lại cho người dùng qua Telegram.
    Sử dụng token động của từng user."""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code != 200:
            print(f"[Telegram Send Error] Status {resp.status_code}: {resp.text}")
        else:
            print(f"[Telegram] Message sent to {chat_id} via custom bot")
    except Exception as e:
        print(f"[Telegram] Lỗi gửi tin nhắn: {e}")
        traceback.print_exc()


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
    Gọi trực tiếp Google Gemini API (giống với app).
    Sử dụng System Prompt cũ để đảm bảo hiệu suất parse tốt nhất.
    """
    now_vn = datetime.now(tz=VN_TZ)
    today_str = now_vn.strftime("%d/%m/%Y")

    # Tạo prompt từ template (chỉ dùng current_date cho prompt tiếng Anh này)
    system_prompt = GEMINI_SYSTEM_PROMPT.format(current_date=today_str)
    
    full_prompt = f"{system_prompt}\n\nUSER INPUT: \"{user_text}\"\n\nJSON OUTPUT:"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": full_prompt}
                ]
            }
        ]
    }

    try:
        response = requests.post(
            f"{GEMINI_API_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
    except requests.exceptions.ReadTimeout:
        print("[Gemini Timeout] AI không phản hồi kịp trong 60s")
        return "ERROR_TIMEOUT"
    except Exception as e:
        print(f"[Gemini Request Error] {e}")
        raise e
    
    if response.status_code != 200:
        print(f"\n====== GEMINI API ERROR ({response.status_code}) ======")
        print(f"Details: {response.text}")
        print("========================================================\n")
        raise Exception(f"Gemini API rejected the request. Error: {response.text}")

    result = response.json()
    
    try:
        raw_text = result['candidates'][0]['content']['parts'][0]['text'].strip()
    except (KeyError, IndexError) as e:
        print(f"[Gemini Response Error] Could not extract text: {e}")
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


def _save_transaction_atomic(firebase_uid: str, firestore_data: dict) -> str:
    """
    Lưu transaction + tăng counter trong 1 Firestore Transaction duy nhất.
    Trả về document ID (reqtele_N).
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
        .document(f"reqtele_{predicted_next}")
    )

    transaction = db.transaction()
    actual_number = _atomic_counter_and_write(transaction, counter_ref, tx_doc_ref, firestore_data)

    doc_id = f"reqtele_{actual_number}"
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


def process_ai_and_save(bot_token: str, firebase_uid: str, chat_id: int, text: str):
    """
    Background Task — KHÔNG có network call nào trong Firestore Transaction.
    Flow: AI parse (network) → Atomic Firestore write → Telegram reply (network).
    """
    try:
        print(f"[Process] chat_id={chat_id}, uid={firebase_uid}, text='{text[:50]}'")

        # 2. Gọi AI — NGOÀI transaction
        parsed = analyze_text_with_gemini(text)
        
        if parsed == "ERROR_TIMEOUT":
            overload_msg = "❌ Xin lỗi bạn, hệ thống AI của Google hiện đang quá tải. Bạn vui lòng thử lại sau ít phút nhé!"
            send_telegram_message(bot_token, chat_id, overload_msg)
            return

        print(f"[AI Result] {parsed}")

        # 3. Build payload — NGOÀI transaction
        firestore_data = _build_firestore_payload(parsed, firebase_uid)

        # 4. ATOMIC: counter + write trong 1 transaction duy nhất
        doc_id = _save_transaction_atomic(firebase_uid, firestore_data)

        # 5. Telegram reply — NGOÀI transaction
        type_label = "Thu nhập" if parsed["type"] == 1 else "Chi tiêu"
        amt = f"{parsed['amount']:,}đ"
        cat_emoji = CATEGORY_EMOJIS.get(parsed["category"], "")
        msg = (
            f"✅Đã ghi nhận thành công!\n\n"
            f"Loại: {type_label}\n"
            f"Số tiền: {amt}\n"
            f"{cat_emoji} Danh mục: {parsed['category']}\n"
            f"Ghi chú: {parsed['note']}\n"
            f"Ngày: {parsed['date']}\n"
            f"ID: {doc_id}"
        )
        send_telegram_message(bot_token, chat_id, msg)

    except json.JSONDecodeError as e:
        print(f"[AI Parse Error] {e}")
        traceback.print_exc()
        send_telegram_message(bot_token, chat_id, "Khong the hieu noi dung. Vi du: An trua 50k")
    except requests.exceptions.RequestException as e:
        print(f"[AI API Error] {e}")
        traceback.print_exc()
        send_telegram_message(bot_token, chat_id, "Loi ket noi AI. Vui long thu lai sau.")
    except Exception as e:
        print(f"[Error] process_ai_and_save: {e}")
        traceback.print_exc()
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

    if "message" in data and "text" in data.get("message", {}):
        chat_id = data["message"]["chat"]["id"]
        text = data["message"]["text"].strip()

        # Dùng bot_token để tìm chủ nhân
        firebase_uid = _get_uid_from_bot_token(bot_token)
        if not firebase_uid:
            send_telegram_message(bot_token, chat_id, "⚠️ Bot chua duoc lien ket tren app So Thu Chi.")
            return {"status": "ok"}

        if text.lower() == "/start":
            msg = "✅ Bot da ket noi voi So Thu Chi!\nBan co the nhan tin nhu: 'An sang 30k'"
            background_tasks.add_task(send_telegram_message, bot_token, chat_id, msg)
        elif text.lower() == "/help":
            background_tasks.add_task(_handle_help_command, bot_token, chat_id)
        else:
            # Phản hồi ngay lập tức để cải thiện UX
            waiting_msg = "⏳ Bot đã lắng nghe yêu cầu của bạn rồi ạ , vui lòng đợi 1 xíu nha..."
            send_telegram_message(bot_token, chat_id, waiting_msg)
            
            background_tasks.add_task(process_ai_and_save, bot_token, firebase_uid, chat_id, text)

    return {"status": "ok"}


if __name__ == "__main__":
    # Render cấp biến PORT động, mặc định là 8000 nếu chạy local
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False if os.getenv("PORT") else True)