import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Callable, Optional
from urllib.parse import urljoin

import requests

from external_cache import (
    find_recent_snapshot,
    get_latest_valid_snapshot,
    get_external_snapshot,
    is_reportable_snapshot,
    save_external_snapshot,
)


VN_TZ = timezone(timedelta(hours=7))
RAW_TEXT_LIMIT = 4000
DEFAULT_TIMEOUT_SECONDS = 10
HTTP_TIMEOUT_SECONDS = float(
    os.getenv("EXTERNAL_HTTP_TIMEOUT_SECONDS")
    or os.getenv("EXTERNAL_COLLECTOR_TIMEOUT_SECONDS")
    or DEFAULT_TIMEOUT_SECONDS
)
FORCE_REFRESH_ENV = (os.getenv("EXTERNAL_COLLECTOR_FORCE_REFRESH") or "false").strip().lower() in {"1", "true", "yes"}
USER_AGENT = os.getenv("EXTERNAL_COLLECTOR_USER_AGENT", "SoThuChiExternalBrief/1.0")

DEFAULT_GOLD_URLS = [
    ("BTMC", "https://btmc.vn/gia-vang-theo-ngay.html"),
    ("PNJ", "https://www.pnj.com.vn/site/gia-vang"),
    ("PNJ Giavang", "https://giavang.pnj.com.vn/"),
    ("Webgia", "https://webgia.com/gia-vang/"),
]
DEFAULT_FUEL_URLS = [
    ("Petrolimex", "https://www.petrolimex.com.vn/nd/gia-xang-dau.html"),
    ("Webgia Petrolimex", "https://webgia.com/gia-xang-dau/petrolimex/"),
    ("Petrolimex thông cáo", "https://www.petrolimex.com.vn/ndi/thong-cao-bao-chi.html"),
    ("Bộ Công Thương", "https://moit.gov.vn/"),
]
DEFAULT_USD_URLS = [
    ("Vietcombank", "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10"),
    ("NHNN", "https://sbv.gov.vn/vi/web/guest/ty-gia"),
    ("Vietcombank", "https://www.vietcombank.com.vn/vi-VN/KHCN/Cong-cu-Tien-ich/Ty-gia"),
]
DEFAULT_AI_URLS = {
    "OpenAI": os.getenv("EXTERNAL_OPENAI_PRICING_URL", "https://openai.com/api/pricing/"),
    "Gemini": os.getenv("EXTERNAL_GEMINI_PRICING_URL", "https://ai.google.dev/gemini-api/docs/pricing"),
    "DeepSeek": os.getenv("EXTERNAL_DEEPSEEK_PRICING_URL", "https://api-docs.deepseek.com/quick_start/pricing"),
}

STATIC_AI_PRICING = [
    {
        "provider": "OpenAI",
        "model": "gpt-4.1",
        "input_usd_per_1m": 2.0,
        "cached_input_usd_per_1m": 0.5,
        "cache_hit_usd_per_1m": None,
        "cache_miss_usd_per_1m": None,
        "output_usd_per_1m": 8.0,
        "source_name": "OpenAI static fallback",
        "source_url": DEFAULT_AI_URLS["OpenAI"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
    {
        "provider": "OpenAI",
        "model": "gpt-4.1-mini",
        "input_usd_per_1m": 0.4,
        "cached_input_usd_per_1m": 0.1,
        "cache_hit_usd_per_1m": None,
        "cache_miss_usd_per_1m": None,
        "output_usd_per_1m": 1.6,
        "source_name": "OpenAI static fallback",
        "source_url": DEFAULT_AI_URLS["OpenAI"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
    {
        "provider": "Gemini",
        "model": "gemini-2.5-flash",
        "input_usd_per_1m": 0.3,
        "cached_input_usd_per_1m": None,
        "cache_hit_usd_per_1m": None,
        "cache_miss_usd_per_1m": None,
        "output_usd_per_1m": 2.5,
        "source_name": "Gemini static fallback",
        "source_url": DEFAULT_AI_URLS["Gemini"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
    {
        "provider": "Gemini",
        "model": "gemini-2.5-pro",
        "input_usd_per_1m": 1.25,
        "cached_input_usd_per_1m": None,
        "cache_hit_usd_per_1m": None,
        "cache_miss_usd_per_1m": None,
        "output_usd_per_1m": 10.0,
        "source_name": "Gemini static fallback",
        "source_url": DEFAULT_AI_URLS["Gemini"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
    {
        "provider": "DeepSeek",
        "model": "deepseek-chat",
        "input_usd_per_1m": None,
        "cached_input_usd_per_1m": None,
        "cache_hit_usd_per_1m": 0.07,
        "cache_miss_usd_per_1m": 0.27,
        "output_usd_per_1m": 1.1,
        "source_name": "DeepSeek static fallback",
        "source_url": DEFAULT_AI_URLS["DeepSeek"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
    {
        "provider": "DeepSeek",
        "model": "deepseek-reasoner",
        "input_usd_per_1m": None,
        "cached_input_usd_per_1m": None,
        "cache_hit_usd_per_1m": 0.14,
        "cache_miss_usd_per_1m": 0.55,
        "output_usd_per_1m": 2.19,
        "source_name": "DeepSeek static fallback",
        "source_url": DEFAULT_AI_URLS["DeepSeek"],
        "source_time": None,
        "last_verified_at": "2025-06-01",
        "is_static_fallback": True,
    },
]


def _now() -> datetime:
    return datetime.now(VN_TZ)


def _date_key(now: Optional[datetime] = None) -> str:
    current = now or _now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=VN_TZ)
    return current.astimezone(VN_TZ).strftime("%Y-%m-%d")


def _hash_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _strip_accents(text: str) -> str:
    try:
        import unicodedata

        normalized = unicodedata.normalize("NFD", text or "")
        stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return stripped.replace("đ", "d").replace("Đ", "D")
    except Exception:
        return text or ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", _strip_accents(text or "").lower()).strip()


def _html_to_lines(html: str) -> list[str]:
    text = unescape(html or "")
    text = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", text)
    text = re.sub(r"(?i)</(?:tr|p|div|li|h\d|br)>", "\n", text)
    text = re.sub(r"(?i)</(?:td|th)>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return [line.strip() for line in text.split("\n") if line.strip()]


def _compact_text(html: str, limit: int = RAW_TEXT_LIMIT) -> str:
    return re.sub(r"\s+", " ", " ".join(_html_to_lines(html))).strip()[:limit]


def _parse_env_urls(primary_key: str, backup_key: str, defaults: list[tuple[str, str]]) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    primary = (os.getenv(primary_key) or "").strip()
    if primary:
        sources.append((_friendly_source_name(primary), primary))
    backup = os.getenv(backup_key) or ""
    for idx, url in enumerate(re.split(r"[\n,|]+", backup)):
        url = url.strip()
        if url:
            sources.append((_friendly_source_name(url), url))
    seen = {url for _name, url in sources}
    for name, url in defaults:
        if url not in seen:
            sources.append((name, url))
    return sources


def _friendly_source_name(url_or_name: str) -> str:
    value = url_or_name or ""
    normalized = value.lower()
    if "btmc.vn" in normalized:
        return "BTMC"
    if "giavang.pnj.com.vn" in normalized or "pnj.com.vn" in normalized:
        return "PNJ"
    if "webgia.com/gia-vang" in normalized:
        return "Webgia"
    if "petrolimex.com.vn/nd/gia-xang-dau" in normalized:
        return "Petrolimex"
    if "petrolimex.com.vn/ndi/thong-cao-bao-chi" in normalized:
        return "Petrolimex thông cáo"
    if "webgia.com/gia-xang-dau/petrolimex" in normalized:
        return "Webgia Petrolimex"
    if "moit.gov.vn" in normalized:
        return "Bộ Công Thương"
    if "sbv.gov.vn" in normalized:
        return "NHNN"
    if "vietcombank.com.vn" in normalized:
        return "Vietcombank"
    if "openai.com" in normalized:
        return "OpenAI"
    if "ai.google.dev" in normalized:
        return "Google AI/Gemini"
    if "deepseek.com" in normalized or "api-docs.deepseek.com" in normalized:
        return "DeepSeek"
    domain_match = re.search(r"https?://([^/]+)", value)
    if domain_match:
        return domain_match.group(1).replace("www.", "")
    return value if not value.startswith("EXTERNAL_") else "Nguồn cấu hình"


def _fetch_text(url: str) -> tuple[str, int]:
    print(f"[External Collector] fetching url={url}")
    last_error = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT_SECONDS)
            print(f"[External Collector] status={resp.status_code} url={url}")
            if resp.status_code == 403:
                raise PermissionError("http_403")
            resp.raise_for_status()
            return resp.text or "", resp.status_code
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                continue
    raise RuntimeError(str(last_error)[:160])


def _base_result(topic: str, date_key: str) -> dict:
    return {
        "topic": topic,
        "status": "failed",
        "source_name": "",
        "source": "",
        "source_url": "",
        "fetched_at": _now().isoformat(),
        "date_key": date_key,
        "source_time": None,
        "items": [],
        "errors": [],
        "warnings": [],
        "raw_hash": None,
        "raw_text_short": None,
        "confidence": 0.0,
        "is_valid": False,
        "has_valid_items": False,
        "summary": "",
        "error": None,
    }


def _finalize_result(result: dict) -> dict:
    result["has_valid_items"] = bool(result.get("items"))
    if result["has_valid_items"] and result.get("errors"):
        result["status"] = "partial"
    elif result["has_valid_items"]:
        result["status"] = "ok"
    else:
        result["status"] = "failed"
    result["is_valid"] = result["status"] in {"ok", "partial"} and result["has_valid_items"]
    result["error"] = "; ".join(result.get("errors") or [])[:300] or None
    return result


def _cached_or_none(topic: str, date_key: str, force_refresh: bool) -> Optional[dict]:
    if force_refresh or FORCE_REFRESH_ENV:
        return None
    cached = get_external_snapshot(topic, date_key, reportable_only=True)
    if cached:
        print(f"[External Collector] cache hit topic={topic} date={date_key}")
        return cached
    print(f"[External Collector] cache miss topic={topic} date={date_key}")
    return None


def _save_or_fallback(result: dict, force_refresh: bool) -> dict:
    if result.get("has_valid_items"):
        return save_external_snapshot(result)
    if force_refresh or FORCE_REFRESH_ENV:
        previous = find_recent_snapshot(result["topic"], result["date_key"], reportable_only=True)
        if previous:
            previous = dict(previous)
            previous.setdefault("warnings", [])
            previous["warnings"] = list(previous.get("warnings") or []) + ["Dùng cache gần nhất vì nguồn mới lỗi."]
            return previous
    return save_external_snapshot(result)


def _to_int_vnd(value: str) -> Optional[int]:
    raw = (value or "").strip()
    if not raw:
        return None
    cleaned = re.sub(r"[^\d.,\s]", "", raw)
    cleaned = re.sub(r"(?<=\d)\s+(?=\d)", "", cleaned)
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "." in cleaned:
        parts = cleaned.split(".")
        if len(parts[-1]) == 3:
            cleaned = "".join(parts)
        else:
            cleaned = ".".join(parts)
    elif "," in cleaned:
        parts = cleaned.split(",")
        if len(parts[-1]) == 3:
            cleaned = "".join(parts)
        else:
            cleaned = ".".join(parts)
    try:
        numeric = float(cleaned)
    except Exception:
        return None
    return int(round(numeric))


def _to_float_usd(value: str) -> Optional[float]:
    match = re.search(r"(\d+(?:[.,]\d+)?)", value or "")
    if not match:
        return None
    return float(match.group(1).replace(",", "."))


def _line_has_unit(line: str, unit_words: list[str]) -> bool:
    normalized = _norm(line)
    return any(word in normalized for word in unit_words)


def _gold_value_to_per_chi(value: str, context: str) -> Optional[int]:
    normalized = _norm(context)
    raw = _to_int_vnd(value)
    usd_float = _to_float_usd(value)
    if raw is None:
        return None
    has_thousand_unit = "1 = 1.000" in context or "1=1.000" in context or "1000 vnd" in normalized or "1.000 vnd" in normalized
    has_million_per_luong = "trieu" in normalized and ("luong" in normalized or "cay" in normalized)
    has_per_luong = "luong" in normalized or "cay" in normalized
    has_per_chi = "chi" in normalized
    if has_thousand_unit and 1000 <= raw <= 30000:
        return raw * 1000
    if has_million_per_luong and usd_float is not None:
        return int(round(usd_float * 1_000_000 / 10))
    if has_per_luong and 10_000_000 <= raw <= 300_000_000:
        return int(round(raw / 10))
    if has_per_chi and 1_000_000 <= raw <= 30_000_000:
        return raw
    if has_thousand_unit and 1_000_000 <= raw <= 30_000_000:
        return raw
    return None


def _canonical_gold_name(line: str) -> Optional[str]:
    normalized = _norm(line)
    if "sjc" in normalized:
        return "SJC 9999"
    if "nhan" in normalized and "9999" in normalized:
        return "Nhẫn tròn trơn 9999"
    if "9999" in normalized or "24k" in normalized:
        return "Vàng 9999"
    return None


def _validate_gold_item(item: dict) -> tuple[bool, str]:
    buy = item.get("buy_per_chi")
    sell = item.get("sell_per_chi")
    if not isinstance(buy, int) or not isinstance(sell, int):
        return False, "missing_buy_or_sell"
    if not (1_000_000 <= buy <= 30_000_000):
        return False, f"invalid_gold_buy:{buy}"
    if not (1_000_000 <= sell <= 30_000_000):
        return False, f"invalid_gold_sell:{sell}"
    if sell < buy:
        return False, "gold_sell_less_than_buy"
    return True, ""


def _select_gold_buy_sell(values: list[int]) -> tuple[Optional[int], Optional[int]]:
    valid = sorted({value for value in values if 1_000_000 <= value <= 30_000_000})
    candidates = []
    for idx, buy in enumerate(valid):
        for sell in valid[idx:]:
            if sell >= buy:
                candidates.append((buy, sell, sell - buy))
    if not candidates:
        return None, None
    non_zero = [item for item in candidates if item[2] > 0]
    candidates = non_zero or candidates
    plausible = [item for item in candidates if item[2] <= 5_000_000]
    candidates = plausible or candidates
    # Prefer the highest plausible buy/sell pair to avoid product codes like 9999 or unit markers.
    buy, sell, _spread = max(candidates, key=lambda item: (item[0], item[1]))
    return buy, sell


def parse_gold_items(text: str, source_name: str, source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
    items = []
    rejects = []
    for line in _html_to_lines(text):
        name = _canonical_gold_name(line)
        if not name:
            continue
        if not _line_has_unit(line, ["chi", "luong", "cay", "1.000 vnd", "1000 vnd"]):
            rejects.append(f"{name}:missing_unit")
            continue
            unit = "VND/lÃ­t"
        numbers = re.findall(r"\d+(?:[.,]\d+)*", line)
        values = [_gold_value_to_per_chi(num, line) for num in numbers]
        values = [value for value in values if value is not None]
        if len(values) < 2:
            rejects.append(f"{name}:missing_buy_sell")
            continue
        buy, sell = _select_gold_buy_sell(values)
        if buy is None or sell is None:
            rejects.append(f"{name}:missing_buy_sell")
            continue
        item = {
            "item_key": f"gold.{re.sub(r'[^A-Za-z0-9]+', '_', _strip_accents(name)).strip('_')}.sell_per_chi",
            "name": name,
            "buy_per_chi": buy,
            "sell_per_chi": sell,
            "buy_per_luong": buy * 10,
            "sell_per_luong": sell * 10,
            "spread_per_chi": sell - buy,
            "unit": "VND/chỉ",
            "source_name": source_name,
            "source_time": source_time,
        }
        ok, reason = _validate_gold_item(item)
        if ok:
            if item["name"] not in {existing["name"] for existing in items}:
                items.append(item)
        else:
            rejects.append(f"{name}:{reason}")
    print(f"[External Collector] parser=gold items={len(items)} rejects={len(rejects)}")
    return items, rejects


def _fuel_name(line: str) -> Optional[str]:
    normalized = _norm(line)
    if "ron95" in normalized or "ron 95" in normalized:
        return "RON95-III"
    if "e5" in normalized and ("ron92" in normalized or "ron 92" in normalized):
        return "E5 RON92-II"
    if "diesel" in normalized or "do 0.05" in normalized or "do 0,05" in normalized:
        return "Diesel DO 0.05S"
    if "dau hoa" in normalized or "2-k" in normalized or re.search(r"\bko\b", normalized):
        return "Dầu hỏa 2-K"
    if "mazut" in normalized or re.search(r"\bfo\b", normalized):
        return "Mazut"
    return None


def _fuel_region(line: str) -> Optional[str]:
    normalized = _norm(line)
    if "vung 1" in normalized or "vung i" in normalized:
        return "vùng 1"
    if "vung 2" in normalized or "vung ii" in normalized:
        return "vùng 2"
    return None


def _validate_fuel_item(item: dict) -> tuple[bool, str]:
    price = item.get("price")
    unit = item.get("unit")
    name = _norm(item.get("name", ""))
    if isinstance(unit, str) and unit.startswith("VND/l"):
        unit = "VND/lÃ­t"
        item["unit"] = unit
        unit = "VND/lít"
        item["unit"] = unit
    if not isinstance(price, int):
        return False, "missing_price"
    if unit not in {"VND/lít", "VND/kg"}:
        return False, "missing_unit"
    if "mazut" in name:
        if unit != "VND/kg" or not (5_000 <= price <= 40_000):
            return False, f"invalid_mazut_price:{price}"
    elif not (10_000 <= price <= 50_000):
        return False, f"invalid_fuel_price:{price}"
    return True, ""


def _extract_effective_time(text: str) -> Optional[str]:
    for pattern in [
        r"(?:từ|tu)\s*(\d{1,2})\s*giờ(?:\s*(\d{1,2})\s*phút)?\s*ngày\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})",
        r"(\d{1,2}):(\d{2})\s*ngày\s*(\d{1,2})[./-](\d{1,2})[./-](\d{4})",
    ]:
        match = re.search(pattern, text or "", re.I)
        if match:
            hour, minute, day, month, year = match.groups()
            return f"{int(hour):02d}:{int(minute or 0):02d} {int(day):02d}/{int(month):02d}/{year}"
    match = re.search(r"kể từ\s*(\d{1,2})\s*giờ(?:\s*(\d{1,2})\s*phút)?", text or "", re.I)
    if match:
        return f"{int(match.group(1)):02d}:{int(match.group(2) or 0):02d}"
    return None


def parse_fuel_items(text: str, source_name: str, source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
    by_name: dict[str, dict] = {}
    rejects = []
    lines = _html_to_lines(text)
    global_context = _norm(" ".join(lines))
    has_global_liter_unit = any(token in global_context for token in ["dong/lit", "vnd/lit", "dong/l", "vnd/l"])
    has_global_kg_unit = any(token in global_context for token in ["dong/kg", "vnd/kg"])
    for line in lines:
        name = _fuel_name(line)
        if not name:
            continue
        normalized = _norm(line)
        unit = None
        if "kg" in normalized:
            unit = "VND/kg"
        elif "lit" in normalized or "lít" in line.lower() or "l/" in normalized:
            unit = "VND/lít"
        if not unit and name == "Mazut" and has_global_kg_unit:
            unit = "VND/kg"
        elif not unit and has_global_liter_unit:
            unit = "VND/lÃ­t"
        price_line = re.sub(r"(?i)(vÃ¹ng|vùng|vung)\s*\d+", " ", line)
        numbers = re.findall(r"\d{1,3}(?:[.,\s]\d{3})+|\d{5}", price_line)
        prices = [_to_int_vnd(num) for num in numbers]
        prices = [price for price in prices if price is not None]
        if not unit or not prices:
            rejects.append(f"{name}:missing_unit_or_price")
            continue
        price = prices[-1]
        item = {
            "item_key": f"fuel.{name.replace(' ', '_')}.{(_fuel_region(line) or 'region_null').replace(' ', '_')}.price",
            "name": name,
            "region": _fuel_region(line),
            "price": price,
            "unit": unit,
            "source_name": source_name,
            "source_url": "",
            "effective_time": source_time,
            "source_time": source_time,
        }
        ok, reason = _validate_fuel_item(item)
        if not ok:
            rejects.append(f"{name}:{reason}")
            print(f"[External Collector] reject fuel reason={reason} line={_strip_accents(line)[:120]}")
            continue
        current = by_name.get(name)
        if not current or item.get("region") == "vùng 1":
            by_name[name] = item
    items = list(by_name.values())
    print(f"[External Collector] parser=fuel items={len(items)} rejects={len(rejects)}")
    return items, rejects


def parse_petrolimex_fuel_article(html: str, source_url: str) -> dict:
    effective_time = _extract_effective_time(_compact_text(html, RAW_TEXT_LIMIT * 2)) or _source_time_from_text(html)
    items, rejects = parse_fuel_items(html, "Petrolimex", effective_time)
    for item in items:
        item["source_url"] = source_url
        item["source_name"] = "Petrolimex"
        item["effective_time"] = effective_time
        item["source_time"] = effective_time
    compact = _compact_text(html, RAW_TEXT_LIMIT)
    return {
        "source_name": "Petrolimex",
        "source_url": source_url,
        "effective_time": effective_time,
        "source_time": effective_time,
        "items": items,
        "errors": [] if items else ["petrolimex_article_no_valid_items"],
        "warnings": rejects,
        "content_hash": _hash_text(compact),
        "raw_hash": _hash_text(compact),
        "raw_text_short": compact,
    }


def _validate_usd_rate(value: Optional[int]) -> bool:
    return value is None or 20_000 <= value <= 35_000


def parse_usd_vnd_items(text: str, source_name: str, source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
    xml_match = re.search(r"<Exrate\b[^>]*(?:CurrencyCode|CurrencyName)=[\"'][^\"']*(?:USD|US DOLLAR)[^\"']*[\"'][^>]*/?>", text or "", re.I)
    if xml_match:
        tag = xml_match.group(0)
        attrs = dict(re.findall(r"(\w+)=[\"']([^\"']*)[\"']", tag))
        buy = _to_int_vnd(attrs.get("Buy", ""))
        transfer = _to_int_vnd(attrs.get("Transfer", ""))
        sell = _to_int_vnd(attrs.get("Sell", ""))
        rejects = []
        for label, value in [("buy", buy), ("transfer", transfer), ("sell", sell)]:
            if value is not None and not _validate_usd_rate(value):
                rejects.append(f"{label}_invalid:{value}")
        if buy and sell and sell < buy:
            rejects.append("usd_sell_less_than_buy")
        if rejects or not any([buy, transfer, sell]):
            return [], rejects or ["usd_rate_not_found"]
        xml_time = source_time or attrs.get("DateTime") or attrs.get("Date") or attrs.get("Time")
        return [{
            "item_key": "usd_vnd.vietcombank.usd",
            "central_rate": None,
            "buy": buy,
            "transfer": transfer,
            "sell": sell,
            "unit": "VND/USD",
            "source_name": "Vietcombank",
            "source_url": "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx?b=10",
            "source_time": xml_time,
        }], []

    lines = _html_to_lines(text)
    central_rate = None
    buy = None
    sell = None
    rejects = []
    for line in lines:
        normalized = _norm(line)
        values = [_to_int_vnd(num) for num in re.findall(r"\d{1,3}(?:[.,]\d{3})+|\d{5}", line)]
        values = [value for value in values if value is not None]
        if not values:
            continue
        if "trung tam" in normalized or "central" in normalized:
            central_rate = values[-1]
        if "usd" in normalized and ("mua" in normalized or "buy" in normalized or "ban" in normalized or "sell" in normalized):
            valid_values = [value for value in values if 20_000 <= value <= 35_000]
            if len(valid_values) >= 2:
                buy = valid_values[0]
                sell = valid_values[-1]
            elif len(valid_values) == 1 and ("ban" in normalized or "sell" in normalized):
                sell = valid_values[0]
            elif len(valid_values) == 1:
                buy = valid_values[0]
    if not _validate_usd_rate(central_rate):
        rejects.append(f"central_rate_invalid:{central_rate}")
        central_rate = None
    if not _validate_usd_rate(buy):
        rejects.append(f"buy_invalid:{buy}")
        buy = None
    if not _validate_usd_rate(sell):
        rejects.append(f"sell_invalid:{sell}")
        sell = None
    if buy and sell and sell < buy:
        rejects.append("usd_sell_less_than_buy")
        buy = None
        sell = None
    if not any([central_rate, buy, sell]):
        return [], rejects or ["usd_rate_not_found"]
    item = {
        "item_key": "usd_vnd.central_rate",
        "central_rate": central_rate,
        "buy": buy,
        "transfer": None,
        "sell": sell,
        "unit": "VND/USD",
        "source_name": source_name,
        "source_url": "",
        "source_time": source_time,
    }
    print("[External Collector] parser=usd_vnd items=1 rejects=%s" % len(rejects))
    return [item], rejects


def _provider_from_source(source_name: str) -> str:
    normalized = _norm(source_name)
    if "openai" in normalized:
        return "OpenAI"
    if "gemini" in normalized or "google" in normalized:
        return "Gemini"
    if "deepseek" in normalized:
        return "DeepSeek"
    return source_name


def parse_ai_pricing_items(text: str, source_name: str, source_url: str = "", source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
    provider = _provider_from_source(source_name)
    items = []
    rejects = []
    for line in _html_to_lines(text):
        normalized = _norm(line)
        if provider == "OpenAI":
            model_match = re.search(r"\b(gpt-[a-z0-9.\-]+)\b", normalized)
        elif provider == "Gemini":
            model_match = re.search(r"\b(gemini-[a-z0-9.\-]+)\b", normalized)
        else:
            model_match = re.search(r"\b(deepseek-[a-z0-9.\-]+)\b", normalized)
        if not model_match:
            continue
        model = model_match.group(1)
        price_line = re.sub(re.escape(model), " ", line, flags=re.I)
        money_values = [float(value.replace(",", ".")) for value in re.findall(r"\$\s*(\d+(?:[.,]\d+)?)", price_line)]
        if len(money_values) < 2:
            money_values = [
                float(value.replace(",", "."))
                for value in re.findall(r"(?:input|cache hit|cache miss|cached|output)[^0-9$]{0,20}\$?\s*(\d+(?:[.,]\d+)?)", price_line, re.I)
            ]
        if len(money_values) < 2:
            rejects.append(f"{provider}.{model}:missing_input_output")
            continue
        lower = normalized
        cache_hit = None
        cache_miss = None
        cached_input = None
        input_price = money_values[0]
        output_price = money_values[-1]
        if "cache hit" in lower or "cached" in lower:
            cached_input = money_values[1] if len(money_values) > 2 else None
        if "cache hit" in lower and "cache miss" in lower and len(money_values) >= 3:
            cache_hit = money_values[0]
            cache_miss = money_values[1]
            input_price = None
            output_price = money_values[-1]
        item = {
            "item_key": f"ai_pricing.{provider}.{model}.output_usd_per_1m",
            "provider": provider,
            "model": model,
            "input_usd_per_1m": input_price,
            "cached_input_usd_per_1m": cached_input,
            "cache_hit_usd_per_1m": cache_hit,
            "cache_miss_usd_per_1m": cache_miss,
            "output_usd_per_1m": output_price,
            "source_name": source_name,
            "source_url": source_url,
            "source_time": source_time,
            "is_static_fallback": False,
        }
        if item["output_usd_per_1m"] is None or (
            item["input_usd_per_1m"] is None and item["cache_miss_usd_per_1m"] is None
        ):
            rejects.append(f"{provider}.{model}:missing_required_prices")
            continue
        items.append(item)
    print(f"[External Collector] parser=ai_pricing provider={provider} items={len(items)} rejects={len(rejects)}")
    return items, rejects


def _source_time_from_text(text: str) -> Optional[str]:
    match = re.search(r"(\d{1,2}[/-]\d{1,2}[/-]\d{4}(?:\s+\d{1,2}:\d{2})?)", text or "")
    return match.group(1) if match else None


def _parse_article_date(text: str) -> Optional[datetime]:
    match = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})", text or "")
    if not match:
        return None
    day, month, year = match.groups()
    try:
        return datetime(int(year), int(month), int(day), tzinfo=VN_TZ)
    except Exception:
        return None


def _fuel_article_score(title: str) -> int:
    normalized = _norm(title)
    strong_keywords = ["dieu chinh gia xang dau", "gia xang dau", "xang dau tu", "ron95", "e5 ron92", "diesel"]
    excludes = ["nhan su", "hoi nghi", "co dong", "moi truong", "hang khong", "canh bao lua dao", "tuyen dung"]
    if any(word in normalized for word in excludes):
        return -100
    score = 0
    for idx, keyword in enumerate(strong_keywords):
        if keyword in normalized:
            score += 20 - idx
    return score


def discover_latest_petrolimex_fuel_article(list_url: str = "https://www.petrolimex.com.vn/nd/gia-xang-dau.html") -> Optional[dict]:
    html, _status = _fetch_text(list_url)
    link_pattern = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", re.I | re.S)
    links = []
    for href, raw_title in link_pattern.findall(html or ""):
        title = re.sub(r"\s+", " ", re.sub(r"(?is)<[^>]+>", " ", unescape(raw_title))).strip()
        if not title:
            continue
        links.append({"title": title, "url": urljoin(list_url, href), "published_dt": _parse_article_date(title)})
    candidates = []
    for link in links:
        score = _fuel_article_score(link["title"])
        if score <= 0:
            continue
        candidates.append({**link, "score": score})
    print(f"[External Collector] petrolimex discovery links={len(links)} candidates={len(candidates)}")
    if not candidates:
        return None
    dated = [candidate for candidate in candidates if candidate.get("published_dt")]
    selected = max(dated, key=lambda item: (item["published_dt"], item["score"])) if dated else max(candidates, key=lambda item: item["score"])
    published = selected["published_dt"].strftime("%d/%m/%Y") if selected.get("published_dt") else None
    safe_title = _strip_accents(selected["title"]).encode("ascii", errors="ignore").decode("ascii")[:100]
    print(f"[External Collector] selected fuel article title={safe_title} url={selected['url']}")
    return {
        "title": selected["title"],
        "url": selected["url"],
        "published_date": published,
        "source_name": "Petrolimex",
        "source_url": list_url,
    }


def _collect_from_sources(topic: str, sources: list[tuple[str, str]], parser: Callable[[str, str, Optional[str]], tuple[list[dict], list[str]]], force_refresh: bool) -> dict:
    date_key = _date_key()
    cached = _cached_or_none(topic, date_key, force_refresh)
    if cached:
        return cached
    result = _base_result(topic, date_key)
    tried = []
    tried_names = []
    for source_name, source_url in sources:
        source_name = _friendly_source_name(source_url) or source_name
        tried.append(source_url)
        tried_names.append(source_name)
        result["source_name"] = source_name
        result["source"] = source_name
        result["source_url"] = source_url
        try:
            html, _status = _fetch_text(source_url)
            source_time = _source_time_from_text(html)
            items, rejects = parser(html, source_name, source_time)
            for item in items:
                item.setdefault("source_url", source_url)
                item["source_name"] = item.get("source_name") or source_name
            result["raw_hash"] = _hash_text(_compact_text(html, RAW_TEXT_LIMIT))
            result["raw_text_short"] = _compact_text(html, RAW_TEXT_LIMIT)
            result["source_time"] = source_time
            result["warnings"].extend(rejects[:12])
            if items:
                result["items"] = items
                result["confidence"] = 0.75 if not rejects else 0.6
                break
            result["errors"].append(f"{source_name}:no_valid_items")
            print(f"[External Collector] fallback topic={topic} from={source_name} reason=no_valid_items")
        except Exception as exc:
            detail = str(exc)[:120]
            result["errors"].append(f"{source_name}:{detail}")
            print(f"[External Collector] fallback topic={topic} from={source_name} reason={detail}")
    if not result["items"]:
        result["errors"].append(f"Không lấy được dữ liệu {topic} từ các nguồn: {', '.join(tried_names)}")
    result["tried_sources"] = list(dict.fromkeys(tried_names))
    return _save_or_fallback(_finalize_result(result), force_refresh)


def collect_gold_price(force_refresh: bool = False) -> dict:
    sources = _parse_env_urls("EXTERNAL_GOLD_URL", "EXTERNAL_GOLD_BACKUP_URLS", DEFAULT_GOLD_URLS)
    return _collect_from_sources("gold", sources, parse_gold_items, force_refresh)


def collect_fuel_price(force_refresh: bool = False) -> dict:
    date_key = _date_key()
    cached_today = _cached_or_none("fuel", date_key, force_refresh)
    if cached_today:
        print(f"[External Collector] fuel cache hit today date={date_key}")
        return cached_today

    configured_fuel_url = (os.getenv("EXTERNAL_FUEL_URL") or "").strip()
    if configured_fuel_url and "petrolimex.com.vn/nd/gia-xang-dau" not in configured_fuel_url:
        direct_result = _collect_from_sources(
            "fuel",
            [(_friendly_source_name(configured_fuel_url), configured_fuel_url)],
            parse_fuel_items,
            force_refresh=True,
        )
        if is_reportable_snapshot(direct_result):
            return direct_result
        print(f"[External Collector] configured fuel url failed, fallback to Petrolimex list url={configured_fuel_url}")

    list_url = configured_fuel_url or "https://www.petrolimex.com.vn/nd/gia-xang-dau.html"
    if "petrolimex.com.vn/nd/gia-xang-dau" not in list_url:
        list_url = "https://www.petrolimex.com.vn/nd/gia-xang-dau.html"

    result = _base_result("fuel", date_key)
    latest_snapshot = get_latest_valid_snapshot("fuel", before_date_key=date_key, max_days=60)
    if latest_snapshot:
        print(f"[External Collector] latest fuel snapshot article={latest_snapshot.get('discovered_article_url')}")

    try:
        article = discover_latest_petrolimex_fuel_article(list_url)
        if article:
            result["discovered_article_title"] = article.get("title")
            result["discovered_article_url"] = article.get("url")
            result["discovered_article_published_date"] = article.get("published_date")
            result["discovery_hash"] = _hash_text(f"{article.get('title')}|{article.get('url')}")
            result["last_discovered_at"] = _now().isoformat()
            if (
                latest_snapshot
                and latest_snapshot.get("discovered_article_url") == article.get("url")
                and not force_refresh
            ):
                copied = dict(latest_snapshot)
                copied.update({
                    "date_key": date_key,
                    "used_cached_article": True,
                    "warnings": list(copied.get("warnings") or []) + [
                        "Bài điều chỉnh giá xăng dầu chưa thay đổi, dùng dữ liệu snapshot gần nhất."
                    ],
                    "last_discovered_at": _now().isoformat(),
                })
                print("[External Collector] same fuel article detected; copied latest snapshot to today")
                return save_external_snapshot(_finalize_result(copied))

            print(f"[External Collector] fetch fuel detail url={article.get('url')}")
            html, _status = _fetch_text(article["url"])
            parsed = parse_petrolimex_fuel_article(html, article["url"])
            result.update(parsed)
            result.update({
                "source_name": "Petrolimex",
                "source": "Petrolimex",
                "source_url": article["url"],
                "discovered_article_title": article.get("title"),
                "discovered_article_url": article.get("url"),
                "discovered_article_published_date": article.get("published_date"),
                "last_parsed_at": _now().isoformat(),
                "used_cached_article": False,
                "tried_sources": ["Petrolimex"],
                "confidence": 0.8,
            })
            if result.get("items"):
                print(f"[External Collector] parsed fuel detail items={len(result['items'])}")
                return save_external_snapshot(_finalize_result(result))
            print("[External Collector] fallback fuel reason=petrolimex_detail_no_valid_items")
        else:
            result["errors"].append("Petrolimex:no_article_candidate")
            print("[External Collector] fallback fuel reason=no_petrolimex_article_candidate")
    except Exception as exc:
        detail = str(exc)[:160]
        result["errors"].append(f"Petrolimex:{detail}")
        print(f"[External Collector] fallback fuel reason={detail}")

    webgia_sources = [("Webgia Petrolimex", "https://webgia.com/gia-xang-dau/petrolimex/")]
    webgia_result = _collect_from_sources("fuel", webgia_sources, parse_fuel_items, force_refresh=True)
    if is_reportable_snapshot(webgia_result):
        webgia_result["status"] = "partial"
        return save_external_snapshot(webgia_result)

    if latest_snapshot:
        fallback = dict(latest_snapshot)
        fallback.update({
            "date_key": date_key,
            "used_cached_article": True,
            "warnings": list(fallback.get("warnings") or []) + ["Nguồn hiện tại lỗi, dùng dữ liệu cache gần nhất."],
        })
        try:
            latest_date = datetime.strptime(str(latest_snapshot.get("date_key")), "%Y-%m-%d").replace(tzinfo=VN_TZ)
            if (_now() - latest_date).days > 30:
                fallback["warnings"].append("Dữ liệu cache đã cũ hơn 30 ngày.")
        except Exception:
            pass
        print("[External Collector] fallback fuel cache latest valid snapshot")
        return save_external_snapshot(_finalize_result(fallback))

    result["tried_sources"] = ["Petrolimex", "Webgia Petrolimex"]
    result["errors"].append("Không lấy được dữ liệu fuel từ các nguồn: Petrolimex, Webgia Petrolimex")
    return save_external_snapshot(_finalize_result(result))


def collect_usd_vnd_rate(force_refresh: bool = False) -> dict:
    sources = _parse_env_urls("EXTERNAL_USD_RATE_URL", "EXTERNAL_USD_RATE_BACKUP_URLS", DEFAULT_USD_URLS)
    return _collect_from_sources("usd_vnd", sources, parse_usd_vnd_items, force_refresh)


def _ai_sources() -> list[tuple[str, str]]:
    return [(provider, url) for provider, url in DEFAULT_AI_URLS.items() if url]


def _static_ai_result(date_key: str, errors: list[str], warnings: Optional[list[str]] = None) -> dict:
    result = _base_result("ai_pricing", date_key)
    result.update({
        "source_name": "Static AI pricing fallback",
        "source": "Static AI pricing fallback",
        "source_url": ", ".join(DEFAULT_AI_URLS.values()),
        "items": [dict(item) for item in STATIC_AI_PRICING],
        "warnings": (warnings or []) + ["Nguồn: static fallback từ cấu hình, cần xác minh lại."],
        "errors": errors,
        "raw_hash": _hash_text(str(STATIC_AI_PRICING)),
        "raw_text_short": "static_ai_pricing_fallback",
        "confidence": 0.45,
    })
    return _finalize_result(result)


def collect_ai_pricing(force_refresh: bool = False) -> dict:
    date_key = _date_key()
    cached = _cached_or_none("ai_pricing", date_key, force_refresh)
    if cached:
        return cached

    result = _base_result("ai_pricing", date_key)
    all_items = []
    errors = []
    warnings = []
    hash_parts = []
    for source_name, source_url in _ai_sources():
        try:
            html, _status = _fetch_text(source_url)
            source_time = _source_time_from_text(html)
            items, rejects = parse_ai_pricing_items(html, source_name, source_url, source_time)
            warnings.extend(rejects[:8])
            hash_parts.append(_hash_text(_compact_text(html, RAW_TEXT_LIMIT)))
            all_items.extend(items)
            if not items:
                errors.append(f"{source_name}:no_valid_model_prices")
        except Exception as exc:
            detail = str(exc)[:120]
            if "403" in detail or "http_403" in detail:
                print(f"[External Collector] AI source forbidden provider={source_name}")
                errors.append(f"{source_name}:forbidden")
            else:
                errors.append(f"{source_name}:{detail}")
            print(f"[External Collector] fallback topic=ai_pricing from={source_name} reason={detail}")

    if not all_items:
        previous = find_recent_snapshot("ai_pricing", date_key, reportable_only=True)
        if previous and is_reportable_snapshot(previous):
            previous = dict(previous)
            previous["warnings"] = list(previous.get("warnings") or []) + ["Dùng cache gần nhất vì live pricing lỗi."]
            return previous
        return save_external_snapshot(_static_ai_result(date_key, errors, warnings))

    result.update({
        "source_name": "Official AI pricing pages",
        "source": "Official AI pricing pages",
        "source_url": ", ".join(DEFAULT_AI_URLS.values()),
        "items": all_items,
        "errors": errors,
        "warnings": warnings,
        "raw_hash": _hash_text("|".join(hash_parts)),
        "raw_text_short": "official_ai_pricing_pages",
        "confidence": 0.75 if not errors else 0.6,
    })
    return _save_or_fallback(_finalize_result(result), force_refresh)


def collect_all_external_data(force_refresh: bool = False) -> dict:
    return {
        "gold": collect_gold_price(force_refresh=force_refresh),
        "fuel": collect_fuel_price(force_refresh=force_refresh),
        "usd_vnd": collect_usd_vnd_rate(force_refresh=force_refresh),
        "ai_pricing": collect_ai_pricing(force_refresh=force_refresh),
    }
