import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import math
from bson import ObjectId

from app.bot.keyboards import payment_duration_keyboard


class TestPaymentDuration(unittest.IsolatedAsyncioTestCase):
    def test_payment_duration_keyboard(self):
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        kb = payment_duration_keyboard(game_id, hourly_rate=600)
        self.assertEqual(len(kb.inline_keyboard), 2)
        row0 = kb.inline_keyboard[0]
        self.assertIn("1.5 часа (900 грн)", row0[0].text)
        self.assertEqual(row0[0].callback_data, f"admin:{game_id}:paydur:90")
        self.assertIn("2.0 часа (1200 грн)", row0[1].text)
        self.assertEqual(row0[1].callback_data, f"admin:{game_id}:paydur:120")
        for row in kb.inline_keyboard:
            for btn in row:
                self.assertLessEqual(len(btn.callback_data.encode("utf-8")), 64)

    def test_cost_splitting_math(self):
        hourly_rate = 600
        duration_min = 90
        total_cost = int((duration_min / 60) * hourly_rate)
        self.assertEqual(total_cost, 900)

        # 12 players -> 75 each
        self.assertEqual(math.ceil(total_cost / 12), 75)
        # 14 players -> 65 each (64.28 -> 65)
        self.assertEqual(math.ceil(total_cost / 14), 65)
        # 10 players -> 90 each
        self.assertEqual(math.ceil(total_cost / 10), 90)


if __name__ == "__main__":
    unittest.main()
