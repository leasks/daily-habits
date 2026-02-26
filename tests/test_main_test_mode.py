import unittest
from fastapi.testclient import TestClient

from app.main import create_app


class MainTestModeTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(test_mode=True))

    def test_root_exposes_test_mode(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["test_mode"])

    def test_webhook_is_mocked_in_test_mode(self):
        payload = {
            "message": {
                "chat": {"id": 1234},
                "text": "- Goal one\n- Goal two\nMost important outcome: Finish tests",
            }
        }
        r = self.client.post("/webhooks/telegram", json=payload)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["test_mode"])
        self.assertEqual(data["parsed"]["goals"][:2], ["Goal one", "Goal two"])

    def test_job_endpoints_short_circuit_in_test_mode(self):
        weekly = self.client.post("/jobs/weekly-memory-review")
        daily = self.client.post("/jobs/daily-reflection-checkin")
        self.assertEqual(weekly.status_code, 200)
        self.assertEqual(daily.status_code, 200)
        self.assertEqual(weekly.json()["processed_users"], 0)
        self.assertEqual(daily.json()["processed_checkins"], 0)


if __name__ == "__main__":
    unittest.main()
