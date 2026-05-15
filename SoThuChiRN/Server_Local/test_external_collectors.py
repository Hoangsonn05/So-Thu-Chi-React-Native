import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import external_collectors as collectors
from external_brief import format_external_brief


def _no_cache(*_args, **_kwargs):
    return {}


def _save_passthrough(snapshot):
    return snapshot


class ExternalCollectorParserTests(unittest.TestCase):
    def setUp(self):
        self.patches = [
            patch("external_collectors.get_external_snapshot", side_effect=_no_cache),
            patch("external_collectors.find_recent_snapshot", return_value=None),
            patch("external_collectors.save_external_snapshot", side_effect=_save_passthrough),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()

    def test_btmc_thousand_unit_gold(self):
        html = """
        <tr><td>SJC 9999</td><td>Mua 16100</td><td>Bán 16200</td><td>Đơn vị: 1 = 1.000 VND/chỉ</td></tr>
        """
        items, rejects = collectors.parse_gold_items(html, "BTMC")
        self.assertFalse(rejects)
        self.assertEqual(items[0]["buy_per_chi"], 16_100_000)
        self.assertEqual(items[0]["sell_per_chi"], 16_200_000)

    def test_gold_per_luong_conversion(self):
        html = "<div>Nhẫn tròn trơn 9999 mua 125.5 bán 126.5 triệu đồng/lượng</div>"
        items, _rejects = collectors.parse_gold_items(html, "PNJ")
        self.assertEqual(items[0]["buy_per_chi"], 12_550_000)
        self.assertEqual(items[0]["sell_per_chi"], 12_650_000)
        self.assertEqual(items[0]["buy_per_luong"], 125_500_000)

    def test_fuel_ron95_valid(self):
        html = "<tr><td>RON95-III vùng 1</td><td>24350 VND/lít</td></tr>"
        items, rejects = collectors.parse_fuel_items(html, "Petrolimex")
        self.assertFalse(rejects)
        self.assertEqual(items[0]["price"], 24_350)
        self.assertEqual(items[0]["unit"], "VND/lít")

    def test_fuel_ron95_5202_rejected(self):
        html = "<tr><td>RON95-III vùng 1</td><td>5.202 VND/lít</td></tr>"
        items, rejects = collectors.parse_fuel_items(html, "Petrolimex")
        self.assertEqual(items, [])
        self.assertTrue(any("invalid_fuel_price" in item for item in rejects))

    def test_usd_rate_valid(self):
        html = "<p>Tỷ giá trung tâm: 25.000 VND/USD</p>"
        items, rejects = collectors.parse_usd_vnd_items(html, "SBV")
        self.assertFalse(rejects)
        self.assertEqual(items[0]["central_rate"], 25_000)

    def test_usd_rate_invalid(self):
        html = "<p>Tỷ giá trung tâm: 5.000 VND/USD</p>"
        items, rejects = collectors.parse_usd_vnd_items(html, "SBV")
        self.assertEqual(items, [])
        self.assertTrue(any("central_rate_invalid" in item for item in rejects))

    def test_ai_pricing_extracts_input_output(self):
        html = """
        <div>gpt-4.1 input $2.00 / 1M tokens cached $0.50 / 1M tokens output $8.00 / 1M tokens</div>
        <div>gpt-4.1-mini input $0.40 / 1M tokens output $1.60 / 1M tokens</div>
        """
        items, rejects = collectors.parse_ai_pricing_items(html, "OpenAI", "https://openai.com/api/pricing/")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["input_usd_per_1m"], 2.0)
        self.assertEqual(items[0]["cached_input_usd_per_1m"], 0.5)
        self.assertEqual(items[0]["output_usd_per_1m"], 8.0)
        self.assertFalse(rejects)

    def test_ai_403_static_fallback(self):
        with patch("external_collectors._fetch_text", side_effect=RuntimeError("http_403")):
            result = collectors.collect_ai_pricing(force_refresh=True)
        self.assertTrue(result["has_valid_items"])
        self.assertTrue(any(item.get("is_static_fallback") for item in result["items"]))
        self.assertNotIn("403", format_external_brief("ai_price_brief", {"ai_pricing": result}))

    def test_primary_source_failure_tries_backup(self):
        calls = []

        def fake_fetch(url):
            calls.append(url)
            if len(calls) == 1:
                raise RuntimeError("primary failed")
            return "<tr><td>RON95-III vùng 1</td><td>24350 VND/lít</td></tr>", 200

        with patch("external_collectors._fetch_text", side_effect=fake_fetch):
            with patch("external_collectors._parse_env_urls", return_value=[("Primary", "https://a"), ("Backup", "https://b")]):
                result = collectors.collect_fuel_price(force_refresh=True)
        self.assertEqual(len(calls), 2)
        self.assertTrue(result["has_valid_items"])
        self.assertEqual(result["items"][0]["price"], 24_350)

    def test_one_failed_group_still_formats_remaining_sections(self):
        snapshots = {
            "gold": {
                "topic": "gold",
                "status": "failed",
                "has_valid_items": False,
                "is_valid": False,
                "source_url": "https://gold.example",
                "errors": ["gold failed"],
            },
            "usd_vnd": {
                "topic": "usd_vnd",
                "status": "ok",
                "has_valid_items": True,
                "is_valid": True,
                "source_name": "SBV",
                "items": [{"central_rate": 25_000, "buy": None, "sell": None, "unit": "VND/USD", "source_name": "SBV"}],
            },
        }
        report = format_external_brief("morning_external_brief", snapshots, datetime(2026, 5, 15, 7, 0, tzinfo=timezone.utc))
        self.assertIn("Không lấy được dữ liệu giá vàng", report)
        self.assertIn("25.000 VND/USD", report)
        self.assertTrue(report.endswith("Dữ liệu chỉ để tham khảo, không phải khuyến nghị tài chính."))

    def test_existing_external_task_types_unchanged(self):
        from agentic_ai import EXTERNAL_BRIEF_TASK_TYPES

        self.assertEqual(
            EXTERNAL_BRIEF_TASK_TYPES,
            {"morning_external_brief", "gold_price_brief", "fuel_price_brief", "ai_price_brief"},
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
