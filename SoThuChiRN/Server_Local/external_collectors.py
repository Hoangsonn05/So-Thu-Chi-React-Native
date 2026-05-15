import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Optional

import requests
from firebase_admin import firestore

from external_cache import get_external_snapshot, save_external_snapshot, find_recent_snapshot_with_hash


DEFAULT_TIMEZONE_OFFSET = timezone(timedelta(hours=7))
HTTP_TIMEOUT_SECONDS = float(os.getenv("EXTERNAL_COLLECTOR_TIMEOUT_SECONDS", "7"))
USER_AGENT = os.getenv(
    "EXTERNAL_COLLECTOR_USER_AGENT",
    "SoThuChiExternalBrief/1.0 (+personal finance brief)",
)
GOLD_SOURCE_URL = os.getenv("EXTERNAL_GOLD_URL", "https://www.pnj.com.vn/blog/gia-vang/")
FUEL_SOURCE_URL = os.getenv("EXTERNAL_FUEL_URL", "").strip()
AI_PRICING_URLS = {
    "ChatGPT/GPT": os.getenv("EXTERNAL_OPENAI_PRICING_URL", "https://openai.com/api/pricing/"),
    "Gemini": os.getenv("EXTERNAL_GEMINI_PRICING_URL", "https://ai.google.dev/gemini-api/docs/pricing"),
    "DeepSeek": os.getenv("EXTERNAL_DEEPSEEK_PRICING_URL", "https://api-docs.deepseek.com/quick_start/pricing"),
}
AI_STATIC_ITEMS = [
    {
        "provider": "ChatGPT/GPT",
        "note": "Theo doi trang pricing chinh thuc cua OpenAI; gia co the thay doi theo model va usage.",
        "source_url": AI_PRICING_URLS["ChatGPT/GPT"],
    },
    {
        "provider": "Gemini",
        "note": "Theo doi trang pricing chinh thuc cua Google AI; gia phu thuoc model, context va khu vuc.",
        "source_url": AI_PRICING_URLS["Gemini"],
    },
    {
        "provider": "DeepSeek",
        "note": "Theo doi trang pricing chinh thuc cua DeepSeek; gia thuong tinh theo token input/output.",
        "source_url": AI_PRICING_URLS["DeepSeek"],
    },
]


def _now() -> datetime:
    return datetime.now(DEFAULT_TIMEZONE_OFFSET)


def _date_key(now: Optional[datetime] = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=DEFAULT_TIMEZONE_OFFSET)
    return current.astimezone(DEFAULT_TIMEZONE_OFFSET).strftime("%Y-%m-%d")


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _compact_text(text: str, limit: int = 12000) -> str:
    text = unescape(text or "")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _fetch_text(url: str) -> str:
    if not url:
        raise ValueError("source_url_not_configured")
    last_error = None
    for _attempt in range(2):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.text or ""
        except Exception as exc:
            last_error = exc
    raise RuntimeError(str(last_error)[:300])


def _base_snapshot(topic: str, source: str, source_url: str, title: str, date_key: str) -> dict:
    return {
        "source": source,
        "source_url": source_url,
        "topic": topic,
        "fetched_at": firestore.SERVER_TIMESTAMP,
        "date_key": date_key,
        "title": title,
        "items": [],
        "summary": "",
        "confidence": 0,
        "raw_hash": "",
        "error": None,
    }


def _cached_or_none(topic: str, date_key: str, force_refresh: bool) -> Optional[dict]:
    if force_refresh:
        return None
    cached = get_external_snapshot(topic, date_key)
    return cached if cached else None


def _normalize_money(value: str) -> str:
    value = re.sub(r"[^\d.,]", "", value or "")
    return value.strip(".,")


def _parse_gold_items(html: str) -> list[dict]:
    text = _compact_text(html, limit=30000)
    items = []
    brands = ["SJC", "PNJ", "DOJI", "BTMC", "9999", "24K"]
    money = r"(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?)"

    for brand in brands:
        pattern = re.compile(rf"(.{{0,80}}{re.escape(brand)}.{{0,160}}?){money}.{{0,60}}?{money}", re.I)
        match = pattern.search(text)
        if not match:
            continue
        context = re.sub(r"\s+", " ", match.group(1)).strip()
        buy = _normalize_money(match.group(2))
        sell = _normalize_money(match.group(3))
        if buy and sell:
            items.append({
                "name": context[:120] or brand,
                "brand": brand,
                "buy": buy,
                "sell": sell,
                "unit": "VND/luong hoặc theo đơn vị nguồn công bố",
            })
        if len(items) >= 5:
            break
    return items


def collect_gold_price(force_refresh: bool = False) -> dict:
    date_key = _date_key()
    cached = _cached_or_none("gold", date_key, force_refresh)
    if cached:
        return cached

    snapshot = _base_snapshot("gold", "PNJ public page", GOLD_SOURCE_URL, "Gia vang", date_key)
    try:
        html = _fetch_text(GOLD_SOURCE_URL)
        items = _parse_gold_items(html)
        snapshot["raw_hash"] = _hash_text(_compact_text(html, limit=20000))
        snapshot["items"] = items
        if items:
            names = ", ".join(item.get("brand") or item.get("name", "") for item in items[:3])
            snapshot["summary"] = f"Da lay duoc bang gia vang tu nguon public ({names})."
            snapshot["confidence"] = 0.72
        else:
            snapshot["summary"] = "Chua parse duoc mua vao/ban ra tu trang gia vang public."
            snapshot["confidence"] = 0.25
            snapshot["error"] = "gold parser did not find buy/sell prices"
    except Exception as exc:
        snapshot["summary"] = "Khong lay duoc du lieu gia vang tu nguon public."
        snapshot["error"] = str(exc)[:300]
    return save_external_snapshot(snapshot)


def _parse_fuel_items(html: str) -> list[dict]:
    text = _compact_text(html, limit=30000)
    fuel_names = ["RON 95", "RON95", "E5 RON 92", "E5RON92", "Dau diesel", "Diesel", "Dau hoa", "Mazut"]
    items = []
    for name in fuel_names:
        match = re.search(rf"({re.escape(name)}.{{0,120}}?)(\d{{1,3}}(?:[.,]\d{{3}})+)", text, re.I)
        if match:
            items.append({
                "name": name,
                "price": _normalize_money(match.group(2)),
                "unit": "VND/lit hoặc theo đơn vị nguồn công bố",
            })
    period_match = re.search(r"(ky dieu chinh|kỳ điều chỉnh|ngay dieu hanh|ngày điều hành).{0,80}?(\d{1,2}[/-]\d{1,2}[/-]\d{4})", text, re.I)
    if period_match and items:
        for item in items:
            item["period"] = period_match.group(2)
    return items


def collect_fuel_price(force_refresh: bool = False) -> dict:
    date_key = _date_key()
    cached = _cached_or_none("fuel", date_key, force_refresh)
    if cached:
        return cached

    snapshot = _base_snapshot("fuel", "configured public page", FUEL_SOURCE_URL, "Gia xang dau", date_key)
    if not FUEL_SOURCE_URL:
        snapshot["summary"] = "Chua cau hinh nguon gia xang dau."
        snapshot["error"] = "fuel source not configured"
        return save_external_snapshot(snapshot)

    try:
        html = _fetch_text(FUEL_SOURCE_URL)
        items = _parse_fuel_items(html)
        snapshot["raw_hash"] = _hash_text(_compact_text(html, limit=20000))
        snapshot["items"] = items
        if items:
            snapshot["summary"] = "Da lay duoc mot so muc gia xang dau tu nguon public."
            snapshot["confidence"] = 0.65
        else:
            snapshot["summary"] = "Chua parse duoc gia xang dau tu nguon da cau hinh."
            snapshot["confidence"] = 0.2
            snapshot["error"] = "fuel parser did not find prices"
    except Exception as exc:
        snapshot["summary"] = "Khong lay duoc du lieu gia xang dau tu nguon public."
        snapshot["error"] = str(exc)[:300]
    return save_external_snapshot(snapshot)


def collect_ai_pricing(force_refresh: bool = False) -> dict:
    date_key = _date_key()
    cached = _cached_or_none("ai_pricing", date_key, force_refresh)
    if cached:
        return cached

    snapshot = _base_snapshot("ai_pricing", "official pricing pages", "", "Gia/goi AI", date_key)
    items = []
    hash_parts = []
    errors = []
    for provider, url in AI_PRICING_URLS.items():
        item = {"provider": provider, "source_url": url}
        try:
            html = _fetch_text(url)
            content_hash = _hash_text(_compact_text(html, limit=20000))
            item["raw_hash"] = content_hash
            item["status"] = "fetched"
            hash_parts.append(f"{provider}:{content_hash}")
        except Exception as exc:
            static = next((row for row in AI_STATIC_ITEMS if row["provider"] == provider), {})
            item["status"] = "static_fallback"
            item["note"] = static.get("note") or "Chua lay duoc trang pricing chinh thuc."
            item["error"] = str(exc)[:200]
            errors.append(f"{provider}: {item['error']}")
            hash_parts.append(f"{provider}:static")
        items.append(item)

    snapshot["source_url"] = ", ".join(AI_PRICING_URLS.values())
    snapshot["items"] = items
    snapshot["raw_hash"] = _hash_text("|".join(hash_parts))
    previous = find_recent_snapshot_with_hash("ai_pricing", date_key)
    if previous and previous.get("raw_hash") == snapshot["raw_hash"]:
        snapshot["summary"] = "Chua ghi nhan thay doi moi ve cac trang pricing AI dang theo doi."
    else:
        snapshot["summary"] = "Da cap nhat dau vet pricing AI tu ChatGPT/GPT, Gemini va DeepSeek."
    snapshot["confidence"] = 0.7 if not errors else 0.45
    snapshot["error"] = "; ".join(errors)[:300] if errors else None
    return save_external_snapshot(snapshot)


def collect_all_external_data(force_refresh: bool = False) -> dict:
    return {
        "gold": collect_gold_price(force_refresh=force_refresh),
        "fuel": collect_fuel_price(force_refresh=force_refresh),
        "ai_pricing": collect_ai_pricing(force_refresh=force_refresh),
    }
