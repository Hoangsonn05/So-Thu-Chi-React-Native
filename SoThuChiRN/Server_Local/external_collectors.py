import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from typing import Callable, Optional

import requests

from external_cache import (
    find_recent_snapshot,
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
]
DEFAULT_USD_URLS = [
    ("SBV", "https://sbv.gov.vn/vi/web/guest/ty-gia"),
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
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
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
        sources.append((primary_key, primary))
    backup = os.getenv(backup_key) or ""
    for idx, url in enumerate(re.split(r"[\n,|]+", backup)):
        url = url.strip()
        if url:
            sources.append((f"{backup_key}_{idx + 1}", url))
    seen = {url for _name, url in sources}
    for name, url in defaults:
        if url not in seen:
            sources.append((name, url))
    return sources


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
    cleaned = re.sub(r"[^\d.,]", "", raw)
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
    if "diesel" in normalized or "do 0.05" in normalized:
        return "Diesel DO 0.05S-II"
    if "dau hoa" in normalized or "2-k" in normalized:
        return "Dầu hỏa 2-K"
    if "mazut" in normalized:
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


def parse_fuel_items(text: str, source_name: str, source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
    by_name: dict[str, dict] = {}
    rejects = []
    for line in _html_to_lines(text):
        name = _fuel_name(line)
        if not name:
            continue
        normalized = _norm(line)
        unit = None
        if "kg" in normalized:
            unit = "VND/kg"
        elif "lit" in normalized or "lít" in line.lower() or "l/" in normalized:
            unit = "VND/lít"
        numbers = re.findall(r"\d+(?:[.,]\d+)*", line)
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
            "effective_time": source_time,
            "source_time": source_time,
        }
        ok, reason = _validate_fuel_item(item)
        if not ok:
            rejects.append(f"{name}:{reason}")
            print(f"[External Collector] reject fuel reason={reason} line={line[:120]}")
            continue
        current = by_name.get(name)
        if not current or item.get("region") == "vùng 1":
            by_name[name] = item
    items = list(by_name.values())
    print(f"[External Collector] parser=fuel items={len(items)} rejects={len(rejects)}")
    return items, rejects


def _validate_usd_rate(value: Optional[int]) -> bool:
    return value is None or 20_000 <= value <= 35_000


def parse_usd_vnd_items(text: str, source_name: str, source_time: Optional[str] = None) -> tuple[list[dict], list[str]]:
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
        "sell": sell,
        "unit": "VND/USD",
        "source_name": source_name,
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


def _collect_from_sources(topic: str, sources: list[tuple[str, str]], parser: Callable[[str, str, Optional[str]], tuple[list[dict], list[str]]], force_refresh: bool) -> dict:
    date_key = _date_key()
    cached = _cached_or_none(topic, date_key, force_refresh)
    if cached:
        return cached
    result = _base_result(topic, date_key)
    tried = []
    for source_name, source_url in sources:
        tried.append(source_url)
        result["source_name"] = source_name
        result["source"] = source_name
        result["source_url"] = source_url
        try:
            html, _status = _fetch_text(source_url)
            source_time = _source_time_from_text(html)
            items, rejects = parser(html, source_name, source_time)
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
        result["errors"].append(f"Không lấy được dữ liệu {topic} từ các nguồn: {', '.join(tried)}")
    return _save_or_fallback(_finalize_result(result), force_refresh)


def collect_gold_price(force_refresh: bool = False) -> dict:
    sources = _parse_env_urls("EXTERNAL_GOLD_URL", "EXTERNAL_GOLD_BACKUP_URLS", DEFAULT_GOLD_URLS)
    return _collect_from_sources("gold", sources, parse_gold_items, force_refresh)


def collect_fuel_price(force_refresh: bool = False) -> dict:
    sources = _parse_env_urls("EXTERNAL_FUEL_URL", "EXTERNAL_FUEL_BACKUP_URLS", DEFAULT_FUEL_URLS)
    return _collect_from_sources("fuel", sources, parse_fuel_items, force_refresh)


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
