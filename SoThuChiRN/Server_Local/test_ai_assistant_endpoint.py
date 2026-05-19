import os
import sys
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import main


client = TestClient(main.app)


class AIAssistantEndpointTests(unittest.TestCase):
    def test_greeting_does_not_call_openrouter(self):
        with patch("main.analyze_text_with_gemini") as mocked_analyze:
            resp = client.post("/api/ai/assistant", json={
                "firebase_uid": "test_uid",
                "message": "Xin chào",
                "mode": "auto",
            })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["intent"], "greeting")
        self.assertIsNone(data["transaction"])
        mocked_analyze.assert_not_called()

    def test_transaction_message_returns_transaction_object(self):
        parsed = {
            "type": 0,
            "amount": 30000,
            "category": "Ăn uống",
            "note": "Ăn sáng",
            "date": "19/05/2026",
            "source": "Tiền mặt",
        }
        with patch("main.analyze_text_with_gemini", return_value=parsed), \
            patch("main._save_transaction_atomic", return_value="appai_1"), \
            patch("main._send_fcm_notification"), \
            patch("agentic_ai.check_budget_thresholds"):
            resp = client.post("/api/ai/assistant", json={
                "firebase_uid": "test_uid",
                "message": "ăn sáng 30k",
                "mode": "auto",
            })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["intent"], "transaction")
        self.assertEqual(data["transaction"]["amount"], 30000)
        self.assertEqual(data["transaction_id"], "appai_1")

    def test_missing_openrouter_key_returns_friendly_error(self):
        with patch("main.OPENROUTER_API_KEY", None):
            resp = client.post("/api/ai/assistant", json={
                "firebase_uid": "test_uid",
                "message": "ăn sáng 30k",
                "mode": "auto",
            })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["message"], "AI backend chưa được cấu hình hoặc đang bận. Vui lòng thử lại sau.")
        self.assertIsNone(data["transaction"])

    def test_missing_firebase_uid_for_transaction_is_clear(self):
        resp = client.post("/api/ai/assistant", json={
            "message": "ăn sáng 30k",
            "mode": "auto",
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["success"])
        self.assertEqual(data["message"], "Bạn cần đăng nhập để dùng Trợ Lý AI.")
        self.assertIsNone(data["transaction_id"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
