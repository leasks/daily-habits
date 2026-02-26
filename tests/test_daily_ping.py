import os
import unittest

from app import daily_ping


class DailyPingTests(unittest.IsolatedAsyncioTestCase):
    async def test_main_short_circuits_in_test_mode(self):
        result = await daily_ping.main(test_mode=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["test_mode"])
        self.assertEqual(result["sent"], 0)

    def test_build_prompt_without_reflection_uses_base_prompt(self):
        os.environ["TEST_MODE"] = "1"
        prompt = daily_ping._build_prompt_for_user(1)
        self.assertIn("Morning check-in", prompt)


if __name__ == "__main__":
    unittest.main()
