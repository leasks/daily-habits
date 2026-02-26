import os
os.environ["TEST_MODE"] = "1"

import unittest

from app import coaching


class CoachingTestModeTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_coaching_returns_mock_text_in_test_mode(self):
        text = await coaching.generate_coaching({"goals": ["A"]}, model="gpt-4.1-mini")
        self.assertIn("Mocked coaching plan", text)

    async def test_generate_weekly_memory_patterns_returns_json(self):
        result = await coaching.generate_weekly_memory_patterns({"goal_history": []})
        self.assertIn("patterns", result)
        self.assertGreaterEqual(result["patterns"][0]["importance"], 7)

    async def test_generate_daily_reflection_returns_expected_fields(self):
        result = await coaching.generate_daily_reflection({"goals": ["A"]})
        self.assertIn("achieved_goals", result)
        self.assertIn("unachieved_goals", result)
        self.assertIn("next_day_prompt", result)


if __name__ == "__main__":
    unittest.main()
