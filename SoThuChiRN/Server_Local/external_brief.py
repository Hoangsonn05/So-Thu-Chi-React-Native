from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_admin import firestore

from external_collectors import (
    collect_ai_pricing,
    collect_all_external_data,
    collect_fuel_price,
    collect_gold_price,
    collect_usd_vnd_rate,
)


DISCLAIMER = "Dữ liệu chỉ để tham khảo, không phải khuyến nghị tài chính."
DEFAULT_TIMEZONE_OFFSET = timezone(timedelta(hours=7))
TASK_TOPICS = {
    "gold_price_brief": ["gold"],
    "fuel_price_brief": ["fuel"],
    "ai_price_brief": ["ai_pricing"],
    "morning_external_brief": ["gold", "fuel", "usd_vnd", "ai_pricing"],
}
TASK_TITLES = {
    "morning_external_brief": "Báo cáo thị trường sáng",
    "gold_price_brief": "Báo cáo giá vàng",
    "fuel_price_brief": "Báo cáo giá xăng dầu",
    "ai_price_brief": "Báo cáo giá AI",
}
GROUP_LABELS = {
    "gold": "giá vàng",
    "fuel": "giá xăng dầu",
    "usd_vnd": "tỷ giá USD/VND",
    "ai_pricing": "giá API AI",
}


def _now() -> datetime:
    return datetime.now(DEFAULT_TIMEZONE_OFFSET)


def _date_key(now: Optional[datetime] = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TIMEZONE_OFFSET)
    return current.astimezone(DEFAULT_TIMEZONE_OFFSET).strftime("%Y-%m-%d")


def _time_label(now: Optional[datetime] = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TIMEZONE_OFFSET)
    return current.astimezone(DEFAULT_TIMEZONE_OFFSET).strftime("%Y-%m-%d %H:%M")


def _vnd(value) -> str:
    if value is None:
        return "N/A"
    return f"{int(value):,}".replace(",", ".")


def _usd(value) -> str:
    if value is None:
        return "N/A"
    return f"{float(value):g}"


def _is_valid_snapshot(snapshot: dict) -> bool:
    return bool(snapshot and snapshot.get("has_valid_items") and snapshot.get("status") in {"ok", "partial"})


def _tried_sources(snapshot: dict) -> str:
    source = snapshot.get("source_url") or snapshot.get("source_name") or snapshot.get("source")
    if source:
        return str(source)
    errors = snapshot.get("errors") or []
    if errors:
        return ", ".join(str(err).split(":", 1)[0] for err in errors[:4])
    return "chưa xác định"


def _failure_line(topic: str, snapshot: dict) -> list[str]:
    return [f"Không lấy được dữ liệu {GROUP_LABELS.get(topic, topic)}. Nguồn đã thử: {_tried_sources(snapshot)}"]


def _source_time(item: dict, snapshot: dict) -> str:
    return item.get("source_time") or item.get("effective_time") or snapshot.get("source_time") or "chưa rõ"


def _format_gold(snapshot: dict) -> list[str]:
    lines = ["🟡 Giá vàng Việt Nam"]
    if not _is_valid_snapshot(snapshot):
        return lines + _failure_line("gold", snapshot)

    items = snapshot.get("items") or []
    shown = items[:3]
    for item in shown:
        lines.extend([
            f"- {item.get('name', 'Vàng')}:",
            f"  Mua vào: {_vnd(item.get('buy_per_chi'))} VND/chỉ ({_vnd(item.get('buy_per_luong'))} VND/lượng)",
            f"  Bán ra: {_vnd(item.get('sell_per_chi'))} VND/chỉ ({_vnd(item.get('sell_per_luong'))} VND/lượng)",
            f"  Chênh lệch: {_vnd(item.get('spread_per_chi'))} VND/chỉ",
            f"  Nguồn: {item.get('source_name') or snapshot.get('source_name') or 'chưa rõ'}",
            f"  Cập nhật: {_source_time(item, snapshot)}",
        ])
    if len(items) > len(shown):
        lines.append(f"... và {len(items) - len(shown)} mục khác đã lưu trong snapshot.")
    return lines


def _format_fuel(snapshot: dict) -> list[str]:
    lines = ["⛽ Giá xăng dầu Việt Nam"]
    if not _is_valid_snapshot(snapshot):
        return lines + _failure_line("fuel", snapshot)

    items = snapshot.get("items") or []
    shown = items[:5]
    for item in shown:
        region = f" {item.get('region')}" if item.get("region") else ""
        lines.append(f"- {item.get('name', 'Nhiên liệu')}{region}: {_vnd(item.get('price'))} {item.get('unit')}")
    if shown:
        first = shown[0]
        lines.append(f"Nguồn: {first.get('source_name') or snapshot.get('source_name') or 'chưa rõ'}")
        lines.append(f"Thời điểm áp dụng: {_source_time(first, snapshot)}")
    if len(items) > len(shown):
        lines.append(f"... và {len(items) - len(shown)} mục khác đã lưu trong snapshot.")
    return lines


def _format_usd(snapshot: dict) -> list[str]:
    lines = ["💵 Tỷ giá USD/VND"]
    if not _is_valid_snapshot(snapshot):
        return lines + _failure_line("usd_vnd", snapshot)

    item = (snapshot.get("items") or [{}])[0]
    lines.extend([
        f"- Tỷ giá trung tâm NHNN: {_vnd(item.get('central_rate'))} VND/USD",
        f"- Mua vào tham khảo: {_vnd(item.get('buy'))} VND/USD",
        f"- Bán ra tham khảo: {_vnd(item.get('sell'))} VND/USD",
        f"Nguồn: {item.get('source_name') or snapshot.get('source_name') or 'chưa rõ'}",
        f"Cập nhật: {_source_time(item, snapshot)}",
    ])
    return lines


def _format_ai(snapshot: dict) -> list[str]:
    lines = ["🤖 Giá API AI"]
    if not _is_valid_snapshot(snapshot):
        return lines + _failure_line("ai_pricing", snapshot)

    grouped = {}
    for item in snapshot.get("items") or []:
        grouped.setdefault(item.get("provider") or "AI", []).append(item)

    hidden = 0
    for provider in ["OpenAI", "Gemini", "DeepSeek"]:
        provider_items = grouped.get(provider) or []
        if not provider_items:
            continue
        lines.append(f"{provider}:")
        shown = provider_items[:2]
        hidden += max(0, len(provider_items) - len(shown))
        for item in shown:
            if provider == "DeepSeek" and item.get("cache_hit_usd_per_1m") is not None:
                lines.append(
                    f"- {item.get('model')}: cache hit ${_usd(item.get('cache_hit_usd_per_1m'))}/1M, "
                    f"cache miss ${_usd(item.get('cache_miss_usd_per_1m'))}/1M, output ${_usd(item.get('output_usd_per_1m'))}/1M"
                )
            else:
                cached = item.get("cached_input_usd_per_1m")
                cached_part = f", cached ${_usd(cached)}/1M" if cached is not None else ""
                lines.append(
                    f"- {item.get('model')}: input ${_usd(item.get('input_usd_per_1m'))}/1M"
                    f"{cached_part}, output ${_usd(item.get('output_usd_per_1m'))}/1M"
                )
    if hidden:
        lines.append(f"... và {hidden} mục khác đã lưu trong snapshot.")
    return lines


def _quick_notes(snapshots: dict) -> list[str]:
    lines = ["📌 Nhận xét nhanh"]
    if "gold" in snapshots:
        gold = snapshots.get("gold") or {}
        gold_history = (gold.get("history") or {})
        if gold_history:
            first_change = next(iter(gold_history.values()))
            direction = "tăng" if first_change.get("change_abs", 0) > 0 else "giảm"
            lines.append(f"- Vàng: {direction} {_vnd(abs(first_change.get('change_abs', 0)))} VND so với snapshot gần nhất.")
        else:
            lines.append("- Vàng: Chưa có dữ liệu so sánh.")

    if "fuel" in snapshots:
        fuel = snapshots.get("fuel") or {}
        fuel_item = (fuel.get("items") or [{}])[0]
        if fuel_item.get("price"):
            lines.append(f"- Xăng dầu: {fuel_item.get('name')} hiện {_vnd(fuel_item.get('price'))} {fuel_item.get('unit')}.")
        else:
            lines.append("- Xăng dầu: Chưa có dữ liệu hợp lệ để nhận xét.")

    if "usd_vnd" in snapshots:
        usd = snapshots.get("usd_vnd") or {}
        usd_item = (usd.get("items") or [{}])[0]
        if usd_item.get("central_rate"):
            lines.append(f"- Tỷ giá: tỷ giá trung tâm {_vnd(usd_item.get('central_rate'))} VND/USD.")
        elif usd_item.get("sell"):
            lines.append(f"- Tỷ giá: bán ra tham khảo {_vnd(usd_item.get('sell'))} VND/USD.")
        else:
            lines.append("- Tỷ giá: Chưa có dữ liệu hợp lệ để nhận xét.")

    if "ai_pricing" in snapshots:
        ai = snapshots.get("ai_pricing") or {}
        ai_items = ai.get("items") or []
        priced = [item for item in ai_items if isinstance(item.get("output_usd_per_1m"), (int, float))]
        if priced:
            cheapest = min(priced, key=lambda item: item["output_usd_per_1m"])
            lines.append(
                f"- AI pricing: output rẻ nhất trong snapshot là {cheapest.get('provider')} "
                f"{cheapest.get('model')} (${_usd(cheapest.get('output_usd_per_1m'))}/1M)."
            )
        else:
            lines.append("- AI pricing: Chưa có dữ liệu model hợp lệ để nhận xét.")
    return lines


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


def format_external_brief(task_type: str, snapshots: dict, now: Optional[datetime] = None) -> str:
    lines = [f"📊 {TASK_TITLES.get(task_type, 'Báo cáo thị trường sáng')} - {_time_label(now)}"]
    if "gold" in snapshots:
        lines.extend(["", *_format_gold(snapshots.get("gold") or {})])
    if "fuel" in snapshots:
        lines.extend(["", *_format_fuel(snapshots.get("fuel") or {})])
    if "usd_vnd" in snapshots:
        lines.extend(["", *_format_usd(snapshots.get("usd_vnd") or {})])
    if "ai_pricing" in snapshots:
        lines.extend(["", *_format_ai(snapshots.get("ai_pricing") or {})])
    lines.extend(["", *_quick_notes(snapshots), "", DISCLAIMER])
    return "\n".join(lines).strip()


def _sources_from_snapshots(snapshots: dict) -> list[dict]:
    sources = []
    for topic, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        sources.append({
            "topic": topic,
            "source": snapshot.get("source_name") or snapshot.get("source") or "",
            "url": snapshot.get("source_url") or "",
            "status": snapshot.get("status"),
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
