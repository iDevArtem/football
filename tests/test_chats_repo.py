import unittest
from unittest.mock import AsyncMock, MagicMock
from app.repositories.chats import ChatRepository


class TestChatRepository(unittest.IsolatedAsyncioTestCase):
    async def test_upsert_and_list_chats(self):
        db = MagicMock()
        db.chats = MagicMock()
        db.chats.update_one = AsyncMock()
        
        # Mock cursor for find()
        mock_docs = [
            {"chat_id": -1001, "title": "Main Group", "type": "supergroup", "is_active": True},
            {"chat_id": -1002, "title": "Reserve Group", "type": "supergroup", "is_active": True},
        ]
        
        class AsyncIterator:
            def __init__(self, items):
                self.items = items
            def __aiter__(self):
                self._iter = iter(self.items)
                return self
            async def __anext__(self):
                try:
                    return next(self._iter)
                except StopIteration:
                    raise StopAsyncIteration
        
        cursor_mock = MagicMock()
        cursor_mock.sort = MagicMock(return_value=AsyncIterator(mock_docs))
        db.chats.find = MagicMock(return_value=cursor_mock)
        
        repo = ChatRepository(db)
        await repo.upsert_chat(-1001, "Main Group", "supergroup")
        
        db.chats.update_one.assert_called_once()
        call_filter, call_update = db.chats.update_one.call_args[0]
        self.assertEqual(call_filter, {"chat_id": -1001})
        self.assertEqual(call_update["$set"]["title"], "Main Group")
        self.assertTrue(call_update["$set"]["is_active"])

        active_chats = await repo.list_active_chats()
        self.assertEqual(len(active_chats), 2)
        self.assertEqual(active_chats[0]["chat_id"], -1001)

    async def test_set_active_status(self):
        db = MagicMock()
        db.chats = MagicMock()
        db.chats.update_one = AsyncMock()
        
        repo = ChatRepository(db)
        await repo.set_active_status(-1001, False)
        
        db.chats.update_one.assert_called_once()
        call_filter, call_update = db.chats.update_one.call_args[0]
        self.assertEqual(call_filter, {"chat_id": -1001})
        self.assertFalse(call_update["$set"]["is_active"])


if __name__ == "__main__":
    unittest.main()
