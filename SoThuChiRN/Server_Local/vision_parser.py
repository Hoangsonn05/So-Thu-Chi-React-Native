"""
vision_parser.py — Module độc lập xử lý OCR hóa đơn từ ảnh Telegram.

Flow:
  1. Nhận file_id từ Telegram → Download ảnh resolution cao nhất
  2. Encode base64 → Gọi OpenRouter Vision API
  3. Parse JSON → Lưu Firestore (tái sử dụng _save_transaction_atomic)
  4. Gửi FCM + Reply Telegram xác nhận

KHÔNG chạm vào bất kỳ logic nào của main.py ngoài 2 hàm được import.
"""

import os
import json
import base64
import traceback
import requests
import re
import uuid
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from runtime_config import OPENROUTER_API_KEY

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"), override=True)

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
VISION_MODEL = "nvidia/nemotron-nano-12b-v2-vl:free"
TELEGRAM_API_BASE = "https://api.telegram.org/bot"

VN_TZ = timezone(timedelta(hours=7))

# Danh mục hợp lệ khớp với app — dùng để validate kết quả OCR
VALID_EXPENSE_CATEGORIES = [
    "Ăn uống", "Chi tiêu", "Quần áo", "Mỹ phẩm", "Giao lưu",
    "Y tế", "Giáo dục", "Tiền điện", "Du lịch", "Liên lạc", "Tiền nhà", "Khác",
]

# System Prompt nghiêm ngặt cho Vision model
VISION_SYSTEM_PROMPT = """You are an expert OCR and financial data extraction assistant. Analyze receipt images and extract key financial data.

RULES:
1. Respond ONLY with a valid JSON object. Do not include markdown code blocks, formatting tags, or conversational text.
2. Extract the exact Total Amount (Tổng tiền thanh toán) as an integer (VND). Ignore "Tiền khách đưa" (Cash given) or "Tiền thối" (Change).
3. Identify the merchant/store name.
4. Summarize the purchased items in Vietnamese to create a short note (max 60 characters).
5. Auto-assign a logical category in Vietnamese from: "Ăn uống", "Chi tiêu", "Quần áo", "Mỹ phẩm", "Giao lưu", "Y tế", "Giáo dục", "Tiền điện", "Du lịch", "Liên lạc", "Tiền nhà", "Khác".
6. Extract the timestamp visible on the receipt in ISO 8601 format. If not visible, use current datetime.
7. Set confidence_score between 0.0 and 1.0 indicating how confident you are in the extraction.

EXPECTED JSON FORMAT (respond with ONLY this JSON, nothing else):
{
  "amount": <integer>,
  "category": "<string>",
  "merchant": "<string>",
  "note": "<string>",
  "timestamp": "<ISO 8601 string>",
  "confidence_score": <float>
}"""


def _download_telegram_photo(bot_token: str, file_id: str) -> bytes:
    """
    Tải ảnh từ Telegram CDN:
      1. Gọi getFile để lấy file_path
      2. Download bytes từ CDN
    """
    # Bước 1: Lấy file_path
    get_file_url = f"{TELEGRAM_API_BASE}{bot_token}/getFile?file_id={file_id}"
    resp = requests.get(get_file_url, timeout=15)
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]

    # Bước 2: Download ảnh
    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    img_resp = requests.get(download_url, timeout=30)
    img_resp.raise_for_status()
    return img_resp.content


def _call_vision_api(image_bytes: bytes, caption: str = "", current_time: str = "") -> dict:
    """
    Gọi OpenRouter Vision API với ảnh base64.
    Trả về dict đã parse từ JSON response.
    """
    if not OPENROUTER_API_KEY:
        print("[Vision OCR] OPENROUTER_API_KEY=missing")
        raise RuntimeError("OPENROUTER_API_KEY missing")

    # Encode ảnh thành base64 data URI
    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    image_data_uri = f"data:image/jpeg;base64,{b64_image}"

    user_text = f"Hãy phân tích hóa đơn trong ảnh và trả về JSON theo định dạng yêu cầu. \n\nCURRENT SYSTEM TIME: {current_time}. \nUSER CAPTION: {caption}. \n\nTIME RULE: If the USER CAPTION implies a specific time or day (e.g., 'hôm nay/today', 'hôm qua/yesterday', 'sáng nay'), you MUST calculate and output the timestamp based on the CURRENT SYSTEM TIME and the caption. In this case, completely IGNORE the date printed on the receipt. ONLY use the printed receipt date if the user caption is empty or contains no time context."

    payload = {
        "model": VISION_MODEL,
        "messages": [
            {
                "role": "system",
                "content": VISION_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_uri
                        }
                    },
                    {
                        "type": "text",
                        "text": user_text
                    }
                ]
            }
        ],
        "temperature": 0.1  # Thấp nhất có thể để tăng tính xác định
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/Hoangsonn05/So-Thu-Chi-React-Native",
        "X-Title": "So Thu Chi Vision OCR"
    }

    response = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=60)
    response.raise_for_status()

    raw_text = response.json()["choices"][0]["message"]["content"].strip()
    print(f"[Vision OCR] Raw response: {raw_text[:300]}")

    # Làm sạch markdown nếu model vẫn bọc trong code fence
    import re
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE).strip()

    parsed = json.loads(cleaned)
    return parsed


def _build_firestore_payload_from_ocr(ocr_data: dict, firebase_uid: str) -> dict:
    """
    Chuyển đổi kết quả OCR thành payload chuẩn cho Firestore
    (khớp với schema của app Android).
    """
    from firebase_admin import firestore as fs

    # Parse timestamp từ OCR (nếu lỗi, fallback về ngày hiện tại)
    try:
        from datetime import datetime
        ts_str = ocr_data.get("timestamp", "")
        if ts_str:
            # Xử lý cả 2 dạng: có offset hoặc không
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        else:
            dt = datetime.now(tz=VN_TZ)
    except Exception:
        dt = datetime.now(tz=VN_TZ)

    # Normalize về UTC để lưu Firestore
    timestamp_utc = dt.astimezone(timezone.utc)

    # Ngày hiển thị theo định dạng app
    dt_vn = dt.astimezone(VN_TZ)
    date_str = dt_vn.strftime("%d/%m/%Y")
    year_month = dt_vn.strftime("%Y-%m")
    year = dt_vn.year

    # Validate & normalize category
    category = ocr_data.get("category", "Khác")
    if category not in VALID_EXPENSE_CATEGORIES:
        category = "Khác"

    amount = int(ocr_data.get("amount", 0))
    merchant = str(ocr_data.get("merchant", "")).strip()
    note = str(ocr_data.get("note", "")).strip()

    # Note ngắn gọn: "merchant - note" hoặc chỉ note
    combined_note = f"{merchant} - {note}" if merchant and note else (merchant or note or "Hóa đơn")
    if len(combined_note) > 80:
        combined_note = combined_note[:77] + "..."

    return {
        "amount": amount,
        "note": combined_note,
        "category": category,
        "type": 0,  # OCR hóa đơn luôn là chi tiêu (expense)
        "date": date_str,
        "timestamp": timestamp_utc,
        "yearMonth": year_month,
        "year": year,
        "lastUpdated": fs.SERVER_TIMESTAMP,
        "createdBy": str(firebase_uid),
        "deviceName": "Telegram Bot (OCR)",
        "deviceId": "telegram_bot_ocr",
        "source": merchant if merchant else "Hóa đơn",
        "isDeleted": False,
        "is_synced": 1,
        "syncStatus": 1
    }


def _normalize_duplicate_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _serialize_pending_payload(payload: dict) -> dict:
    serializable = {}
    for key, value in payload.items():
        if key == "lastUpdated":
            continue
        if isinstance(value, datetime):
            serializable[key] = value.isoformat()
        else:
            serializable[key] = value
    return serializable


def _has_duplicate_ocr_transaction(firebase_uid: str, payload: dict, ocr_data: dict) -> bool:
    db = firestore.client()
    ts = payload.get("timestamp")
    if not isinstance(ts, datetime):
        return False

    source_key = _normalize_duplicate_text(ocr_data.get("merchant") or payload.get("source"))
    if not source_key:
        return False

    start = ts - timedelta(hours=24)
    end = ts + timedelta(hours=24)
    amount = int(payload.get("amount", 0) or 0)

    query = (
        db.collection("users")
        .document(firebase_uid)
        .collection("transactions")
        .where(filter=FieldFilter("timestamp", ">=", start))
        .where(filter=FieldFilter("timestamp", "<=", end))
    )

    for doc in query.stream():
        data = doc.to_dict() or {}
        if data.get("isDeleted") is True or data.get("type") != 0:
            continue
        try:
            existing_amount = int(data.get("amount", 0) or 0)
        except (TypeError, ValueError):
            existing_amount = 0
        if existing_amount != amount:
            continue

        existing_source = _normalize_duplicate_text(data.get("merchant") or data.get("source"))
        if existing_source and (
            existing_source == source_key
            or existing_source in source_key
            or source_key in existing_source
        ):
            return True

    return False


def _build_pending_ocr_keyboard(action_id: str, save_text: str) -> dict:
    return {
        "inline_keyboard": [
            [{"text": save_text, "callback_data": f"save_pending_ocr:{action_id}"}],
            [{"text": "Bỏ qua", "callback_data": f"cancel_pending_ocr:{action_id}"}],
        ]
    }


def _format_pending_ocr_time(payload: dict) -> str:
    ts = payload.get("timestamp")
    if isinstance(ts, datetime):
        return ts.astimezone(VN_TZ).strftime("%d/%m/%Y %H:%M")
    return str(ts or "N/A")


def _create_pending_ocr_action(firebase_uid: str, reason: str, payload: dict, ocr_data: dict) -> str:
    db = firestore.client()
    action_id = uuid.uuid4().hex
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    db.collection("users").document(firebase_uid).collection("pending_actions").document(action_id).set({
        "action_type": "ocr_confirm",
        "reason": reason,
        "payload": _serialize_pending_payload(payload),
        "ocr_data": ocr_data,
        "created_at": firestore.SERVER_TIMESTAMP,
        "expires_at": expires_at,
        "status": "pending",
    })
    return action_id


def _send_pending_ocr_confirmation(bot_token: str, chat_id: int, reason: str, action_id: str, payload: dict, ocr_data: dict, send_telegram_message):
    if reason == "duplicate":
        msg = "Hóa đơn này có vẻ đã tồn tại. Bạn vẫn muốn lưu lại không?"
        keyboard = _build_pending_ocr_keyboard(action_id, "Vẫn lưu")
    else:
        confidence = float(ocr_data.get("confidence_score", 0) or 0)
        msg = (
            "Bot chưa chắc về thông tin hóa đơn này. Bạn xác nhận lưu không?\n\n"
            f"Số tiền: {int(payload.get('amount', 0) or 0):,}đ\n"
            f"Danh mục: {payload.get('category', 'Khác')}\n"
            f"Nơi mua: {payload.get('source', '')}\n"
            f"Ghi chú: {payload.get('note', '')}\n"
            f"Thời gian: {_format_pending_ocr_time(payload)}\n"
            f"Độ chính xác OCR: {int(confidence * 100)}%"
        )
        keyboard = _build_pending_ocr_keyboard(action_id, "Lưu")
    send_telegram_message(bot_token, chat_id, msg, reply_markup=keyboard)


def parse_receipt_image(bot_token: str, file_id: str, firebase_uid: str, chat_id: int, caption: str = "", current_time: str = ""):
    """
    Hàm chính — được gọi bởi BackgroundTasks trong main.py.

    Pipeline:
      download → base64 → Vision API → parse JSON → Firestore → Telegram reply
    """
    # Import hàm tái sử dụng từ main (tránh circular import: chỉ import khi cần)
    from main import _save_transaction_atomic, _send_fcm_notification, send_telegram_message

    print(f"[Vision OCR] Bắt đầu xử lý ảnh file_id={file_id} cho uid={firebase_uid}")

    try:
        # Bước 1: Download ảnh chất lượng cao nhất
        print("[Vision OCR] Đang tải ảnh từ Telegram...")
        image_bytes = _download_telegram_photo(bot_token, file_id)
        print(f"[Vision OCR] Đã tải ảnh: {len(image_bytes):,} bytes")

        # Bước 2: Gọi Vision API
        print(f"[Vision OCR] Đang gửi ảnh đến Vision model với caption='{caption}'...")
        ocr_data = _call_vision_api(image_bytes, caption, current_time)
        print(f"[Vision OCR] Kết quả OCR: {ocr_data}")

        # Validate amount
        amount = int(ocr_data.get("amount", 0))
        if amount <= 0:
            raise ValueError(f"Số tiền không hợp lệ từ OCR: {amount}")

        # Bước 3: Build payload & lưu Firestore
        firestore_payload = _build_firestore_payload_from_ocr(ocr_data, firebase_uid)
        confidence = float(ocr_data.get("confidence_score", 0) or 0)
        reason = None
        if _has_duplicate_ocr_transaction(firebase_uid, firestore_payload, ocr_data):
            reason = "duplicate"
        elif confidence < 0.75:
            reason = "low_confidence"

        if reason:
            action_id = _create_pending_ocr_action(firebase_uid, reason, firestore_payload, ocr_data)
            _send_pending_ocr_confirmation(
                bot_token,
                chat_id,
                reason,
                action_id,
                firestore_payload,
                ocr_data,
                send_telegram_message,
            )
            print(f"[Vision OCR] Pending action created: {action_id}, reason={reason}")
            return

        doc_id = _save_transaction_atomic(firebase_uid, firestore_payload, "ocr")
        print(f"[Vision OCR] Đã lưu Firestore: {doc_id}")

        # Bước 4: Gửi FCM push notification (kích hoạt sync app)
        try:
            _send_fcm_notification(firebase_uid, doc_id, {
                "amount": amount,
                "category": firestore_payload["category"],
                "note": firestore_payload["note"],
                "date": firestore_payload["date"],
                "source": firestore_payload["source"],
            })
        except Exception as fcm_err:
            print(f"[Vision OCR] FCM error (non-critical): {fcm_err}")

        # Bước 5: Reply Telegram xác nhận
        category = firestore_payload["category"]
        merchant = ocr_data.get("merchant", "")
        note = ocr_data.get("note", "")

        # Hiển thị độ tin cậy để người dùng biết
        confidence_icon = "🟢" if confidence >= 0.85 else ("🟡" if confidence >= 0.6 else "🔴")

        merchant_line = f"🏪 Nơi mua: {merchant}\n" if merchant else ""
        note_line = f"📝 Ghi chú: {note}\n" if note else ""

        # Định dạng thời gian hiển thị: DD/MM/YYYY HH:MM
        display_time = "N/A"
        if "timestamp" in firestore_payload:
            ts = firestore_payload["timestamp"]
            # Chuyển từ datetime object sang string VN
            dt_vn = ts.astimezone(VN_TZ)
            display_time = dt_vn.strftime("%d/%m/%Y %H:%M")

        reply_msg = (
            f"✅ *Đã ghi nhận hóa đơn thành công!*\n\n"
            f"💰 Số tiền: *{amount:,}đ*\n"
            f"🏷️ Danh mục: {category}\n"
            f"{merchant_line}"
            f"{note_line}"
            f"🕒 Thời gian: {display_time}\n"
            f"{confidence_icon} Độ chính xác OCR: {int(confidence * 100)}%"
        )

        send_telegram_message(bot_token, chat_id, reply_msg)

    except requests.exceptions.RequestException as net_err:
        print(f"[Vision OCR] Lỗi mạng: {net_err}")
        traceback.print_exc()
        send_telegram_message(
            bot_token, chat_id,
            "❌ Không thể tải ảnh do lỗi kết nối. Vui lòng thử lại sau."
        )

    except json.JSONDecodeError as json_err:
        print(f"[Vision OCR] Lỗi parse JSON từ Vision model: {json_err}")
        traceback.print_exc()
        send_telegram_message(
            bot_token, chat_id,
            "⚠️ Bot không thể đọc được thông tin hóa đơn. "
            "Hóa đơn có thể bị mờ hoặc góc chụp chưa đủ rõ. "
            "Bạn hãy chụp lại với ánh sáng tốt hơn nhé!"
        )

    except ValueError as val_err:
        print(f"[Vision OCR] Dữ liệu không hợp lệ: {val_err}")
        traceback.print_exc()
        send_telegram_message(
            bot_token, chat_id,
            f"⚠️ Không thể xác định số tiền từ hóa đơn. "
            "Bạn có thể nhập thủ công: ví dụ 'Ăn cơm 50k'."
        )

    except Exception as e:
        print(f"[Vision OCR] Lỗi không xác định: {e}")
        traceback.print_exc()
        send_telegram_message(
            bot_token, chat_id,
            "❌ Đã có lỗi xảy ra khi xử lý hóa đơn. Vui lòng thử lại hoặc nhập thủ công."
        )
