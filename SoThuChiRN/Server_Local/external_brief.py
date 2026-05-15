from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_admin import firestore

from external_collectors import (
    collect_ai_pricing,
    collect_all_external_data,
    collect_fuel_price,
    collect_gold_price,
)


DISCLAIMER = "Dữ liệu chỉ để tham khảo, không phải khuyến nghị tài chính."
DEFAULT_TIMEZONE_OFFSET = timezone(timedelta(hours=7))
TASK_TOPICS = {
    "gold_price_brief": ["gold"],
    "fuel_price_brief": ["fuel"],
    "ai_price_brief": ["ai_pricing"],
    "morning_external_brief": ["gold", "fuel", "ai_pricing"],
}
TASK_TITLES = {
    "morning_external_brief": "Báo cáo thị trường sáng",
    "gold_price_brief": "Báo cáo giá vàng",
    "fuel_price_brief": "Báo cáo giá xăng dầu",
    "ai_price_brief": "Báo cáo giá AI",
}


def _now() -> datetime:
    return datetime.now(DEFAULT_TIMEZONE_OFFSET)


def _date_key(now: Optional[datetime] = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TIMEZONE_OFFSET)
    return current.astimezone(DEFAULT_TIMEZONE_OFFSET).strftime("%Y-%m-%d")


def _collect_for_task(task_type: str, force_refresh: bool) -> dict:
    if task_type == "gold_price_brief":
        return {"gold": collect_gold_price(force_refresh=force_refresh)}
    if task_type == "fuel_price_brief":
        return {"fuel": collect_fuel_price(force_refresh=force_refresh)}
    if task_type == "ai_price_brief":
        return {"ai_pricing": collect_ai_pricing(force_refresh=force_refresh)}
    if task_type == "morning_external_brief":
        return collect_all_external_data(force_refresh=force_refresh)
    raise ValueError("unsupported_external_brief_type")


def _format_gold(snapshot: dict) -> list[str]:
    lines = ["Giá vàng:"]
    items = snapshot.get("items") or []
    if items:
        for item in items[:4]:
            name = item.get("brand") or item.get("name") or "Vàng"
            buy = item.get("buy") or "?"
            sell = item.get("sell") or "?"
            unit = item.get("unit") or ""
            lines.append(f"- {name}: mua {buy}, bán {sell} {unit}".strip())
    else:
        lines.append(f"- {snapshot.get('summary') or 'Chưa có dữ liệu giá vàng rõ ràng.'}")
    if snapshot.get("error"):
        lines.append(f"- Lưu ý: {snapshot.get('error')}")
    lines.append(f"Nguồn: {snapshot.get('source_url') or snapshot.get('source') or 'chưa cấu hình'}")
    return lines


def _format_fuel(snapshot: dict) -> list[str]:
    lines = ["Giá xăng dầu:"]
    items = snapshot.get("items") or []
    if items:
        for item in items[:6]:
            period = f", kỳ {item.get('period')}" if item.get("period") else ""
            lines.append(f"- {item.get('name', 'Nhiên liệu')}: {item.get('price', '?')} {item.get('unit', '')}{period}".strip())
    else:
        lines.append(f"- {snapshot.get('summary') or 'Chưa có dữ liệu giá xăng dầu rõ ràng.'}")
    if snapshot.get("error"):
        lines.append(f"- Lưu ý: {snapshot.get('error')}")
    lines.append(f"Nguồn: {snapshot.get('source_url') or snapshot.get('source') or 'chưa cấu hình'}")
    return lines


def _format_ai(snapshot: dict) -> list[str]:
    lines = ["Giá/gói AI:"]
    lines.append(f"- {snapshot.get('summary') or 'Chưa có cập nhật mới.'}")
    for item in (snapshot.get("items") or [])[:3]:
        provider = item.get("provider") or "AI"
        status = item.get("status") or "unknown"
        note = item.get("note")
        if note:
            lines.append(f"- {provider}: {note}")
        else:
            lines.append(f"- {provider}: theo dõi trang chính thức ({status}).")
    if snapshot.get("error"):
        lines.append(f"- Lưu ý: {snapshot.get('error')}")
    lines.append(f"Nguồn: {snapshot.get('source_url') or snapshot.get('source') or 'official pricing pages'}")
    return lines


def format_external_brief(task_type: str, snapshots: dict, now: Optional[datetime] = None) -> str:
    title = TASK_TITLES.get(task_type, "Báo cáo dữ liệu ngoài")
    lines = [f"{title} - {_date_key(now)}"]
    if "gold" in snapshots:
        lines.extend(["", *_format_gold(snapshots.get("gold") or {})])
    if "fuel" in snapshots:
        lines.extend(["", *_format_fuel(snapshots.get("fuel") or {})])
    if "ai_pricing" in snapshots:
        lines.extend(["", *_format_ai(snapshots.get("ai_pricing") or {})])
    lines.extend(["", DISCLAIMER])
    return "\n".join(lines).strip()


def _sources_from_snapshots(snapshots: dict) -> list[dict]:
    sources = []
    for topic, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        sources.append({
            "topic": topic,
            "source": snapshot.get("source") or "",
            "url": snapshot.get("source_url") or "",
            "error": snapshot.get("error"),
            "confidence": snapshot.get("confidence", 0),
            "raw_hash": snapshot.get("raw_hash") or "",
        })
    return sources


def _external_report_ref(db, uid: str, report_id: str):
    return db.collection("users").document(uid).collection("external_reports").document(report_id)


def build_external_report_id(uid: str, task_type: str, date_key: str, mode: str, now: Optional[datetime] = None) -> str:
    if mode == "auto":
        return f"{uid}_{task_type}_{date_key}_auto"
    current = now or _now()
    return f"{uid}_{task_type}_{date_key}_manual_{current.strftime('%H%M%S')}"


def save_external_report(uid: str, report_id: str, task_type: str, date_key: str, mode: str, content: str, snapshots: dict, status: str = "generated", payload: Optional[dict] = None) -> None:
    db = firestore.client()
    _external_report_ref(db, uid, report_id).set({
        "uid": uid,
        "task_type": task_type,
        "date_key": date_key,
        "generated_at": firestore.SERVER_TIMESTAMP,
        "delivery_mode": mode,
        "title": TASK_TITLES.get(task_type, "Báo cáo dữ liệu ngoài"),
        "content": content,
        "sources": _sources_from_snapshots(snapshots),
        "snapshots": snapshots,
        "status": status,
        "payload": payload or {},
        "updated_at": firestore.SERVER_TIMESTAMP,
    }, merge=True)


def generate_external_brief(uid: str, task_type: str, mode: str = "auto", force_refresh: bool = False, now: Optional[datetime] = None, report_id: Optional[str] = None, save_report: bool = True, payload: Optional[dict] = None) -> dict:
    if task_type not in TASK_TOPICS:
        raise ValueError("unsupported_external_brief_type")

    current = now or _now()
    date_key = _date_key(current)
    snapshots = _collect_for_task(task_type, force_refresh=force_refresh)
    content = format_external_brief(task_type, snapshots, current)
    final_report_id = report_id or build_external_report_id(uid, task_type, date_key, mode, current)
    if save_report:
        save_external_report(uid, final_report_id, task_type, date_key, mode, content, snapshots, payload=payload)
    return {
        "report_id": final_report_id,
        "task_type": task_type,
        "date_key": date_key,
        "content": content,
        "sources": _sources_from_snapshots(snapshots),
        "snapshots": snapshots,
    }
