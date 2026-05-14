import os
import json
import requests
import traceback
import calendar
from datetime import datetime, timezone, timedelta
from typing import Optional
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
VN_TZ = timezone(timedelta(hours=7))

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

def execute_schedule_report(firebase_uid: str, target_datetime_iso: str, report_type: str) -> str:
    """ Lưu lịch báo cáo vào Firestore collection 'scheduled_tasks'. """
    db = firestore.client()
    try:
        print(f"[Execute Tool] schedule_report: target={target_datetime_iso}, type={report_type}")
        # Nhận ISO string, chuyển thành datetime object chuẩn (đã có múi giờ hoặc gán UTC+7)
        # Python 3.7+ hỗ trợ fromisoformat với múi giờ (+07:00)
        dt_str = target_datetime_iso.replace('Z', '+00:00')
        dt = datetime.fromisoformat(dt_str)
        
        # Đảm bảo lưu đúng định dạng để sau này query dễ dàng
        target_utc = dt.astimezone(timezone.utc)
        
        task_data = {
            "uid": firebase_uid,
            "target_datetime": target_utc,
            "report_type": report_type,
            "status": "pending",
            "created_at": firestore.SERVER_TIMESTAMP
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

# -------------- POLLING JOB HÀNG PHÚT --------------

def poll_scheduled_tasks_job():
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
