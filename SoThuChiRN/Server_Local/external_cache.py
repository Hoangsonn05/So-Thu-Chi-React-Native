from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_admin import firestore


EXTERNAL_SNAPSHOTS_COLLECTION = "external_snapshots"
REPORTABLE_STATUSES = {"ok", "partial"}
RAW_TEXT_SHORT_LIMIT = 4000


def _snapshot_ref(db, topic: str, date_key: str):
    return db.collection(EXTERNAL_SNAPSHOTS_COLLECTION).document(f"{topic}_{date_key}")


def is_reportable_snapshot(snapshot: Optional[dict]) -> bool:
    if not snapshot:
        return False
    return (
        snapshot.get("status") in REPORTABLE_STATUSES
        and bool(snapshot.get("has_valid_items"))
        and bool(snapshot.get("is_valid"))
    )


def get_external_snapshot(topic: str, date_key: str, reportable_only: bool = False) -> dict:
    db = firestore.client()
    snap = _snapshot_ref(db, topic, date_key).get()
    data = snap.to_dict() if snap.exists else {}
    if reportable_only and not is_reportable_snapshot(data):
        return {}
    return data


def _date_keys_before(before_date_key: str, max_days: int) -> list[str]:
    try:
        current = datetime.strptime(before_date_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return []
    return [(current - timedelta(days=offset)).strftime("%Y-%m-%d") for offset in range(1, max_days + 1)]


def find_recent_snapshot(topic: str, before_date_key: str, max_days: int = 14, reportable_only: bool = True) -> Optional[dict]:
    for date_key in _date_keys_before(before_date_key, max_days):
        snapshot = get_external_snapshot(topic, date_key, reportable_only=reportable_only)
        if snapshot:
            return snapshot
    return None


def find_recent_snapshot_with_hash(topic: str, before_date_key: str, max_days: int = 14) -> Optional[dict]:
    for date_key in _date_keys_before(before_date_key, max_days):
        snapshot = get_external_snapshot(topic, date_key, reportable_only=False)
        if snapshot.get("raw_hash"):
            return snapshot
    return None


def _item_history_key(topic: str, item: dict) -> str:
    return item.get("item_key") or item.get("key") or f"{topic}.{item.get('name') or item.get('provider') or 'item'}"


def _numeric_fields(item: dict) -> dict:
    fields = {}
    for key, value in item.items():
        if key in {"source_time", "source_name", "source_url", "unit", "name", "model", "provider", "region", "item_key"}:
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            fields[key] = value
    return fields


def build_item_history(topic: str, items: list[dict], previous_snapshot: Optional[dict]) -> dict:
    previous_items = {}
    for item in (previous_snapshot or {}).get("items") or []:
        previous_items[_item_history_key(topic, item)] = item

    history = {}
    for item in items or []:
        item_key = _item_history_key(topic, item)
        prev = previous_items.get(item_key) or {}
        for field, value in _numeric_fields(item).items():
            prev_value = prev.get(field)
            if not isinstance(prev_value, (int, float)) or prev_value == 0:
                continue
            change_abs = value - prev_value
            history[f"{item_key}.{field}"] = {
                "previous": prev_value,
                "current": value,
                "change_abs": change_abs,
                "change_pct": round(change_abs / prev_value * 100, 4),
            }
    return history


def save_external_snapshot(snapshot: dict) -> dict:
    db = firestore.client()
    topic = snapshot.get("topic")
    date_key = snapshot.get("date_key")
    if not topic or not date_key:
        raise ValueError("external_snapshot_requires_topic_and_date_key")

    raw_text_short = snapshot.get("raw_text_short")
    if isinstance(raw_text_short, str):
        raw_text_short = raw_text_short[:RAW_TEXT_SHORT_LIMIT]

    previous_snapshot = find_recent_snapshot(topic, date_key, reportable_only=True)
    items = snapshot.get("items") or []
    payload = {
        "topic": topic,
        "date_key": date_key,
        "status": snapshot.get("status") or ("ok" if items else "failed"),
        "source": snapshot.get("source") or snapshot.get("source_name") or "",
        "source_name": snapshot.get("source_name") or snapshot.get("source") or "",
        "source_url": snapshot.get("source_url") or "",
        "fetched_at": snapshot.get("fetched_at") or firestore.SERVER_TIMESTAMP,
        "source_time": snapshot.get("source_time"),
        "title": snapshot.get("title") or "",
        "items": items,
        "errors": snapshot.get("errors") or ([] if not snapshot.get("error") else [snapshot.get("error")]),
        "warnings": snapshot.get("warnings") or [],
        "summary": snapshot.get("summary") or "",
        "confidence": float(snapshot.get("confidence") or 0),
        "raw_hash": snapshot.get("raw_hash"),
        "raw_text_short": raw_text_short,
        "error": snapshot.get("error"),
        "is_valid": bool(snapshot.get("is_valid")),
        "has_valid_items": bool(snapshot.get("has_valid_items")),
        "history": build_item_history(topic, items, previous_snapshot),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    _snapshot_ref(db, topic, date_key).set(payload, merge=True)
    return payload
