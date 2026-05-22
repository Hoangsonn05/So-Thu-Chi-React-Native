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
                {"amount": 35000, "type": 0, "note": "Circle K", "source": "Momo"},
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

    def test_deterministic_parser_required_bank_notifications(self):
        cases = [
            {
                "name": "momo_income",
                "package": "com.mservice.momotransfer",
                "title": "Nhận tiền chuyển khoản từ NGUYEN HOANG S...",
                "text": 'Số tiền 5.000 đ, kèm lời nhắn: "Test AI gg FT26142754623982".',
                "amount": 5000,
                "type": 1,
                "source": "Momo",
                "category": main.INCOME_CATEGORIES[-1],
                "note": "Nhận tiền MoMo từ NGUYEN HOANG S... - Test AI gg",
                "redacted": ["FT26142754623982"],
            },
            {
                "name": "mb_income",
                "package": "com.mbmobile",
                "title": "Thông báo biến động số dư",
                "text": "TK 09xxx005|GD: +7,000VND 22/05/26 09:12 |SD: 15,000VND|TU: NGUYEN HOANG SON - 2610200595|ND: Test AI gg FT26142090977510 kC97BE76/588218",
                "amount": 7000,
                "type": 1,
                "source": "MB Bank",
                "category": main.INCOME_CATEGORIES[-1],
                "note": "Nhận chuyển khoản từ NGUYEN HOANG SON - Test AI gg",
                "redacted": ["2610200595", "FT26142090977510", "kC97BE76/588218", "SD:"],
            },
            {
                "name": "mb_expense",
                "package": "com.mbmobile",
                "title": "Thông báo biến động số dư",
                "text": "TK 09xxx005|GD:-15,000VND 22/05/26 09:21 |SD: 0VND|DEN: NGUYEN HOANG SON - 2610200595|ND: MBCT test ai gg ck tru tien D2JLC58U/308441",
                "amount": 15000,
                "type": 0,
                "source": "MB Bank",
                "category": main.EXPENSE_CATEGORIES[-1],
                "note": "MBCT test ai gg ck tru tien",
                "redacted": ["09xxx005", "2610200595", "D2JLC58U/308441", "SD:"],
            },
            {
                "name": "jollibee",
                "package": "com.mservice.momotransfer",
                "title": "Thanh toán thành công",
                "text": "Bạn đã thanh toán 35.000đ tại Jollibee",
                "amount": 35000,
                "type": 0,
                "source": "Momo",
                "category": main.EXPENSE_CATEGORIES[0],
                "note": "Jollibee",
                "redacted": [],
            },
            {
                "name": "circle_k_mb",
                "package": "com.mbmobile",
                "title": "Thông báo biến động số dư",
                "text": "TK xxx GD: -60,000VND ND: Thanh toan Circle K",
                "amount": 60000,
                "type": 0,
                "source": "MB Bank",
                "category": main.EXPENSE_CATEGORIES[1],
                "note": "Circle K",
                "redacted": [],
            },
            {
                "name": "circle_k_bidv",
                "package": "com.vnpay.bidv",
                "title": "Bien dong so du",
                "text": "Bien dong so du: -200,000 VND. Noi dung: Thanh toan QR Circle K",
                "amount": 200000,
                "type": 0,
                "source": "BIDV",
                "category": main.EXPENSE_CATEGORIES[1],
                "note": "Circle K",
                "redacted": [],
            },
            {
                "name": "techcombank",
                "package": "vn.com.techcombank.bb.app",
                "title": "Thông báo giao dịch",
                "text": "TK 1903xxx bị trừ 500.000 VND. ND: Chuyen tien an trua",
                "amount": 500000,
                "type": 0,
                "source": "Techcombank",
                "category": main.EXPENSE_CATEGORIES[-1],
                "note": "Chuyen tien an trua",
                "redacted": [],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                parsed = main.parse_auto_notification_deterministic(case["title"], case["text"], case["package"])
                merged = main._merge_auto_notification_parse(parsed, None)
                self.assertEqual(merged["amount"], case["amount"])
                self.assertEqual(merged["type"], case["type"])
                self.assertEqual(merged["source"], case["source"])
                self.assertEqual(merged["category"], case["category"])
                self.assertIn(case["note"], merged["note"])
                for forbidden in case["redacted"]:
                    self.assertNotIn(forbidden, merged["note"])

    def test_momo_note_extraction_keeps_sender_and_message(self):
        cases = [
            {
                "name": "trimmed_sender_message",
                "title": "Nhận tiền chuyển khoản từ NGUYEN HOANG S...",
                "text": 'Số tiền 5.500 đ, kèm lời nhắn: "Test doc nd ck ai FT26142008910608".',
                "amount": 5500,
                "note": "Nhận tiền MoMo từ NGUYEN HOANG S... - Test doc nd ck ai",
                "forbidden": ["FT26142008910608"],
            },
            {
                "name": "full_sender_message",
                "title": "Nhận tiền chuyển khoản từ NGUYEN HOANG SON",
                "text": 'Số tiền 10.000 đ, kèm lời nhắn: "Test AI gg FT26142754623982."',
                "amount": 10000,
                "note": "Nhận tiền MoMo từ NGUYEN HOANG SON - Test AI gg",
                "forbidden": ["FT26142754623982"],
            },
            {
                "name": "full_sender_without_message",
                "title": "Nhận tiền chuyển khoản từ NGUYEN HOANG SON",
                "text": "Số tiền 5.500 đ",
                "amount": 5500,
                "note": "Nhận tiền MoMo từ NGUYEN HOANG SON",
                "forbidden": [],
            },
            {
                "name": "sender_account_removed",
                "title": "Nhận tiền chuyển khoản từ NGUYEN HOANG SON - 2610200595",
                "text": 'Số tiền 5.500 đ, kèm lời nhắn: "Test doc nd ck ai FT26142008910608".',
                "amount": 5500,
                "note": "Nhận tiền MoMo từ NGUYEN HOANG SON - Test doc nd ck ai",
                "forbidden": ["2610200595", "FT26142008910608"],
            },
            {
                "name": "jollibee_expense",
                "title": "Thanh toán thành công",
                "text": "Bạn đã thanh toán 35.000đ tại Jollibee",
                "amount": 35000,
                "type": 0,
                "category": main.EXPENSE_CATEGORIES[0],
                "note": "Thanh toán MoMo - Jollibee",
                "forbidden": [],
            },
            {
                "name": "circle_k_expense",
                "title": "Thanh toán thành công",
                "text": "Bạn đã thanh toán 60.000đ tại Circle K",
                "amount": 60000,
                "type": 0,
                "category": main.EXPENSE_CATEGORIES[1],
                "note": "Thanh toán MoMo - Circle K",
                "forbidden": [],
            },
        ]

        for case in cases:
            with self.subTest(case=case["name"]):
                parsed = main.parse_auto_notification_deterministic(
                    case["title"],
                    case["text"],
                    "com.mservice.momotransfer",
                )
                merged = main._merge_auto_notification_parse(
                    parsed,
                    {"note": "Nhận 5.500đ từ Nguyễn Hoàng Sơn"},
                )
                self.assertEqual(merged["amount"], case["amount"])
                self.assertEqual(merged["type"], case.get("type", 1))
                self.assertEqual(merged["source"], "Momo")
                self.assertEqual(merged["category"], case.get("category", main.INCOME_CATEGORIES[-1]))
                self.assertEqual(merged["note"], case["note"])
                for forbidden in case["forbidden"]:
                    self.assertNotIn(forbidden, merged["note"])

    def test_momo_render_payload_uses_deterministic_parser_without_ai(self):
        saved_payloads = []

        def _save(_uid, payload, _prefix):
            saved_payloads.append(payload)
            return "at_momo"

        with patch("main.analyze_text_with_gemini") as ai, \
            patch("main._save_transaction_atomic", side_effect=_save), \
            patch("main._send_fcm_notification"), \
            patch("main._send_auto_detect_telegram_notification"), \
            patch("agentic_ai.check_budget_thresholds"), \
            patch("builtins.print") as printed:
            main.process_ai_and_save(
                None,
                "uid",
                None,
                'Thông báo từ ứng dụng com.mservice.momotransfer: Nhận tiền chuyển khoản từ NGUYEN HOANG SON - Số tiền 8.000 ₫, kèm lời nhắn: "Test doc giao dich v3 FT26142263740354".',
                True,
                "com.mservice.momotransfer",
                "Nhận tiền chuyển khoản từ NGUYEN HOANG SON",
                'Số tiền 8.000 ₫, kèm lời nhắn: "Test doc giao dich v3 FT26142263740354".',
            )

        ai.assert_not_called()
        self.assertEqual(len(saved_payloads), 1)
        self.assertEqual(saved_payloads[0]["amount"], 8000)
        self.assertEqual(saved_payloads[0]["type"], 1)
        self.assertEqual(saved_payloads[0]["source"], "Momo")
        self.assertEqual(saved_payloads[0]["category"], main.INCOME_CATEGORIES[-1])
        self.assertEqual(
            saved_payloads[0]["note"],
            "Nhận tiền MoMo từ NGUYEN HOANG SON - Test doc giao dich v3",
        )
        self.assertNotIn("FT26142263740354", saved_payloads[0]["note"])
        log_lines = [" ".join(str(part) for part in call.args) for call in printed.call_args_list]
        self.assertIn("[AutoParser] deterministic_success=True", log_lines)
        self.assertIn("[AutoParser] locked_fields=amount,type,source,note", log_lines)
        self.assertIn("[AutoParser] ai_fallback=False", log_lines)

    def test_gd_sign_locks_amount_type_and_mapped_source_from_ai_override(self):
        deterministic = main.parse_auto_notification_deterministic(
            "Thông báo biến động số dư",
            "TK xxx GD:-15,000VND ND: MBCT test ai gg ck tru tien",
            "com.mbmobile",
        )
        merged = main._merge_auto_notification_parse(
            deterministic,
            {"amount": 999999, "type": 1, "source": "Wrong", "note": "AI note"},
        )
        self.assertEqual(merged["amount"], 15000)
        self.assertEqual(merged["type"], 0)
        self.assertEqual(merged["source"], "MB Bank")

    def test_facebook_normal_notification_skips_firestore_and_telegram(self):
        with patch("main._save_transaction_atomic") as save, \
            patch("main._send_fcm_notification") as fcm, \
            patch("main._send_auto_detect_telegram_notification") as telegram, \
            patch("main.analyze_text_with_gemini") as ai:
            main.process_ai_and_save(
                None,
                "uid",
                None,
                "Facebook - Bạn có một thông báo mới",
                True,
                "com.facebook.katana",
                "Facebook",
                "Bạn có một thông báo mới",
            )

        save.assert_not_called()
        fcm.assert_not_called()
        telegram.assert_not_called()
        ai.assert_not_called()

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
