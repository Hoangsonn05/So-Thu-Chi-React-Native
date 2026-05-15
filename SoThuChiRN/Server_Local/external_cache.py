from datetime import datetime, timedelta, timezone
from typing import Optional

from firebase_admin import firestore


EXTERNAL_SNAPSHOTS_COLLECTION = "external_snapshots"


def get_external_snapshot(topic: str, date_key: str) -> dict:
    db = firestore.client()
    snap = db.collection(EXTERNAL_SNAPSHOTS_COLLECTION).document(f"{topic}_{date_key}").get()
    return snap.to_dict() if snap.exists else {}


def save_external_snapshot(snapshot: dict) -> dict:
    db = firestore.client()
    topic = snapshot.get("topic")
    date_key = snapshot.get("date_key")
    if not topic or not date_key:
        raise ValueError("external_snapshot_requires_topic_and_date_key")

    payload = {
        "source": snapshot.get("source") or "",
        "source_url": snapshot.get("source_url") or "",
        "topic": topic,
        "fetched_at": snapshot.get("fetched_at") or firestore.SERVER_TIMESTAMP,
        "date_key": date_key,
        "title": snapshot.get("title") or "",
        "items": snapshot.get("items") or [],
        "summary": snapshot.get("summary") or "",
        "confidence": float(snapshot.get("confidence") or 0),
        "raw_hash": snapshot.get("raw_hash") or "",
        "error": snapshot.get("error"),
        "updated_at": firestore.SERVER_TIMESTAMP,
    }
    db.collection(EXTERNAL_SNAPSHOTS_COLLECTION).document(f"{topic}_{date_key}").set(payload, merge=True)
    return payload


def find_recent_snapshot_with_hash(topic: str, before_date_key: str, max_days: int = 14) -> Optional[dict]:
    try:
        current = datetime.strptime(before_date_key, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        return None

    for offset in range(1, max_days + 1):
        date_key = (current - timedelta(days=offset)).strftime("%Y-%m-%d")
        snapshot = get_external_snapshot(topic, date_key)
        if snapshot.get("raw_hash"):
            return snapshot
    return None
