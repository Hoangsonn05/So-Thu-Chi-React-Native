import os
import json
import requests
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional
from google.api_core.exceptions import FailedPrecondition

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
Nhiệm vụ của bạn là giải đáp các thắc mắc về tình hình tài chính của người dùng dựa trên dữ liệu thật, cũng như lên lịch báo cáo tự động theo yêu cầu.

Bạn BẮT BUỘC phải dùng công cụ `query_database` khi người dùng hỏi về:
- Tổng chi tiêu, thu nhập (ví dụ: "Tháng này tiêu bao nhiêu?", "Báo cáo tuần qua", "Hôm nay tôi tiêu gì?").
- Số tiền chi cho một danh mục cụ thể (ví dụ: "Tiêu bao nhiêu tiền ăn uống rồi?", "Tiền điện tháng này").

Bạn BẮT BUỘC phải dùng công cụ `schedule_report` khi người dùng yêu cầu đặt lịch báo cáo trong tương lai:
- Ví dụ: "Lên lịch báo cáo lúc 16:20 hôm nay", "Nhắc tôi xem báo cáo vào 8h sáng mai".
- Định dạng thời gian cho công cụ này là chuẩn ISO 8601 (ví dụ: 2026-05-08T16:20:00). Bạn tự tính toán datetime phù hợp theo múi giờ Việt Nam (UTC+7).

QUY TẮC:
1. KHÔNG tự bịa ra con số. Luôn gọi `query_database`.
2. Khi nhận được kết quả từ công cụ, hãy tổng hợp lại thành một đoạn văn ngắn gọn, chuyên nghiệp, lịch sự bằng tiếng Việt để báo cáo cho người dùng.
3. Nếu gọi `schedule_report`, hãy xác nhận với người dùng rằng lịch đã được lưu thành công.
"""

def execute_schedule_report(firebase_uid: str, target_datetime_iso: str, report_type: str) -> str:
    """ Lưu lịch báo cáo vào Firestore collection 'scheduled_tasks'. """
    db = firestore.client()
    try:
        # Nhận ISO string, chuyển thành datetime object chuẩn (đã có múi giờ hoặc gán UTC+7)
        dt = datetime.fromisoformat(target_datetime_iso.replace('Z', '+00:00'))
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
        traceback.print_exc()
        return json.dumps({"status": "error", "error": str(e)})

def execute_query_database(firebase_uid: str, category: str, timeframe: str) -> str:
    """
    Truy vấn dữ liệu Firestore dựa trên yêu cầu từ AI.
    """
    db = firestore.client()
    try:
        now = datetime.now(tz=VN_TZ)
        end_date = now
        
        if timeframe == "current_month":
            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "last_week":
            start_date = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif timeframe == "today":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else: # all_time
            start_date = now.replace(year=2000, month=1, day=1)

        start_utc = start_date.astimezone(timezone.utc)
        end_utc = end_date.astimezone(timezone.utc)

        query = db.collection("users").document(firebase_uid).collection("transactions")
        query = query.where("timestamp", ">=", start_utc).where("timestamp", "<=", end_utc)
        
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
                        "timeframe": { "type": "string", "description": "Khoảng thời gian: 'current_month', 'last_week', 'today', 'all_time'" }
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
            else:
                db_result = json.dumps({"error": "Unknown function"})
                
                # Nếu db_result chứa lỗi từ phía code gọi hàm (do try-except bên trong)
                # thì AI sẽ tự động đọc json {"error": ...} và có thể xin lỗi user.
                
                # Cập nhật danh sách message với tool response
                messages.append(message) 
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "name": function_name,
                    "content": db_result
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
        tasks_query = db.collection("scheduled_tasks").where("status", "==", "pending").where("target_datetime", "<=", now_utc)
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

