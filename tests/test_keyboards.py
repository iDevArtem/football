import unittest
from app.bot.keyboards import broadcast_groups_keyboard, admin_game_keyboard


class TestKeyboards(unittest.TestCase):
    def test_broadcast_keyboard_callbacks_under_64_bytes(self):
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        chats = [
            {"chat_id": -1001234567890, "title": "Основной состав"},
            {"chat_id": -1009876543210, "title": "Резервный состав"},
        ]
        linked_chat_ids = {-1001234567890}
        kb = broadcast_groups_keyboard(game_id, chats, linked_chat_ids)
        
        button_texts = []
        callbacks = []
        for row in kb.inline_keyboard:
            for btn in row:
                button_texts.append(btn.text)
                callbacks.append(btn.callback_data)
                self.assertLessEqual(len(btn.callback_data.encode("utf-8")), 64)
                
        self.assertTrue(any("Опубликовать во всех" in t for t in button_texts))
        self.assertTrue(any("✅" in t and "Основной состав" in t for t in button_texts))
        self.assertTrue(any("➕" in t and "Резервный состав" in t for t in button_texts))
        self.assertIn(f"admin:{game_id}:pub_all", callbacks)
        self.assertIn(f"admin:{game_id}:unpub:-1001234567890", callbacks)
        self.assertIn(f"admin:{game_id}:pub:-1009876543210", callbacks)

    def test_admin_keyboard_includes_broadcast(self):
        game_id = "64a8b79f2e3d4c5b6a7b8c9d"
        kb = admin_game_keyboard(game_id, friends_allowed=False, status="registration_open")
        callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
        self.assertIn(f"admin:{game_id}:broadcast_menu", callbacks)


if __name__ == "__main__":
    unittest.main()
