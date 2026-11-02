import unittest
from datetime import datetime, timezone
from bson import ObjectId
from app.services.render import format_game_message


class TestRenderDynamic(unittest.TestCase):
    def test_dynamic_format_and_no_friends_text(self):
        game = {
            "_id": ObjectId(),
            "title": "Футбол",
            "start_at": datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc),
            "duration_minutes": 90,
            "hourly_rate": 600,
            "price": 75,
            "max_players": 15,
            "status": "registration_open",
            "friends_allowed": False,
        }

        # 0 players
        text_0 = format_game_message(game, [])
        self.assertNotIn("Друзья", text_0)
        self.assertNotIn("записываются только участники группы", text_0)
        self.assertIn("Сбор состава (нужно от 10 чел для 5х5)", text_0)

        # 10 players
        p10 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(10)]
        text_10 = format_game_message(game, p10)
        self.assertIn("2 команды 5х5 (10 чел)", text_10)
        self.assertNotIn("Друзья", text_10)

        # 12 players
        p12 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(12)]
        text_12 = format_game_message(game, p12)
        self.assertIn("2 команды 5х5 (+2 на замену)", text_12)
        self.assertNotIn("Друзья", text_12)

        # 14 players
        p14 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(14)]
        text_14 = format_game_message(game, p14)
        self.assertIn("3 команды (14 чел, с ротацией/заменами)", text_14)

        # 15 players
        p15 = [{"status": "confirmed", "type": "player", "display_name": f"P{i}"} for i in range(15)]
        text_15 = format_game_message(game, p15)
        self.assertIn("3 команды 5х5 (15 чел — полный сбор!)", text_15)
        self.assertNotIn("Друзья", text_15)

    def test_dynamic_format_custom_max_players(self):
        from app.services.render import dynamic_format_text
        self.assertEqual(dynamic_format_text(4, max_players=10), "⏳ Сбор состава (4/10)")
        self.assertEqual(dynamic_format_text(10, max_players=10), "🔥 Состав набран (10 чел — сбор закрыт)")
        self.assertEqual(dynamic_format_text(12, max_players=10), "🔥 Состав набран (10 чел, резерв 2)")


if __name__ == "__main__":
    unittest.main()
