import json
import os
import sys
import unittest
from unittest.mock import Mock, patch


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main


class _FakeUserDoc:
    def __init__(self, data):
        self.exists = data is not None
        self._data = data or {}

    def to_dict(self):
        return self._data


class _FakeUserRef:
    def __init__(self, data):
        self._data = data

    def get(self):
        return _FakeUserDoc(self._data)


class _FakeUsersCollection:
    def __init__(self, data):
        self._data = data

    def document(self, _firebase_uid):
        return _FakeUserRef(self._data)


class _FakeDb:
    def __init__(self, data):
        self._data = data

    def collection(self, name):
        if name != "users":
            raise AssertionError(f"Unexpected collection: {name}")
        return _FakeUsersCollection(self._data)


class _FakeOpenRouterResponse:
    status_code = 200
    text = ""

    def json(self):
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "type": 0,
                                "amount": 35000,
                                "category": main.EXPENSE_CATEGORIES[-1],
                                "note": "Thanh toan Circle K",
                                "date": "22/05/2026",
                                "source": "Momo",
                            }
                        )
                    }
                }
            ]
        }


class AutoNotificationPipelineTests(unittest.TestCase):
    def test_package_source_mapping_for_supported_notifications(self):
        expected = {
            "com.mservice.momotransfer": "Momo",
            "vn.com.vng.zalopay": "ZaloPay",
            "vn.com.techcombank.bb.app": "Techcombank",
            "com.tecb.smartbanking": "Techcombank",
            "com.mbmobile": "MB Bank",
            "com.vnpay.bidv": "BIDV",
            "com.bidv.smartbanking": "BIDV",
        }
        for package_name, source in expected.items():
            with self.subTest(package_name=package_name):
                self.assertEqual(main.map_package_to_source(package_name), source)

    def test_single_ai_parser_preserves_source(self):
        with patch("main.OPENROUTER_API_KEY", "test-key"), \
            patch("main.requests.post", return_value=_FakeOpenRouterResponse()), \
            patch("builtins.print"):
            parsed = main.analyze_text_with_gemini("Momo thanh toan Circle K 35.000d")

        self.assertEqual(parsed["source"], "Momo")

    def test_required_auto_notification_cases_keep_mapped_source(self):
        cases = [
            (
                "com.mservice.momotransfer",
                "Ban da thanh toan 35.000d tai Circle K",
                {"amount": 35000, "type": 0, "note": "Thanh toan Circle K", "source": "Momo"},
            ),
            (
                "vn.com.vng.zalopay",
                "Giao dich thanh toan thanh cong 120,000 VND",
                {"amount": 120000, "type": 0, "note": "Thanh toan ZaloPay", "source": "ZaloPay"},
            ),
            (
                "vn.com.techcombank.bb.app",
                "TK 1903xxx bi tru 500.000 VND. ND: Chuyen tien an trua",
                {"amount": 500000, "type": 0, "note": "Chuyen tien an trua", "source": "Techcombank"},
            ),
            (
                "com.mbmobile",
                "TK xxx ghi co +1.000.000 VND tu NGUYEN VAN A",
                {"amount": 1000000, "type": 1, "note": "Tu NGUYEN VAN A", "source": "MB Bank"},
            ),
            (
                "com.vnpay.bidv",
                "Bien dong so du: -200,000 VND. Noi dung: Thanh toan QR",
                {"amount": 200000, "type": 0, "note": "Thanh toan QR", "source": "BIDV"},
            ),
        ]

        for package_name, text, expected in cases:
            parsed = {
                "amount": expected["amount"],
                "type": expected["type"],
                "category": main.EXPENSE_CATEGORIES[-1] if expected["type"] == 0 else main.INCOME_CATEGORIES[-1],
                "note": expected["note"],
                "date": "22/05/2026",
                "source": "",
            }
            save_payloads = []

            def _save(_uid, payload, _prefix):
                save_payloads.append(payload)
                return "at_1"

            with self.subTest(package_name=package_name), \
                patch("main._is_likely_multi_transaction_text", return_value=False), \
                patch("main.analyze_text_with_gemini", return_value=parsed.copy()), \
                patch("main._save_transaction_atomic", side_effect=_save), \
                patch("main._send_fcm_notification"), \
                patch("main._send_auto_detect_telegram_notification"), \
                patch("agentic_ai.check_budget_thresholds"):
                main.process_ai_and_save(None, "uid", None, text, True, package_name)

            self.assertEqual(save_payloads[0]["amount"], expected["amount"])
            self.assertEqual(save_payloads[0]["type"], expected["type"])
            self.assertEqual(save_payloads[0]["source"], expected["source"])
            self.assertIn(expected["note"], save_payloads[0]["note"])

    def test_auto_telegram_skip_when_config_is_missing(self):
        with patch("main.db", _FakeDb({})), patch("main.send_telegram_message") as send_message:
            sent = main._send_auto_detect_telegram_notification("uid", {"amount": 35000})

        self.assertFalse(sent)
        send_message.assert_not_called()

    def test_auto_telegram_failure_does_not_escape(self):
        telegram_config = {"telegramConfig": {"botToken": "test-token", "chatId": 1234}}
        with patch("main.db", _FakeDb(telegram_config)), \
            patch("main.send_telegram_message", side_effect=RuntimeError("send failed")):
            sent = main._send_auto_detect_telegram_notification(
                "uid",
                {"amount": 35000, "type": 0, "source": "Momo", "note": "Thanh toan Circle K"},
            )

        self.assertFalse(sent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
