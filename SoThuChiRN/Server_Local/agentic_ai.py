import os
import json
import requests
import traceback
import calendar
import hashlib
import re
import unicodedata
from datetime import datetime, timezone, timedelta
from typing import Optional
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
from google.api_core.exceptions import FailedPrecondition
from google.cloud.firestore_v1.base_query import FieldFilter

from firebase_admin import firestore, messaging

# Dùng chung config
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "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")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL_NAME = "nvidia/nemotron-3-super-120b-a12b:free"
DEFAULT_TIMEZONE = "Asia/Bangkok"
DEFAULT_EXTERNAL_SEND_TIME = "07:00"
DEFAULT_FINANCE_SEND_TIME = "20:00"
EXTERNAL_BRIEF_TASK_TYPES = {
    "morning_external_brief",
    "gold_price_brief",
    "fuel_price_brief",
    "ai_price_brief",
}
EXTERNAL_BRIEF_TITLES = {
    "morning_external_brief": "Bao cao thi truong sang",
    "gold_price_brief": "Bao cao gia vang",
    "fuel_price_brief": "Bao cao gia xang dau",
    "ai_price_brief": "Bao cao gia AI",
}
EXTERNAL_BRIEF_FALLBACK_MESSAGE = "Tính năng đang có khung xử lý, nguồn dữ liệu chưa cấu hình."
FINANCE_REPORT_TASK_TYPES = {
    "expense_report",
    "daily_finance_report",
    "weekly_finance_report",
    "monthly_finance_report",
}
DEFAULT_DAILY_FINANCE_TASK_TYPE = "daily_finance_report"
TASK_ACTIVE_STATUSES = {"active", "pending"}
TASK_TERMINAL_STATUSES = {"completed", "failed", "disabled"}
SUPPORTED_SCHEDULED_TASK_TYPES = (
    FINANCE_REPORT_TASK_TYPES | EXTERNAL_BRIEF_TASK_TYPES
)
SCHEDULER_LOCK_MINUTES = 5
SCHEDULER_MAX_RETRIES = 3


def _get_tz(timezone_name: str = DEFAULT_TIMEZONE):
    if ZoneInfo:
        try:
            return ZoneInfo(timezone_name or DEFAULT_TIMEZONE)
        except Exception:
            pass
    return timezone(timedelta(hours=7))


VN_TZ = _get_tz(DEFAULT_TIMEZONE)

# Prompt cho công việc tổng hợp/truy vấn của Agent
AGENTIC_SYSTEM_PROMPT = """Bạn là "Giám đốc tài chính" AI chủ động của ứng dụng cá nhân Sổ Thu Chi.
Nhiệm vụ của bạn là giải đáp các thắc mắc về tình hình tài chính của người dùng dựa trên dữ liệu thật, cũng như lên lịch báo cáo và thiết lập cảnh báo ngân sách theo yêu cầu.

BẮT BUỘC TUÂN THỦ PHÂN BIỆT Ý ĐỊNH:
1. Nếu người dùng nói về một việc ĐÃ XẢY RA (Ví dụ: "Đã tiêu", "Vừa mua", "Hết 50k", "Ăn sáng 30k") -> Đây là ghi chép giao dịch. Vì bạn là Agent truy vấn/báo cáo, nếu thấy ý định này, hãy lịch sự nhắc người dùng rằng bạn chỉ hỗ trợ báo cáo và thiết lập ngân sách.
2. Nếu người dùng nói về một MỤC TIÊU/GIỚI HẠN trong tương lai (Ví dụ: "Đặt hạn mức", "Ngân sách tháng này là", "Giới hạn chi tiêu", "Cài đặt ngân sách") -> BẮT BUỘC gọi công cụ `set_budget_alert`.

VÍ DỤ (Few-Shot):
- User: "Hôm nay đi ăn sáng hết 50k" -> Intent: Ghi chép chi tiêu (AI sẽ không gọi tool ngân sách, chỉ trả lời nhắc nhở).
- User: "Đặt hạn mức ăn uống 5 triệu, báo tôi khi tiêu hết 80%" -> Intent: Gọi tool `set_budget_alert` (category='Ăn uống', budget_amount=5000000, threshold_pct=80).
- User: "Ngân sách tháng này là 10 triệu" -> Intent: Gọi tool `set_budget_alert` (category='Tất cả', budget_amount=10000000, threshold_pct=80).
- User: "Tôi muốn giới hạn chi tiêu 1 triệu cho mua sắm" -> Intent: Gọi tool `set_budget_alert` (category='Mua sắm', budget_amount=1000000, threshold_pct=80).

DƯỚI ĐÂY LÀ CÁC CÔNG CỤ CỦA BẠN:

Bạn BẮT BUỘC phải dùng công cụ `query_database` khi người dùng hỏi về:
- Tổng chi tiêu, thu nhập (ví dụ: "Tháng này tiêu bao nhiêu?", "Báo cáo tuần qua", "Hôm nay tôi tiêu gì?").
- Số tiền chi cho một danh mục cụ thể (ví dụ: "Tiêu bao nhiêu tiền ăn uống rồi?", "Tiền điện tháng này").

Bạn BẮT BUỘC phải dùng công cụ `schedule_report` khi người dùng yêu cầu đặt lịch báo cáo trong tương lai:
- Ví dụ: "Lên lịch báo cáo lúc 16:20 hôm nay", "Nhắc tôi xem báo cáo vào 8h sáng mai".
- Định dạng thời gian cho công cụ này là chuẩn ISO 8601 (ví dụ: 2026-05-08T16:20:00). Bạn tự tính toán datetime phù hợp theo múi giờ Việt Nam (UTC+7).

Bạn BẮT BUỘC phải dùng công cụ `set_budget_alert` khi người dùng muốn thiết lập hạn mức/ngân sách chi tiêu:
- Ví dụ: "Đặt ngân sách ăn uống tháng này là 5 triệu", "Cảnh báo tôi khi tiêu quá 80% ngân sách tổng".
- Nếu người dùng không nói rõ danh mục, mặc định là 'Tất cả'. Nếu không nói rõ phần trăm cảnh báo, mặc định là 80%.

QUY TẮC:
1. KHÔNG tự bịa ra con số. Luôn gọi `query_database`.
2. Khi nhận được kết quả từ công cụ, hãy tổng hợp lại thành một đoạn văn ngắn gọn, chuyên nghiệp, lịch sự bằng tiếng Việt để báo cáo cho người dùng.
3. Nếu gọi `schedule_report` hoặc `set_budget_alert`, hãy xác nhận với người dùng rằng thông tin đã được lưu thành công.
"""

AGENTIC_SYSTEM_PROMPT += """

ADDITIONAL FINANCIAL QUERY TOOLS:
- Use `top_transactions` for largest transactions / top spending / top income.
- Use `merchant_spending` for spending at a merchant, store, brand, wallet, or payee, for example Highlands, Shopee, Grab.
- Use `compare_periods` for comparison questions such as "so voi thang truoc", "so voi tuan truoc".
- Use `category_trend` for questions about which category increased/decreased strongly.

Supported timeframes: today, current_week, last_week, current_month, last_month, all_time.
All totals, aggregates, rankings, comparisons, and percentages MUST be computed by Python tools from Firestore data before you answer.
You may only explain the returned tool result. Do not calculate or invent financial numbers yourself.
Only describe computed values returned by tools. Do not infer causes or trends not explicitly present in tool output.

TELEGRAM RESPONSE STYLE:
- Keep replies mobile-friendly: short paragraphs and compact lines.
- Use light emoji only when helpful, for example 📊, 💸, 🏪, 🔝.
- Format VND amounts with dot separators, for example 57.948.200đ.
- Do not use raw markdown bullets like "- **...".
- If evidence is missing, say the data is not available instead of guessing.
"""


def execute_set_budget_alert(firebase_uid: str, category: str, budget_amount: float, threshold_pct: float) -> str:
    """ Lưu cấu hình ngân sách vào Firestore. """
    db = firestore.client()
    try:
        # Normalize category name
        cat_key = category if category else "Tất cả"
        
        budget_data = {
            "category": cat_key,
            "budget_amount": float(budget_amount),
            "alert_threshold_percentage": float(threshold_pct),
            "updated_at": firestore.SERVER_TIMESTAMP
        }
        
        # Lưu vào collection chuyên biệt cho ngân sách
        db.collection("user_budgets").document(firebase_uid).collection("budgets").document(cat_key).set(budget_data, merge=True)
        
        return json.dumps({
            "status": "success", 
            "message": f"Đã thiết lập ngân sách cho '{cat_key}' là {budget_amount:,.0f}đ. Tôi sẽ cảnh báo khi bạn tiêu quá {threshold_pct}%."
        }, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"status": "error", "error": str(e)})


def get_vn_now() -> datetime:
    return datetime.now(tz=VN_TZ)


def get_date_key(dt: datetime, timezone_name: str = DEFAULT_TIMEZONE) -> str:
    tz = _get_tz(timezone_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz).strftime("%Y-%m-%d")


def _parse_hhmm(value: str, fallback: str = DEFAULT_FINANCE_SEND_TIME) -> tuple[int, int]:
    text = (value or fallback).strip()
    match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    if not match:
        text = fallback
        match = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    return int(match.group(1)), int(match.group(2))


def _coerce_datetime(value) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=VN_TZ)
        except ValueError:
            return None
    return None


def _task_type_from_legacy(task: dict) -> str:
    report_type = (task.get("task_type") or task.get("report_type") or "daily_finance_report").strip()
    aliases = {
        "summary": "daily_finance_report",
        "daily_summary": "daily_finance_report",
        "weekly_summary": "weekly_finance_report",
        "monthly_summary": "monthly_finance_report",
        "finance_report": "daily_finance_report",
    }
    return aliases.get(report_type, report_type)


def _timeframe_for_task_type(task_type: str) -> str:
    if task_type == "weekly_finance_report":
        return "current_week"
    if task_type == "monthly_finance_report":
        return "current_month"
    return "today"


def calculate_next_run_at(task: dict, from_dt: datetime) -> Optional[datetime]:
    timezone_name = task.get("timezone") or DEFAULT_TIMEZONE
    tz = _get_tz(timezone_name)
    local_from = from_dt.astimezone(tz) if from_dt.tzinfo else from_dt.replace(tzinfo=tz)
    schedule_type = (task.get("schedule_type") or "").strip().lower()

    legacy_target = _coerce_datetime(task.get("target_datetime"))
    if not schedule_type and legacy_target:
        return legacy_target.astimezone(timezone.utc)

    if schedule_type == "once":
        target = _coerce_datetime(task.get("next_run_at")) or legacy_target
        return target.astimezone(timezone.utc) if target else None

    hour, minute = _parse_hhmm(task.get("time"), DEFAULT_FINANCE_SEND_TIME)
    candidate = local_from.replace(hour=hour, minute=minute, second=0, microsecond=0)

    if schedule_type in {"daily", "default_daily", ""}:
        if candidate <= local_from:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc)

    if schedule_type == "weekly":
        payload = task.get("payload") or {}
        weekday = int(payload.get("weekday", local_from.weekday()))
        days_ahead = (weekday - local_from.weekday()) % 7
        candidate = candidate + timedelta(days=days_ahead)
        if candidate <= local_from:
            candidate += timedelta(days=7)
        return candidate.astimezone(timezone.utc)

    if schedule_type == "monthly":
        payload = task.get("payload") or {}
        target_day = int(payload.get("day", local_from.day))

        def monthly_candidate(year: int, month: int) -> datetime:
            last_day = calendar.monthrange(year, month)[1]
            day = min(max(1, target_day), last_day)
            return datetime(year, month, day, hour, minute, tzinfo=tz)

        candidate = monthly_candidate(local_from.year, local_from.month)
        if candidate <= local_from:
            year = local_from.year + (1 if local_from.month == 12 else 0)
            month = 1 if local_from.month == 12 else local_from.month + 1
            candidate = monthly_candidate(year, month)
        return candidate.astimezone(timezone.utc)

    return None


def _delivery_state_ref(db, uid: str, task_type: str, date_key: str):
    state_key = f"{task_type}_{date_key}"
    return db.collection("users").document(uid).collection("delivery_state").document(state_key)


def get_delivery_state(uid: str, task_type: str, date_key: str) -> dict:
    db = firestore.client()
    snap = _delivery_state_ref(db, uid, task_type, date_key).get()
    return snap.to_dict() if snap.exists else {}


def update_delivery_state(uid: str, task_type: str, date_key: str, **updates) -> None:
    db = firestore.client()
    ref = _delivery_state_ref(db, uid, task_type, date_key)
    existing = ref.get()
    payload = {
        "uid": uid,
        "task_type": task_type,
        "date_key": date_key,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if not existing.exists:
        payload.update({
            "scheduled_time": updates.get("scheduled_time"),
            "auto_send_done": False,
            "manual_send_done": False,
            "skip_auto_today": False,
            "last_manual_at": None,
            "last_auto_at": None,
            "last_report_id": None,
        })
    payload.update(updates)
    ref.set(payload, merge=True)


def should_skip_auto_delivery(uid: str, task_type: str, scheduled_time: str, now: datetime) -> bool:
    date_key = get_date_key(now, DEFAULT_TIMEZONE)
    state = get_delivery_state(uid, task_type, date_key)
    if state.get("auto_send_done"):
        print(f"[DeliveryState] skip auto: already sent uid={uid} task={task_type} date={date_key}")
        return True
    if state.get("skip_auto_today"):
        print(f"[DeliveryState] skip auto: manual before schedule uid={uid} task={task_type} date={date_key}")
        return True
    if task_type in EXTERNAL_BRIEF_TASK_TYPES and state.get("manual_send_done"):
        tz = _get_tz(DEFAULT_TIMEZONE)
        local_now = now.astimezone(tz) if now.tzinfo else now.replace(tzinfo=tz)
        hour, minute = _parse_hhmm(scheduled_time, DEFAULT_EXTERNAL_SEND_TIME)
        scheduled_at = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if local_now >= scheduled_at:
            print(f"[DeliveryState] skip auto: manual after schedule uid={uid} task={task_type} date={date_key}")
            return True
    return False


def mark_manual_report_delivery(uid: str, task_type: str, scheduled_time: str, skip_auto_today: bool = False) -> None:
    now = get_vn_now()
    date_key = get_date_key(now, DEFAULT_TIMEZONE)
    update_delivery_state(
        uid,
        task_type,
        date_key,
        scheduled_time=scheduled_time,
        manual_send_done=True,
        skip_auto_today=skip_auto_today,
        last_manual_at=firestore.SERVER_TIMESTAMP,
        last_report_id=None,
    )

def execute_schedule_report(firebase_uid: str, target_datetime_iso: str, report_type: str) -> str:
    """ Lưu lịch báo cáo vào Firestore collection 'scheduled_tasks'. """
    db = firestore.client()
    try:
        print(f"[Execute Tool] schedule_report: target={target_datetime_iso}, type={report_type}")
        # Nhận ISO string, chuyển thành datetime object chuẩn (đã có múi giờ hoặc gán UTC+7)
        # Python 3.7+ hỗ trợ fromisoformat với múi giờ (+07:00)
        dt_str = target_datetime_iso.replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=VN_TZ)
        
        # Đảm bảo lưu đúng định dạng để sau này query dễ dàng
        target_utc = dt.astimezone(timezone.utc)
        task_type = _task_type_from_legacy({"report_type": report_type})
        local_dt = dt.astimezone(VN_TZ)
        if task_type == "weekly_finance_report":
            schedule_type = "weekly"
        elif task_type == "monthly_finance_report":
            schedule_type = "monthly"
        elif task_type in {"daily_finance_report", "expense_report"} and report_type != "summary":
            schedule_type = "daily"
        else:
            schedule_type = "once"
        
        task_data = {
            "uid": firebase_uid,
            "task_type": task_type,
            "schedule_type": schedule_type,
            "timezone": DEFAULT_TIMEZONE,
            "time": local_dt.strftime("%H:%M"),
            "next_run_at": target_utc,
            "last_run_at": None,
            "last_success_at": None,
            "retry_count": 0,
            "payload": {
                "report_type": report_type,
                "source": "agentic_schedule_report",
                "skip_default_if_manual_before_scheduled": False,
                "weekday": local_dt.weekday(),
                "day": local_dt.day,
            },
            "target_datetime": target_utc,
            "report_type": report_type,
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }
        
        db.collection("scheduled_tasks").add(task_data)
        return json.dumps({"status": "success", "message": f"Đã lên lịch thành công cho thời gian {dt.strftime('%d/%m/%Y %H:%M')}"}, ensure_ascii=False)
        
    except Exception as e:
        print(f"[Tool Error] execute_schedule_report: {e}")
        traceback.print_exc()
        return json.dumps({"status": "error", "error": str(e)})

def execute_query_database(firebase_uid: str, category: str, timeframe: str) -> str:
    """
    Truy vấn dữ liệu Firestore dựa trên yêu cầu từ AI.
    """
    db = firestore.client()
    try:
        start_date, end_date = _get_period_bounds(timeframe)

        start_utc = start_date.astimezone(timezone.utc)
        end_utc = end_date.astimezone(timezone.utc)

        query = db.collection("users").document(firebase_uid).collection("transactions")
        query = query.where(filter=FieldFilter("timestamp", ">=", start_utc)).where(filter=FieldFilter("timestamp", "<=", end_utc))
        
        docs = query.stream()
        
        total_expense = 0
        total_income = 0
        details = {}
        
        for doc in docs:
            data = doc.to_dict()
            if data.get("isDeleted", False):
                continue
                
            amount = data.get("amount", 0)
            t_type = data.get("type", 0) # 0: chi, 1: thu
            t_cat = data.get("category", "Khác")
            
            if t_type == 0:
                total_expense += amount
                details[t_cat] = details.get(t_cat, 0) + amount
            else:
                total_income += amount
        
        cat_lower = category.lower()
        if cat_lower in ["tất cả", "all", "tổng", "tổng cộng"]:
            result = {
                "Thời gian": f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}",
                "Tổng chi": total_expense,
                "Tổng thu": total_income,
                "Chi tiết chi tiêu": details
            }
        elif cat_lower in ["chi tiêu", "expense"]:
            result = {
                "Thời gian": f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}",
                "Tổng chi": total_expense,
                "Chi tiết": details
            }
        elif cat_lower in ["thu nhập", "income"]:
            result = {
                "Thời gian": f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}",
                "Tổng thu": total_income
            }
        else:
            # Lấy category cụ thể
            matched_expense = 0
            # Normalize for matching
            for k, v in details.items():
                if k.lower() == cat_lower:
                    matched_expense = v
                    break
            
            result = {
                "Thời gian": f"Từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}",
                f"Danh mục yêu cầu ({category})": matched_expense
            }
            
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def _get_period_bounds(timeframe: str) -> tuple[datetime, datetime]:
    now = datetime.now(tz=VN_TZ)
    key = (timeframe or "current_month").strip().lower()

    if key == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif key == "current_week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
    elif key == "last_week":
        this_week_start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(microseconds=1)
    elif key == "last_month":
        first_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_prev = first_current - timedelta(microseconds=1)
        start = last_prev.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = last_prev
    elif key == "all_time":
        start = now.replace(year=2000, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now
    else:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        end = now

    return start, end


def _format_period(start: datetime, end: datetime) -> str:
    return f"{start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}"


def _fetch_transactions_for_period(firebase_uid: str, timeframe: str) -> tuple[list[dict], datetime, datetime]:
    db = firestore.client()
    start_vn, end_vn = _get_period_bounds(timeframe)
    start_utc = start_vn.astimezone(timezone.utc)
    end_utc = end_vn.astimezone(timezone.utc)

    query = db.collection("users").document(firebase_uid).collection("transactions")
    query = query.where(filter=FieldFilter("timestamp", ">=", start_utc)).where(filter=FieldFilter("timestamp", "<=", end_utc))

    transactions = []
    for doc in query.stream():
        data = doc.to_dict() or {}
        if data.get("isDeleted", False):
            continue

        try:
            amount = float(data.get("amount", 0) or 0)
        except (TypeError, ValueError):
            amount = 0

        transactions.append({
            "id": doc.id,
            "amount": amount,
            "type": 1 if data.get("type") == 1 else 0,
            "category": str(data.get("category", "Khac")),
            "note": str(data.get("note", "")),
            "source": str(data.get("source", "")),
            "date": str(data.get("date", "")),
        })

    return transactions, start_vn, end_vn


def _category_matches(actual: str, requested: str) -> bool:
    requested = (requested or "").strip().lower()
    if requested in {"", "all", "tat ca", "tong", "tong cong", "tất cả"}:
        return True
    return (actual or "").strip().lower() == requested


def _sum_metric(transactions: list[dict], metric: str, category: str = "all") -> float:
    metric_key = (metric or "expense").strip().lower()
    total_income = 0.0
    total_expense = 0.0
    for tx in transactions:
        if not _category_matches(tx.get("category", ""), category):
            continue
        if tx.get("type") == 1:
            total_income += tx.get("amount", 0)
        else:
            total_expense += tx.get("amount", 0)

    if metric_key in {"income", "thu", "thu_nhap"}:
        return total_income
    if metric_key in {"net", "balance", "chenh_lech"}:
        return total_income - total_expense
    return total_expense


def execute_compare_periods(firebase_uid: str, metric: str, current_period: str, compare_period: str, category: str = "all") -> str:
    try:
        current_txs, current_start, current_end = _fetch_transactions_for_period(firebase_uid, current_period)
        previous_txs, previous_start, previous_end = _fetch_transactions_for_period(firebase_uid, compare_period)

        current_value = _sum_metric(current_txs, metric, category)
        previous_value = _sum_metric(previous_txs, metric, category)
        diff = current_value - previous_value
        percent_change = None if previous_value == 0 else (diff / previous_value) * 100

        result = {
            "tool": "compare_periods",
            "metric": metric or "expense",
            "category": category or "all",
            "current_period": current_period,
            "current_period_range": _format_period(current_start, current_end),
            "current_value": current_value,
            "current_transaction_count": len(current_txs),
            "compare_period": compare_period,
            "compare_period_range": _format_period(previous_start, previous_end),
            "previous_value": previous_value,
            "previous_transaction_count": len(previous_txs),
            "difference": diff,
            "percent_change": percent_change,
            "percent_change_note": "N/A because previous_value is 0" if previous_value == 0 else None,
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def execute_top_transactions(firebase_uid: str, timeframe: str, transaction_type: str = "expense", limit: int = 5, category: str = "all") -> str:
    try:
        safe_limit = max(1, min(int(limit or 5), 10))
        txs, start, end = _fetch_transactions_for_period(firebase_uid, timeframe)

        type_key = (transaction_type or "expense").strip().lower()
        expected_type = 1 if type_key in {"income", "thu", "thu_nhap"} else 0
        filtered = [
            tx for tx in txs
            if tx.get("type") == expected_type and _category_matches(tx.get("category", ""), category)
        ]
        filtered.sort(key=lambda tx: tx.get("amount", 0), reverse=True)

        result = {
            "tool": "top_transactions",
            "timeframe": timeframe,
            "period_range": _format_period(start, end),
            "transaction_type": transaction_type or "expense",
            "category": category or "all",
            "limit": safe_limit,
            "matched_count": len(filtered),
            "top_transactions": filtered[:safe_limit],
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def execute_merchant_spending(firebase_uid: str, merchant: str, timeframe: str) -> str:
    try:
        merchant_key = (merchant or "").strip().lower()
        txs, start, end = _fetch_transactions_for_period(firebase_uid, timeframe)
        matched = []

        for tx in txs:
            if tx.get("type") != 0:
                continue
            haystack = f"{tx.get('source', '')} {tx.get('note', '')}".lower()
            if merchant_key and merchant_key in haystack:
                matched.append(tx)

        total_spent = sum(tx.get("amount", 0) for tx in matched)
        matched.sort(key=lambda tx: tx.get("amount", 0), reverse=True)

        result = {
            "tool": "merchant_spending",
            "merchant": merchant,
            "timeframe": timeframe,
            "period_range": _format_period(start, end),
            "total_spent": total_spent,
            "matched_count": len(matched),
            "matched_examples": matched[:5],
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def execute_category_trend(firebase_uid: str, current_period: str, compare_period: str, limit: int = 5) -> str:
    try:
        safe_limit = max(1, min(int(limit or 5), 10))
        current_txs, current_start, current_end = _fetch_transactions_for_period(firebase_uid, current_period)
        previous_txs, previous_start, previous_end = _fetch_transactions_for_period(firebase_uid, compare_period)

        def group_expenses(transactions: list[dict]) -> dict[str, float]:
            grouped = {}
            for tx in transactions:
                if tx.get("type") != 0:
                    continue
                cat = tx.get("category", "Khac")
                grouped[cat] = grouped.get(cat, 0.0) + tx.get("amount", 0)
            return grouped

        current_by_cat = group_expenses(current_txs)
        previous_by_cat = group_expenses(previous_txs)
        all_categories = sorted(set(current_by_cat) | set(previous_by_cat))

        trends = []
        for cat in all_categories:
            current_value = current_by_cat.get(cat, 0.0)
            previous_value = previous_by_cat.get(cat, 0.0)
            diff = current_value - previous_value
            percent_change = None if previous_value == 0 else (diff / previous_value) * 100
            trends.append({
                "category": cat,
                "current_value": current_value,
                "previous_value": previous_value,
                "difference": diff,
                "percent_change": percent_change,
                "percent_change_note": "N/A because previous_value is 0" if previous_value == 0 else None,
            })

        trends.sort(key=lambda item: item["difference"], reverse=True)
        result = {
            "tool": "category_trend",
            "current_period": current_period,
            "current_period_range": _format_period(current_start, current_end),
            "compare_period": compare_period,
            "compare_period_range": _format_period(previous_start, previous_end),
            "limit": safe_limit,
            "top_increases": trends[:safe_limit],
            "top_decreases": sorted(trends, key=lambda item: item["difference"])[:safe_limit],
        }
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        traceback.print_exc()
        return json.dumps({"error": str(e)})


def chat_with_agentic_ai(text: str, firebase_uid: str) -> Optional[str]:
    """
    Gọi OpenRouter với Function Calling để giải đáp truy vấn.
    """
    tools = [
        {
            "type": "function",
            "function": {
                "name": "query_database",
                "description": "Truy vấn dữ liệu Firebase để lấy tổng thu/chi theo danh mục và khoảng thời gian.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": { "type": "string", "description": "Danh mục (ví dụ: 'Ăn uống', 'Tất cả', 'Chi tiêu', 'Thu nhập')" },
                        "timeframe": { "type": "string", "description": "Khoảng thời gian: 'today', 'current_week', 'last_week', 'current_month', 'last_month', 'all_time'" }
                    },
                    "required": ["category", "timeframe"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "schedule_report",
                "description": "Lên lịch gửi báo cáo tài chính vào một thời điểm trong tương lai.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "target_datetime": { "type": "string", "description": "Thời gian gửi báo cáo (định dạng ISO 8601, ví dụ: '2026-05-08T16:20:00+07:00')" },
                        "report_type": { "type": "string", "description": "Loại báo cáo cần gửi (ví dụ: 'weekly_summary', 'daily_summary')" }
                    },
                    "required": ["target_datetime", "report_type"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "compare_periods",
                "description": "Compare computed financial totals between two periods. Python computes all totals and percentage changes from Firestore.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "metric": { "type": "string", "description": "Metric to compare: expense, income, or net. Default expense." },
                        "current_period": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" },
                        "compare_period": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" },
                        "category": { "type": "string", "description": "Optional category, or all." }
                    },
                    "required": ["metric", "current_period", "compare_period"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "top_transactions",
                "description": "Return the largest transactions in a period. Default limit is 5, maximum is 10.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeframe": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" },
                        "transaction_type": { "type": "string", "description": "expense or income. Default expense." },
                        "limit": { "type": "integer", "description": "Number of transactions. Default 5, max 10." },
                        "category": { "type": "string", "description": "Optional category, or all." }
                    },
                    "required": ["timeframe"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "merchant_spending",
                "description": "Compute spending at a merchant/store/brand/payee by matching source and note. Returns matched_count and examples.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "merchant": { "type": "string", "description": "Merchant, store, brand, wallet, or payee name, e.g. Highlands." },
                        "timeframe": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" }
                    },
                    "required": ["merchant", "timeframe"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "category_trend",
                "description": "Compare category spending between two periods and return strongest increases/decreases.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "current_period": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" },
                        "compare_period": { "type": "string", "description": "today, current_week, last_week, current_month, last_month, all_time" },
                        "limit": { "type": "integer", "description": "Number of categories. Default 5, max 10." }
                    },
                    "required": ["current_period", "compare_period"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "set_budget_alert",
                "description": "CHỈ sử dụng công cụ này khi người dùng muốn thiết lập mục tiêu tài chính, hạn mức hoặc ngân sách (từ khóa: đặt hạn mức, đặt ngân sách, giới hạn chi tiêu). KHÔNG sử dụng công cụ này để ghi chép các khoản chi tiêu thông thường.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "category": { "type": "string", "description": "Danh mục cần đặt ngân sách (ví dụ: 'Ăn uống', 'Tất cả')" },
                        "budget_amount": { "type": "number", "description": "Số tiền hạn mức (ví dụ: 5000000)" },
                        "threshold_pct": { "type": "number", "description": "Phần trăm ngưỡng cảnh báo (ví dụ: 80)" }
                    },
                    "required": ["category", "budget_amount", "threshold_pct"]
                }
            }
        }
    ]

    messages = [
        {"role": "system", "content": AGENTIC_SYSTEM_PROMPT},
        {"role": "user", "content": text}
    ]

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto"
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/Hoangsonn05/So-Thu-Chi-React-Native",
        "X-Title": "So Thu Chi Agent"
    }

    try:
        response = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        result = response.json()
        
        message = result['choices'][0]['message']
        
        if message.get("tool_calls"):
            tool_call = message["tool_calls"][0]
            function_name = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"])
            
            print(f"[Agentic AI] Dùng tool: {function_name} với args: {arguments}")
            
            if function_name == "query_database":
                db_result = execute_query_database(
                    firebase_uid=firebase_uid,
                    category=arguments.get("category", "Tất cả"),
                    timeframe=arguments.get("timeframe", "current_month")
                )
            elif function_name == "schedule_report":
                db_result = execute_schedule_report(
                    firebase_uid=firebase_uid,
                    target_datetime_iso=arguments.get("target_datetime"),
                    report_type=arguments.get("report_type", "summary")
                )
            elif function_name == "compare_periods":
                db_result = execute_compare_periods(
                    firebase_uid=firebase_uid,
                    metric=arguments.get("metric", "expense"),
                    current_period=arguments.get("current_period", "current_month"),
                    compare_period=arguments.get("compare_period", "last_month"),
                    category=arguments.get("category", "all")
                )
            elif function_name == "top_transactions":
                db_result = execute_top_transactions(
                    firebase_uid=firebase_uid,
                    timeframe=arguments.get("timeframe", "current_month"),
                    transaction_type=arguments.get("transaction_type", "expense"),
                    limit=arguments.get("limit", 5),
                    category=arguments.get("category", "all")
                )
            elif function_name == "merchant_spending":
                db_result = execute_merchant_spending(
                    firebase_uid=firebase_uid,
                    merchant=arguments.get("merchant", ""),
                    timeframe=arguments.get("timeframe", "current_month")
                )
            elif function_name == "category_trend":
                db_result = execute_category_trend(
                    firebase_uid=firebase_uid,
                    current_period=arguments.get("current_period", "current_month"),
                    compare_period=arguments.get("compare_period", "last_month"),
                    limit=arguments.get("limit", 5)
                )
            elif function_name == "set_budget_alert":
                db_result = execute_set_budget_alert(
                    firebase_uid=firebase_uid,
                    category=arguments.get("category", "Tất cả"),
                    budget_amount=arguments.get("budget_amount", 0),
                    threshold_pct=arguments.get("threshold_pct", 80)
                )
            else:
                db_result = json.dumps({"error": "Unknown function"})
            
            # CẬP NHẬT: Đưa khối lệnh xử lý Tool Response ra ngoài khối if/else
            # Đảm bảo dù là tool nào thì kết quả cũng được gửi về cho AI tổng hợp
            
            # Cập nhật danh sách message với tool response
            messages.append(message) 
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "name": function_name,
                "content": db_result
            })
            messages.append({
                "role": "system",
                "content": (
                    "Format the final Telegram reply for mobile. Use light emoji, short lines, "
                    "and VND dot separators like 57.948.200đ. Avoid raw markdown such as '- **...'. "
                    "Only describe computed values returned by tools. Do not infer causes or trends "
                    "not explicitly present in tool output."
                )
            })
            
            payload["messages"] = messages
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            
            second_response = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=60)
            second_response.raise_for_status()
            second_result = second_response.json()
            
            final_answer = second_result['choices'][0]['message']['content']
            return final_answer.strip()
                
        elif message.get("content"):
            return message["content"].strip()
            
    except Exception as e:
        print(f"[Agentic AI Error] {e}")
        traceback.print_exc()
        return "Hiện tại hệ thống đang gặp sự cố kết nối hoặc dữ liệu. Bạn vui lòng thử lại sau ít phút nhé!"

# -------------- CRON JOB HÀNG TUẦN --------------

def send_fcm_push(firebase_uid: str, title: str, body: str):
    """ Gửi Push notification cho ứng dụng di động qua FCM. """
    try:
        db = firestore.client()
        user_doc = db.collection("users").document(firebase_uid).get()
        if not user_doc.exists: return
        
        user_data = user_doc.to_dict() or {}
        fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")
        
        if not fcm_token: return
        
        msg = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            data={"type": "WEEKLY_REPORT"},
            android=messaging.AndroidConfig(priority="high"),
            token=fcm_token,
        )
        messaging.send(msg)
        print(f"[CronJob] Đã gửi FCM cho {firebase_uid}")
    except Exception as e:
        print(f"[CronJob] Lỗi gửi FCM: {e}")

def send_tg_msg(bot_token: str, chat_id: int, text: str):
    """ Gửi Telegram (dùng lại code từ main hoặc viết hàm gọi thẳng API). """
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[CronJob] Lỗi gửi Telegram: {e}")

# -------------- RECURRING EXPENSE DETECTION --------------

RECURRING_LOOKBACK_DAYS = 90
RECURRING_CYCLES_DAYS = (7, 14, 30, 31)
RECURRING_AMOUNT_TOLERANCE = 0.10
RECURRING_MIN_CONFIDENCE_TO_NOTIFY = 0.65
RECURRING_NOTIFY_COOLDOWN_DAYS = 30


def _strip_accents(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value or "")
    return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")


def _normalize_recurring_text(value: str) -> str:
    text = _strip_accents(value or "").lower()
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", " ", text)
    text = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", text)
    text = re.sub(r"\b(ngay|date|luc|vao)\s+\d{1,2}\b", " ", text)
    text = re.sub(r"\b\d+([.,]\d+)?\s*(k|nghin|ngan|tr|trieu|d|đ|vnd|dong)\b", " ", text)
    text = re.sub(r"\b\d{4,}\b", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\b(thanh\s*toan|payment|gd|giao\s*dich|hoa\s*don|bill|auto|autopay|ck|chuyen\s*khoan)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _clean_recurring_display_text(value: str) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\b\d{1,2}[/-]\d{1,2}([/-]\d{2,4})?\b", " ", text)
    text = re.sub(r"\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b", " ", text)
    text = re.sub(r"\b\d+([.,]\d+)?\s*(k|nghìn|ngàn|tr|triệu|d|đ|vnd|đồng)\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"[_*`~|]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -:;,.")
    return text[:80]


def _transaction_datetime(data: dict) -> Optional[datetime]:
    ts = data.get("timestamp")
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)

    date_text = data.get("date")
    if isinstance(date_text, str):
        for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(date_text, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
    return None


def _format_vnd(amount: float) -> str:
    return f"{int(round(amount)):,.0f}".replace(",", ".") + "đ"


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _amounts_are_close(amounts: list[float]) -> bool:
    if len(amounts) < 2:
        return False
    baseline = _median(amounts)
    if baseline <= 0:
        return False
    return all(abs(amount - baseline) / baseline <= RECURRING_AMOUNT_TOLERANCE for amount in amounts)


def _best_cycle(dates: list[datetime]) -> tuple[Optional[int], float]:
    if len(dates) < 2:
        return None, 0.0
    gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
    if not gaps:
        return None, 0.0

    best_cycle = None
    best_score = 0.0
    for cycle in RECURRING_CYCLES_DAYS:
        matched = sum(1 for gap in gaps if abs(gap - cycle) <= 3)
        score = matched / len(gaps)
        if score > best_score:
            best_cycle = cycle
            best_score = score
    return best_cycle, best_score


def _recurring_confidence(occurrences: int, amount_score: float, interval_score: float) -> float:
    occurrence_score = 1.0 if occurrences >= 3 else 0.72
    confidence = (occurrence_score * 0.35) + (amount_score * 0.30) + (interval_score * 0.35)
    return round(min(confidence, 0.99), 2)


def _recurring_doc_ref(db, firebase_uid: str, insight_id: str):
    return (
        db.collection("users")
        .document(firebase_uid)
        .collection("finance_insights")
        .document("recurring_expenses")
        .collection("items")
        .document(insight_id)
    )


def _build_recurring_message(item: dict) -> str:
    label = item.get("merchant_or_note") or "Khoản chi"
    amount = _format_vnd(float(item.get("estimated_amount", 0) or 0))
    frequency = int(item.get("frequency_days", 0) or 0)
    if frequency in (30, 31):
        period = "mỗi tháng"
    elif frequency == 14:
        period = "mỗi 2 tuần"
    elif frequency == 7:
        period = "mỗi tuần"
    else:
        period = f"mỗi {frequency} ngày"
    return f"Phát hiện khoản chi lặp lại: {label} khoảng {amount} {period}."


def _should_notify_recurring(existing: dict, item: dict, now: datetime) -> bool:
    if item.get("confidence", 0) < RECURRING_MIN_CONFIDENCE_TO_NOTIFY:
        return False
    if not existing:
        return True

    old_amount = float(existing.get("estimated_amount", 0) or 0)
    new_amount = float(item.get("estimated_amount", 0) or 0)
    amount_changed = old_amount > 0 and abs(new_amount - old_amount) / old_amount > 0.15
    frequency_changed = existing.get("frequency_days") != item.get("frequency_days")

    last_notified = existing.get("last_notified_at")
    if isinstance(last_notified, datetime):
        last_notified = last_notified if last_notified.tzinfo else last_notified.replace(tzinfo=timezone.utc)
        if now - last_notified < timedelta(days=RECURRING_NOTIFY_COOLDOWN_DAYS):
            return amount_changed or frequency_changed

    return amount_changed or frequency_changed or existing.get("status") != "active"


def detect_recurring_expenses(firebase_uid: str) -> list[dict]:
    db = firestore.client()
    now = datetime.now(timezone.utc)
    start_utc = now - timedelta(days=RECURRING_LOOKBACK_DAYS)
    notified_items = []

    try:
        query = (
            db.collection("users")
            .document(firebase_uid)
            .collection("transactions")
            .where(filter=FieldFilter("timestamp", ">=", start_utc))
            .where(filter=FieldFilter("timestamp", "<=", now))
        )

        groups: dict[str, list[dict]] = {}
        for doc in query.stream():
            data = doc.to_dict() or {}
            if data.get("isDeleted", False) is True or data.get("type") != 0:
                continue

            tx_dt = _transaction_datetime(data)
            if not tx_dt:
                continue

            try:
                amount = float(data.get("amount", 0) or 0)
            except (TypeError, ValueError):
                amount = 0
            if amount <= 0:
                continue

            merchant = _normalize_recurring_text(str(data.get("merchant", "")))
            source = _normalize_recurring_text(str(data.get("source", "")))
            note = _normalize_recurring_text(str(data.get("note", "")))
            display_label = (
                _clean_recurring_display_text(data.get("merchant", ""))
                or _clean_recurring_display_text(data.get("note", ""))
                or _clean_recurring_display_text(data.get("source", ""))
            )
            key_parts = [part for part in (merchant, source, note) if part]
            if not key_parts:
                continue

            key = "|".join(key_parts)
            groups.setdefault(key, []).append({
                "amount": amount,
                "timestamp": tx_dt,
                "merchant_or_note": display_label or merchant or note or source,
            })

        user_doc = db.collection("users").document(firebase_uid).get()
        user_data = user_doc.to_dict() if user_doc.exists else {}
        tg_config = (user_data or {}).get("telegramConfig") or {}
        bot_token = tg_config.get("botToken")
        chat_id = tg_config.get("chatId")
        active_ids = set()

        for key, txs in groups.items():
            if len(txs) < 2:
                continue

            txs.sort(key=lambda tx: tx["timestamp"])
            amounts = [tx["amount"] for tx in txs]
            if not _amounts_are_close(amounts):
                continue

            dates = [tx["timestamp"] for tx in txs]
            frequency_days, interval_score = _best_cycle(dates)
            if not frequency_days or interval_score <= 0:
                continue

            estimated_amount = _median(amounts)
            max_deviation = max(abs(amount - estimated_amount) / estimated_amount for amount in amounts)
            amount_score = 1.0 - min(max_deviation, RECURRING_AMOUNT_TOLERANCE) / RECURRING_AMOUNT_TOLERANCE
            confidence = _recurring_confidence(len(txs), amount_score, interval_score)
            insight_id = hashlib.sha1(f"{key}|{frequency_days}".encode("utf-8")).hexdigest()[:24]
            active_ids.add(insight_id)

            doc_ref = _recurring_doc_ref(db, firebase_uid, insight_id)
            existing_snap = doc_ref.get()
            existing = existing_snap.to_dict() if existing_snap.exists else {}
            item = {
                "merchant_or_note": txs[-1]["merchant_or_note"],
                "estimated_amount": round(estimated_amount, 2),
                "frequency_days": frequency_days,
                "occurrences": len(txs),
                "first_seen": dates[0],
                "last_seen": dates[-1],
                "confidence": confidence,
                "status": "active",
                "normalized_key": key,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }
            if not existing:
                item["created_at"] = firestore.SERVER_TIMESTAMP
                item["last_notified_at"] = None

            should_notify = _should_notify_recurring(existing, item, now)
            if should_notify and bot_token and chat_id:
                send_tg_msg(bot_token, chat_id, _build_recurring_message(item))
                item["last_notified_at"] = firestore.SERVER_TIMESTAMP
                notified_items.append({"id": insight_id, **item})
            elif existing and "last_notified_at" in existing:
                item["last_notified_at"] = existing.get("last_notified_at")

            doc_ref.set(item, merge=True)

        existing_docs = (
            db.collection("users")
            .document(firebase_uid)
            .collection("finance_insights")
            .document("recurring_expenses")
            .collection("items")
            .stream()
        )
        for snap in existing_docs:
            if snap.id not in active_ids and (snap.to_dict() or {}).get("status") == "active":
                snap.reference.set({"status": "inactive", "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)

    except Exception as e:
        print(f"[Recurring Detection Error] uid={firebase_uid}: {e}")
        traceback.print_exc()

    return notified_items


def recurring_expenses_daily_job():
    print(f"[Recurring Job] Scan started: {datetime.now(tz=VN_TZ).strftime('%Y-%m-%d %H:%M:%S')}")
    db = firestore.client()
    try:
        for user_doc in db.collection("users").stream():
            detect_recurring_expenses(user_doc.id)
    except Exception as e:
        print(f"[Recurring Job Error] {e}")
        traceback.print_exc()

# -------------- POLLING JOB HÀNG PHÚT --------------

def _default_task_id(uid: str, task_type: str) -> str:
    return f"{uid}_{task_type}_default"


def _create_default_task_if_missing(db, uid: str, task_type: str, send_time: str) -> None:
    doc_ref = db.collection("scheduled_tasks").document(_default_task_id(uid, task_type))
    if doc_ref.get().exists:
        return
    now_utc = datetime.now(timezone.utc)
    task = {
        "uid": uid,
        "task_type": task_type,
        "schedule_type": "default_daily",
        "status": "active",
        "timezone": DEFAULT_TIMEZONE,
        "time": send_time,
        "last_run_at": None,
        "last_success_at": None,
        "retry_count": 0,
        "payload": {"source": "system_default", "skip_default_if_manual_before_scheduled": False},
        "created_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    task["next_run_at"] = calculate_next_run_at(task, now_utc)
    doc_ref.set(task, merge=True)
    print(f"[Scheduler] ensured default task uid={uid} task={task_type} time={send_time}")


def _user_has_custom_finance_task(db, uid: str) -> bool:
    for snap in db.collection("scheduled_tasks").where(filter=FieldFilter("uid", "==", uid)).stream():
        task = snap.to_dict() or {}
        if task.get("status") not in TASK_ACTIVE_STATUSES:
            continue
        if task.get("schedule_type") == "default_daily":
            continue
        if _task_type_from_legacy(task) in {"expense_report", "daily_finance_report"}:
            return True
    return False


def ensure_default_scheduled_tasks(db) -> None:
    for user_doc in db.collection("users").stream():
        user_data = user_doc.to_dict() or {}
        tg_config = user_data.get("telegramConfig") or {}
        fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")
        if not ((tg_config.get("botToken") and tg_config.get("chatId")) or fcm_token):
            continue
        uid = user_doc.id
        for task_type in sorted(EXTERNAL_BRIEF_TASK_TYPES):
            _create_default_task_if_missing(db, uid, task_type, DEFAULT_EXTERNAL_SEND_TIME)
        if not _user_has_custom_finance_task(db, uid):
            _create_default_task_if_missing(db, uid, DEFAULT_DAILY_FINANCE_TASK_TYPE, DEFAULT_FINANCE_SEND_TIME)


def ensure_default_scheduled_tasks_job() -> None:
    print(f"[Scheduler] ensure default tasks started: {datetime.now(tz=VN_TZ).strftime('%H:%M:%S')}")
    db = firestore.client()
    try:
        ensure_default_scheduled_tasks(db)
    except Exception as e:
        print(f"[Scheduler] ensure default tasks failed: {e}")
        traceback.print_exc()


def _brief_prompt_for_task(task_type: str) -> str:
    if task_type == "gold_price_brief":
        return "Tao ban tin ngan ve gia vang hom nay cho nguoi dung Viet Nam. Neu khong co du lieu realtime, noi ro he thong chua co nguon gia realtime."
    if task_type == "fuel_price_brief":
        return "Tao ban tin ngan ve gia xang dau Viet Nam hom nay. Neu khong co du lieu realtime, noi ro he thong chua co nguon gia realtime."
    if task_type == "ai_price_brief":
        return "Tao ban tin ngan ve gia/chi phi cac dich vu AI pho bien hom nay. Neu khong co du lieu realtime, noi ro he thong chua co nguon gia realtime."
    return "Tao ban tin buoi sang gom vang, xang dau va gia/chi phi AI. Neu khong co du lieu realtime, noi ro cac muc nao chua co nguon realtime."


def _external_brief_snapshot_ref(db, task_type: str, date_key: str):
    return db.collection("external_brief_snapshots").document(f"{task_type}_{date_key}")


def get_external_brief_snapshot(task_type: str, date_key: str) -> dict:
    db = firestore.client()
    snap = _external_brief_snapshot_ref(db, task_type, date_key).get()
    return snap.to_dict() if snap.exists else {}


def _save_external_brief_snapshot(task_type: str, date_key: str, content: str, source_status: str, source_payload: Optional[dict] = None) -> None:
    db = firestore.client()
    _external_brief_snapshot_ref(db, task_type, date_key).set({
        "task_type": task_type,
        "date_key": date_key,
        "content": content,
        "source_status": source_status,
        "source_payload": source_payload or {},
        "generated_at": firestore.SERVER_TIMESTAMP,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)


def collect_external_brief_data(task_type: str, date_key: str) -> Optional[dict]:
    """Hook for real collectors.

    Expected future return shape:
    {
        "content": "ready-to-send Vietnamese brief",
        "sources": [{"name": "...", "url": "..."}],
    }
    """
    return None


def _render_external_brief(task_type: str, collected: Optional[dict]) -> tuple[str, str, dict]:
    if collected and isinstance(collected.get("content"), str) and collected["content"].strip():
        return collected["content"].strip(), "collector", collected
    return EXTERNAL_BRIEF_FALLBACK_MESSAGE, "collector_not_configured", {}


def generate_external_brief(task_type: str, uid: Optional[str] = None, now: Optional[datetime] = None, force_refresh: bool = False) -> str:
    if task_type not in EXTERNAL_BRIEF_TASK_TYPES:
        raise ValueError("unsupported_external_brief_type")

    current = now or get_vn_now()
    date_key = get_date_key(current, DEFAULT_TIMEZONE)
    if not force_refresh:
        cached = get_external_brief_snapshot(task_type, date_key)
        cached_content = (cached or {}).get("content")
        if isinstance(cached_content, str) and cached_content.strip():
            print(f"[External Brief] cache hit task={task_type} date={date_key}")
            return cached_content.strip()

    collected = collect_external_brief_data(task_type, date_key)
    content, source_status, source_payload = _render_external_brief(task_type, collected)
    _save_external_brief_snapshot(task_type, date_key, content, source_status, source_payload)
    print(f"[External Brief] generated task={task_type} date={date_key} source={source_status}")
    return content


def generate_finance_report(uid: str, task_type: str) -> str:
    timeframe = _timeframe_for_task_type(task_type)
    if task_type == "weekly_finance_report":
        query = "Hay lap bao cao tai chinh tuan nay (current_week): tong thu, tong chi, so du va top khoan chi lon."
    elif task_type == "monthly_finance_report":
        query = "Hay lap bao cao tai chinh thang nay (current_month): tong thu, tong chi, so du va top khoan chi lon."
    else:
        query = f"Hay lap bao cao tai chinh hom nay ({timeframe}): tong thu, tong chi, so du va cac khoan chi dang chu y."
    return chat_with_agentic_ai(query, uid) or "Chua tao duoc bao cao tai chinh luc nay."


def send_manual_report_previous(uid: str, task_type: str) -> str:
    db = firestore.client()
    user_doc = db.collection("users").document(uid).get()
    user_data = user_doc.to_dict() if user_doc.exists else {}
    tg_config = (user_data or {}).get("telegramConfig") or {}
    bot_token = tg_config.get("botToken")
    chat_id = tg_config.get("chatId")
    if task_type in EXTERNAL_BRIEF_TASK_TYPES:
        content = generate_external_brief(task_type)
        scheduled_time = DEFAULT_EXTERNAL_SEND_TIME
        now = get_vn_now()
        hour, minute = _parse_hhmm(scheduled_time, DEFAULT_EXTERNAL_SEND_TIME)
        skip_auto = now < now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        mark_manual_report_delivery(uid, task_type, scheduled_time, skip_auto_today=skip_auto)
        title = "Bao cao du lieu ngoai"
    else:
        content = generate_finance_report(uid, task_type)
        scheduled_time = DEFAULT_FINANCE_SEND_TIME
        mark_manual_report_delivery(uid, task_type, scheduled_time, skip_auto_today=False)
        title = "Bao cao tai chinh"
    if bot_token and chat_id:
        send_tg_msg(bot_token, chat_id, f"{title}\n\n{content}")
    return content


def _normalize_task_for_execution(task: dict) -> dict:
    normalized = dict(task)
    task_type = _task_type_from_legacy(task)
    normalized["task_type"] = task_type
    normalized.setdefault("schedule_type", "once" if task.get("target_datetime") else "daily")
    normalized.setdefault("timezone", DEFAULT_TIMEZONE)
    normalized.setdefault("time", DEFAULT_EXTERNAL_SEND_TIME if task_type in EXTERNAL_BRIEF_TASK_TYPES else DEFAULT_FINANCE_SEND_TIME)
    normalized.setdefault("payload", {})
    normalized.setdefault("retry_count", 0)
    return normalized


def _task_due(task: dict, now_utc: datetime) -> bool:
    next_run = _coerce_datetime(task.get("next_run_at")) or _coerce_datetime(task.get("target_datetime"))
    return bool(next_run and next_run <= now_utc)


def _execute_scheduled_task(db, doc, task: dict, now_utc: datetime) -> None:
    task = _normalize_task_for_execution(task)
    uid = task.get("uid")
    task_type = task.get("task_type")
    scheduled_time = task.get("time") or DEFAULT_FINANCE_SEND_TIME
    if not uid:
        doc.reference.set({"status": "failed", "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
        return
    doc.reference.set({"status": "processing", "last_run_at": firestore.SERVER_TIMESTAMP, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
    try:
        if not should_skip_auto_delivery(uid, task_type, scheduled_time, now_utc):
            user_doc = db.collection("users").document(uid).get()
            if not user_doc.exists:
                raise ValueError(f"user not found: {uid}")
            user_data = user_doc.to_dict() or {}
            tg_config = user_data.get("telegramConfig") or {}
            bot_token = tg_config.get("botToken")
            chat_id = tg_config.get("chatId")
            fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")
            if task_type in EXTERNAL_BRIEF_TASK_TYPES:
                content = generate_external_brief(task_type)
                title = "Bao cao du lieu ngoai"
            else:
                content = generate_finance_report(uid, task_type)
                title = "Bao cao tai chinh"
            if bot_token and chat_id:
                send_tg_msg(bot_token, chat_id, f"{title}\n\n{content}")
            if fcm_token:
                send_fcm_push(uid, title, content[:150] + ("..." if len(content) > 150 else ""))
            date_key = get_date_key(now_utc, task.get("timezone") or DEFAULT_TIMEZONE)
            current_state = get_delivery_state(uid, task_type, date_key)
            update_delivery_state(
                uid,
                task_type,
                date_key,
                scheduled_time=scheduled_time,
                auto_send_done=True,
                manual_send_done=current_state.get("manual_send_done", False),
                skip_auto_today=current_state.get("skip_auto_today", False),
                last_auto_at=firestore.SERVER_TIMESTAMP,
                last_report_id=doc.id,
            )
        schedule_type = task.get("schedule_type")
        if schedule_type == "once":
            doc.reference.set({"status": "completed", "last_success_at": firestore.SERVER_TIMESTAMP, "updated_at": firestore.SERVER_TIMESTAMP}, merge=True)
        else:
            doc.reference.set({
                "status": "active",
                "next_run_at": calculate_next_run_at(task, now_utc + timedelta(seconds=1)),
                "last_success_at": firestore.SERVER_TIMESTAMP,
                "retry_count": 0,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }, merge=True)
        print(f"[Scheduler] task done id={doc.id} uid={uid} type={task_type}")
    except Exception as e:
        retry_count = int(task.get("retry_count", 0) or 0) + 1
        doc.reference.set({
            "status": "active" if task.get("schedule_type") != "once" else "pending",
            "next_run_at": now_utc + timedelta(minutes=min(30, 2 ** min(retry_count, 5))),
            "retry_count": retry_count,
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        print(f"[Scheduler] task failed id={doc.id} uid={uid} type={task_type}: {e}")
        traceback.print_exc()


def poll_scheduled_tasks_job_legacy():
    """ Quét Firestore mỗi phút để tìm và thực thi các báo cáo đến hạn. """
    print(f"[Polling Job] Quét các tác vụ đến hạn: {datetime.now(tz=VN_TZ).strftime('%H:%M:%S')}")
    db = firestore.client()
    try:
        now_utc = datetime.now(timezone.utc)
        
        # Lấy các task pending và đã đến/qua hạn
        tasks_query = db.collection("scheduled_tasks").where(filter=FieldFilter("status", "==", "pending")).where(filter=FieldFilter("target_datetime", "<=", now_utc))
        docs = tasks_query.stream()
        
        for doc in docs:
            task_data = doc.to_dict()
            uid = task_data.get("uid")
            
            print(f"[Polling Job] Đang thực thi task {doc.id} cho user {uid}")
            
            # Cập nhật status thành completed (để không chạy lại)
            doc.reference.update({"status": "completed"})
            
            # Lấy thông tin user để gửi báo cáo
            user_doc = db.collection("users").document(uid).get()
            if not user_doc.exists:
                continue
                
            user_data = user_doc.to_dict()
            tg_config = user_data.get("telegramConfig")
            bot_token = tg_config.get("botToken") if tg_config else None
            chat_id = tg_config.get("chatId") if tg_config else None
            fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")
            
            if (bot_token and chat_id) or fcm_token:
                # Dùng AI để tạo báo cáo
                report_query = "Hãy lập một báo cáo tài chính ngắn gọn nhưng đầy đủ cho tôi trong 7 ngày qua (last_week). Liệt kê tổng thu, tổng chi và những khoản chi tiêu lớn nhất."
                report_content = chat_with_agentic_ai(report_query, uid)
                
                if report_content:
                    title = "📊 Báo cáo Tài chính Đã Lên Lịch"
                    
                    if bot_token and chat_id:
                        send_tg_msg(bot_token, chat_id, f"*{title}*\n\n{report_content}")
                    
                    if fcm_token:
                        short_body = report_content[:150] + ("..." if len(report_content) > 150 else "")
                        send_fcm_push(uid, title, short_body)
                        
    except FailedPrecondition as fpe:
        # Lỗi Index Firestore: Log ra thay vì in toàn bộ traceback hoặc crash
        print(f"[Polling Job Error] Firestore Error: Index missing or is currently building. Bỏ qua lần quét này. Chi tiết: {fpe}")
    except Exception as e:
        print(f"[Polling Job Error] {e}")
        traceback.print_exc()

def poll_scheduled_tasks_job_previous():
    """Quet Firestore moi phut de thuc thi scheduled_tasks schema moi va task cu."""
    print(f"[Polling Job] scan due tasks: {datetime.now(tz=VN_TZ).strftime('%H:%M:%S')}")
    db = firestore.client()
    try:
        now_utc = datetime.now(timezone.utc)
        ensure_default_scheduled_tasks(db)

        seen_ids = set()
        for status in ("active", "pending"):
            for doc in db.collection("scheduled_tasks").where(filter=FieldFilter("status", "==", status)).stream():
                if doc.id in seen_ids:
                    continue
                seen_ids.add(doc.id)
                task_data = doc.to_dict() or {}
                if _task_due(task_data, now_utc):
                    print(f"[Polling Job] executing task id={doc.id} uid={task_data.get('uid')} type={_task_type_from_legacy(task_data)}")
                    _execute_scheduled_task(db, doc, task_data, now_utc)
    except FailedPrecondition as fpe:
        print(f"[Polling Job Error] Firestore index missing/building. Skip this scan. Detail: {fpe}")
    except Exception as e:
        print(f"[Polling Job Error] {e}")
        traceback.print_exc()


class NoDeliveryChannelError(Exception):
    pass


def _scheduler_now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_legacy_task(task: dict) -> dict:
    normalized = dict(task or {})
    task_type = _task_type_from_legacy(normalized)
    normalized["task_type"] = task_type
    normalized.setdefault("schedule_type", "once" if normalized.get("target_datetime") else "daily")
    normalized.setdefault("timezone", DEFAULT_TIMEZONE)
    normalized.setdefault(
        "time",
        DEFAULT_EXTERNAL_SEND_TIME if task_type in EXTERNAL_BRIEF_TASK_TYPES else DEFAULT_FINANCE_SEND_TIME,
    )
    normalized.setdefault("payload", {})
    normalized.setdefault("retry_count", 0)
    if not normalized.get("next_run_at") and normalized.get("target_datetime"):
        normalized["next_run_at"] = normalized.get("target_datetime")
    return normalized


def _is_due_task(task: dict, now_utc: datetime) -> bool:
    normalized = _normalize_legacy_task(task)
    next_run = _coerce_datetime(normalized.get("next_run_at")) or _coerce_datetime(normalized.get("target_datetime"))
    return bool(next_run and next_run <= now_utc)


def _processing_lock_active(task: dict, now_utc: datetime) -> bool:
    if (task.get("status") or "").lower() != "processing":
        return False
    lock_until = _coerce_datetime(task.get("processing_lock_until"))
    return bool(lock_until and lock_until > now_utc)


def _claim_scheduled_task(db, task_id: str, now_utc: datetime) -> Optional[dict]:
    doc_ref = db.collection("scheduled_tasks").document(task_id)
    transaction = db.transaction()

    @firestore.transactional
    def _claim(transaction):
        snap = doc_ref.get(transaction=transaction)
        if not snap.exists:
            return None
        current = _normalize_legacy_task(snap.to_dict() or {})
        status = (current.get("status") or "").lower()
        if status in TASK_TERMINAL_STATUSES:
            return {"_skip_reason": "terminal_status", **current}
        if _processing_lock_active(current, now_utc):
            return {"_skip_reason": "processing_lock_active", **current}
        if status not in {"active", "pending", "processing"}:
            return {"_skip_reason": "not_runnable_status", **current}
        if not _is_due_task(current, now_utc):
            return {"_skip_reason": "not_due", **current}

        transaction.set(doc_ref, {
            "status": "processing",
            "task_type": current.get("task_type"),
            "schedule_type": current.get("schedule_type"),
            "timezone": current.get("timezone"),
            "time": current.get("time"),
            "next_run_at": current.get("next_run_at"),
            "processing_started_at": now_utc,
            "processing_lock_until": now_utc + timedelta(minutes=SCHEDULER_LOCK_MINUTES),
            "updated_at": firestore.SERVER_TIMESTAMP,
        }, merge=True)
        current["_previous_status"] = status
        return current

    return _claim(transaction)


def _mark_task_failed(task_id: str, task_data: dict, failed_reason: str, terminal: bool = False) -> None:
    db = firestore.client()
    normalized = _normalize_legacy_task(task_data)
    retry_count = int(normalized.get("retry_count", 0) or 0)
    next_retry_count = retry_count + 1
    should_terminal = terminal or next_retry_count >= SCHEDULER_MAX_RETRIES
    schedule_type = normalized.get("schedule_type")
    retry_status = "pending" if schedule_type == "once" else "active"
    update = {
        "status": "failed" if should_terminal else retry_status,
        "retry_count": next_retry_count,
        "failed_reason": failed_reason,
        "last_failed_at": firestore.SERVER_TIMESTAMP,
        "processing_lock_until": None,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if not should_terminal:
        update["next_run_at"] = _scheduler_now_utc() + timedelta(minutes=min(30, 2 ** min(next_retry_count, 5)))
    db.collection("scheduled_tasks").document(task_id).set(update, merge=True)


def _mark_task_success(task_id: str, task_data: dict, now_utc: datetime) -> None:
    db = firestore.client()
    normalized = _normalize_legacy_task(task_data)
    schedule_type = (normalized.get("schedule_type") or "once").lower()
    update = {
        "last_run_at": now_utc,
        "last_success_at": now_utc,
        "retry_count": 0,
        "failed_reason": None,
        "processing_lock_until": None,
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    if schedule_type == "once":
        update["status"] = "completed"
    else:
        update["status"] = "active"
        update["next_run_at"] = calculate_next_run_at(normalized, now_utc + timedelta(seconds=1))
    db.collection("scheduled_tasks").document(task_id).set(update, merge=True)


def send_report_to_user(uid: str, title: str, content: str, payload: Optional[dict] = None) -> dict:
    db = firestore.client()
    user_doc = db.collection("users").document(uid).get()
    if not user_doc.exists:
        raise NoDeliveryChannelError("user_not_found")

    user_data = user_doc.to_dict() or {}
    tg_config = user_data.get("telegramConfig") or {}
    bot_token = tg_config.get("botToken")
    chat_id = tg_config.get("chatId")
    fcm_token = user_data.get("fcmToken") or user_data.get("fcm_token")

    sent = {"telegram": False, "fcm": False}
    errors = {}
    if bot_token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            resp = requests.post(url, json={"chat_id": chat_id, "text": f"{title}\n\n{content}"}, timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(f"{resp.status_code}:{resp.text[:120]}")
            sent["telegram"] = True
        except Exception as e:
            errors["telegram"] = str(e)

    if fcm_token:
        try:
            msg = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=content[:150] + ("..." if len(content) > 150 else ""),
                ),
                data={
                    "type": "SCHEDULED_REPORT",
                    "task_type": str((payload or {}).get("task_type", "")),
                },
                android=messaging.AndroidConfig(priority="high"),
                token=fcm_token,
            )
            messaging.send(msg)
            sent["fcm"] = True
        except Exception as e:
            errors["fcm"] = str(e)

    if not any(sent.values()):
        if errors:
            raise RuntimeError(f"delivery_failed:{errors}")
        raise NoDeliveryChannelError("no_delivery_channel")
    if errors:
        print(f"[Scheduler] partial delivery uid={uid} sent={sent} errors={errors}")
    return sent


def handle_manual_external_report_request(uid: str, requested_type: str, source: str = "telegram") -> str:
    if requested_type not in EXTERNAL_BRIEF_TASK_TYPES:
        raise ValueError("unsupported_external_brief_type")

    now = get_vn_now()
    date_key = get_date_key(now, DEFAULT_TIMEZONE)
    scheduled_time = DEFAULT_EXTERNAL_SEND_TIME
    hour, minute = _parse_hhmm(scheduled_time, DEFAULT_EXTERNAL_SEND_TIME)
    scheduled_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    current_state = get_delivery_state(uid, requested_type, date_key)
    skip_auto_today = bool(current_state.get("skip_auto_today")) or now < scheduled_at

    content = generate_external_brief(requested_type, uid=uid, now=now)
    title = EXTERNAL_BRIEF_TITLES.get(requested_type, "Bao cao du lieu ngoai")
    send_report_to_user(uid, title, content, {
        "task_type": requested_type,
        "delivery_mode": "manual",
        "source": source,
    })
    update_delivery_state(
        uid,
        requested_type,
        date_key,
        scheduled_time=scheduled_time,
        auto_send_done=bool(current_state.get("auto_send_done", False)),
        manual_send_done=True,
        skip_auto_today=skip_auto_today,
        last_manual_at=firestore.SERVER_TIMESTAMP,
        last_report_id=f"manual_{requested_type}_{date_key}",
        last_manual_source=source,
    )
    print(
        f"[Scheduler] manual external report sent uid={uid} type={requested_type} "
        f"date={date_key} skip_auto_today={skip_auto_today}"
    )
    return content


def send_manual_report(uid: str, task_type: str) -> str:
    if task_type in EXTERNAL_BRIEF_TASK_TYPES:
        return handle_manual_external_report_request(uid, task_type, source="manual_report")

    content = generate_finance_report(uid, task_type)
    scheduled_time = DEFAULT_FINANCE_SEND_TIME
    mark_manual_report_delivery(uid, task_type, scheduled_time, skip_auto_today=False)
    send_report_to_user(uid, "Bao cao tai chinh", content, {"task_type": task_type, "delivery_mode": "manual"})
    print(f"[Scheduler] manual report sent uid={uid} type={task_type} skip_auto_today=False")
    return content


def _scheduled_report_content(uid: str, task_type: str, payload: dict) -> tuple[str, str]:
    if task_type in EXTERNAL_BRIEF_TASK_TYPES:
        return "Bao cao du lieu ngoai", generate_external_brief(task_type)
    if task_type in FINANCE_REPORT_TASK_TYPES:
        return "Bao cao tai chinh", generate_finance_report(uid, task_type)
    raise ValueError("unsupported_task_type")


def _mark_auto_delivery(uid: str, task_type: str, task_id: str, scheduled_time: str, now_utc: datetime) -> None:
    date_key = get_date_key(now_utc, DEFAULT_TIMEZONE)
    state = get_delivery_state(uid, task_type, date_key)
    update_delivery_state(
        uid,
        task_type,
        date_key,
        scheduled_time=scheduled_time,
        auto_send_done=True,
        manual_send_done=state.get("manual_send_done", False),
        skip_auto_today=state.get("skip_auto_today", False),
        last_auto_at=firestore.SERVER_TIMESTAMP,
        last_report_id=task_id,
    )


def execute_scheduled_task(task_id: str, task_data: dict) -> dict:
    db = firestore.client()
    now_utc = _scheduler_now_utc()
    claimed = _claim_scheduled_task(db, task_id, now_utc)
    if not claimed:
        print(f"[Scheduler] task skipped id={task_id} reason=not_found")
        return {"status": "skipped", "reason": "not_found"}

    skip_reason = claimed.get("_skip_reason")
    if skip_reason:
        print(f"[Scheduler] task skipped id={task_id} reason={skip_reason}")
        return {"status": "skipped", "reason": skip_reason}

    task = _normalize_legacy_task(claimed)
    uid = task.get("uid")
    task_type = task.get("task_type")
    scheduled_time = task.get("time") or DEFAULT_FINANCE_SEND_TIME
    payload = task.get("payload") or {}

    try:
        if not uid:
            raise ValueError("missing_uid")
        if task_type not in SUPPORTED_SCHEDULED_TASK_TYPES:
            _mark_task_failed(task_id, task, "unsupported_task_type", terminal=True)
            print(f"[Scheduler] task failed id={task_id} reason=unsupported_task_type")
            return {"status": "failed", "reason": "unsupported_task_type"}

        if should_skip_auto_delivery(uid, task_type, scheduled_time, now_utc):
            _mark_task_success(task_id, task, now_utc)
            print(f"[Scheduler] task skipped due delivery_state id={task_id} uid={uid} type={task_type}")
            return {"status": "skipped", "reason": "delivery_state"}

        title, content = _scheduled_report_content(uid, task_type, payload)
        send_result = send_report_to_user(uid, title, content, {"task_type": task_type, **payload})
        _mark_auto_delivery(uid, task_type, task_id, scheduled_time, now_utc)
        _mark_task_success(task_id, task, now_utc)
        print(f"[Scheduler] task success id={task_id} uid={uid} type={task_type} sent={send_result}")
        return {"status": "success", "sent": send_result}
    except NoDeliveryChannelError as e:
        reason = str(e) or "no_delivery_channel"
        _mark_task_failed(task_id, task, reason, terminal=True)
        print(f"[Scheduler] task failed id={task_id} uid={uid} type={task_type} reason={reason}")
        return {"status": "failed", "reason": reason}
    except Exception as e:
        reason = str(e)[:300] or e.__class__.__name__
        _mark_task_failed(task_id, task, reason, terminal=False)
        print(f"[Scheduler] task failed id={task_id} uid={uid} type={task_type} reason={reason}")
        traceback.print_exc()
        return {"status": "failed", "reason": reason}


def _collect_due_scheduled_tasks(db, now_utc: datetime) -> list[tuple[str, dict]]:
    due_tasks: list[tuple[str, dict]] = []
    seen_ids = set()
    for status in ("active", "pending", "processing"):
        for doc in db.collection("scheduled_tasks").where(filter=FieldFilter("status", "==", status)).stream():
            if doc.id in seen_ids:
                continue
            seen_ids.add(doc.id)
            task = doc.to_dict() or {}
            if status == "processing" and _processing_lock_active(task, now_utc):
                print(f"[Scheduler] task skipped due active lock id={doc.id}")
                continue
            if _is_due_task(task, now_utc):
                due_tasks.append((doc.id, task))
    return due_tasks


def poll_scheduled_tasks_job():
    """Task dispatcher entrypoint called by APScheduler every minute."""
    db = firestore.client()
    now_utc = _scheduler_now_utc()
    try:
        due_tasks = _collect_due_scheduled_tasks(db, now_utc)
        print(f"[Scheduler] due task count={len(due_tasks)} at={now_utc.isoformat()}")
        for task_id, task_data in due_tasks:
            try:
                execute_scheduled_task(task_id, task_data)
            except Exception as task_error:
                print(f"[Scheduler] unexpected task crash id={task_id}: {task_error}")
                traceback.print_exc()
    except FailedPrecondition as fpe:
        print(f"[Scheduler] Firestore index missing/building. Skip scan. Detail: {fpe}")
    except Exception as e:
        print(f"[Scheduler] polling batch failed: {e}")
        traceback.print_exc()

# -------------- DYNAMIC BUDGETING & PROACTIVE ALERTS --------------

def generate_ai_budget_warning(firebase_uid: str, data: dict):
    """ Gọi AI để tạo lời cảnh báo cá nhân hóa khi vượt ngưỡng ngân sách. """
    print(f"[Budget Alert] Đang gọi AI tạo cảnh báo cho {firebase_uid} - {data['category']}")
    
    prompt = f"""Bạn là Giám đốc tài chính AI. Hãy đưa ra một lời cảnh báo NGẮN GỌN (dưới 50 từ), 
    thân thiện nhưng nghiêm túc về việc chi tiêu cho danh mục '{data['category']}'.
    
    Thông số hiện tại:
    - Hạn mức tháng: {data['budget_amount']:,.0f}đ
    - Đã tiêu: {data['current_spent']:,.0f}đ ({data['percent_used']:.1f}% hạn mức)
    - Dự báo cuối tháng sẽ tiêu: {data['projected_spent']:,.0f}đ
    
    Hãy đưa ra một lời khuyên thực tế để người dùng cân đối lại chi tiêu."""

    try:
        payload = {
            "model": MODEL_NAME,
            "messages": [{"role": "user", "content": prompt}]
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "HTTP-Referer": "https://github.com/Hoangsonn05/So-Thu-Chi-React-Native",
            "X-Title": "So Thu Chi Budget Alert"
        }
        
        response = requests.post(OPENROUTER_API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        ai_msg = response.json()['choices'][0]['message']['content'].strip()
        
        # Gửi qua Telegram và FCM
        db = firestore.client()
        user_doc = db.collection("users").document(firebase_uid).get()
        if user_doc.exists:
            u_data = user_doc.to_dict()
            tg = u_data.get("telegramConfig")
            if tg and tg.get("chatId") and tg.get("botToken"):
                send_tg_msg(tg["botToken"], tg["chatId"], f"⚠️ *CẢNH BÁO NGÂN SÁCH*\n\n{ai_msg}")
            
            fcm_token = u_data.get("fcmToken") or u_data.get("fcm_token")
            if fcm_token:
                send_fcm_push(firebase_uid, "⚠️ Cảnh báo chi tiêu", ai_msg)
                
    except Exception as e:
        print(f"[Budget Alert Error] AI Warning failed: {e}")

def check_budget_thresholds(firebase_uid: str, category: str, new_amount: float):
    """ 
    Logic Gating: Kiểm tra toán học trước khi quyết định gọi AI.
    Hàm này được gọi mỗi khi có giao dịch chi tiêu mới.
    """
    db = firestore.client()
    try:
        # 1. Lấy cấu hình ngân sách (kiểm tra category cụ thể và 'Tất cả')
        budgets_ref = db.collection("user_budgets").document(firebase_uid).collection("budgets")
        budget_docs = budgets_ref.stream()
        
        # Danh sách các cấu hình ngân sách liên quan
        relevant_budgets = []
        for b in budget_docs:
            b_data = b.to_dict()
            b_cat = b_data.get("category", "Tất cả")
            if b_cat == "Tất cả" or b_cat.lower() == category.lower():
                relevant_budgets.append(b_data)
        
        if not relevant_budgets:
            return

        # 2. Tính toán chi tiêu trong tháng hiện tại
        now = datetime.now(tz=VN_TZ)
        start_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        # Số ngày trong tháng
        _, days_in_month = calendar.monthrange(now.year, now.month)
        current_day = now.day
        
        start_utc = start_month.astimezone(timezone.utc)
        
        # Query Firestore để tính tổng chi tiêu tháng này
        # (Lưu ý: Yêu cầu index trên category + timestamp + createdBy nếu filter category)
        for budget in relevant_budgets:
            target_cat = budget["category"]
            
            query = db.collection("users").document(firebase_uid).collection("transactions")
            query = query.where(filter=FieldFilter("type", "==", 0)).where(filter=FieldFilter("isDeleted", "==", False)).where(filter=FieldFilter("timestamp", ">=", start_utc))
            
            if target_cat != "Tất cả":
                query = query.where(filter=FieldFilter("category", "==", target_cat))
            
            docs = query.stream()
            total_spent = 0
            for doc in docs:
                total_spent += doc.to_dict().get("amount", 0)
            
            # 3. Tính toán Gating & Projection
            budget_amount = budget["budget_amount"]
            threshold_pct = budget.get("alert_threshold_percentage", 80)
            percent_used = (total_spent / budget_amount) * 100
            
            # Dự báo: (số tiền tiêu / số ngày qua) * tổng số ngày trong tháng
            projected_spent = (total_spent / current_day) * days_in_month
            
            # 4. Kiểm tra điều kiện gọi AI
            # Điều kiện: Tiêu quá ngưỡng % HOẶC Dự báo tiêu vượt ngân sách
            should_alert = (percent_used >= threshold_pct) or (projected_spent > budget_amount)
            
            if should_alert:
                # 5. Throttling: Kiểm tra lần cuối gửi cảnh báo (tránh spam)
                last_alert = budget.get("last_alert_sent")
                if last_alert:
                    # Chuyển timestamp về VN time
                    last_dt = last_alert.astimezone(VN_TZ)
                    if last_dt.date() == now.date():
                        # Đã gửi cảnh báo hôm nay rồi
                        print(f"[Budget Alert] Throttled: Đã gửi cảnh báo cho {target_cat} hôm nay.")
                        continue
                
                # 6. Kích hoạt AI tạo nội dung và gửi
                alert_data = {
                    "category": target_cat,
                    "budget_amount": budget_amount,
                    "current_spent": total_spent,
                    "percent_used": percent_used,
                    "projected_spent": projected_spent
                }
                generate_ai_budget_warning(firebase_uid, alert_data)
                
                # 7. Cập nhật last_alert_sent
                budgets_ref.document(target_cat).update({"last_alert_sent": firestore.SERVER_TIMESTAMP})

    except Exception as e:
        print(f"[Budget Check Error] {e}")
        traceback.print_exc()
