import os
import smtplib
import tempfile
from datetime import datetime
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional

import firebase_admin
import pandas as pd
import uvicorn
from openpyxl.styles import Border, Font, Side
from openpyxl.utils import get_column_letter
from fastapi import FastAPI, HTTPException
from firebase_admin import credentials, firestore
from pydantic import BaseModel, Field

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FIREBASE_KEY_PATH = os.path.join(BASE_DIR, "firebase_key.json")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
GMAIL_USER = "sothuchi3@gmail.com"
GMAIL_APP_PASSWORD ="tflj trrq ixes hhux"
EMAIL_FROM_NAME = "Báo cáo giao dịch"

if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred)

db = firestore.client()
app = FastAPI(title="Firestore Export API")


class ExportEmailRequest(BaseModel):
    userId: str = Field(..., min_length=1)
    userEmail: str = Field(..., min_length=1)


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
    msg = MIMEMultipart()
    msg["Subject"] = "Báo cáo Excel giao dịch"
    msg["From"] = f"{EMAIL_FROM_NAME} <{GMAIL_USER}>"
    msg["To"] = to_email
    msg.attach(MIMEText("Đính kèm file báo cáo Excel theo yêu cầu.", "plain", "utf-8"))

    with open(attachment_path, "rb") as f:
        part = MIMEBase("application", "vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        part.set_payload(f.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f'attachment; filename="{filename}"')
    msg.attach(part)

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.starttls()
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, [to_email], msg.as_string())


@app.post("/api/export-email")
def export_email(body: ExportEmailRequest):
    if not os.path.isfile(FIREBASE_KEY_PATH):
        raise HTTPException(status_code=500, detail="Thiếu firebase_key.json")

    try:
        rows = _fetch_transactions(body.userId)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi Firestore: {e!s}") from e

    fd, tmp_path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    filename = f"bao_cao_{body.userId}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx"

    try:
        _build_excel(tmp_path, rows)
        try:
            _send_email_with_attachment(body.userEmail, tmp_path, filename)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi gửi email: {e!s}") from e
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


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
