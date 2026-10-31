import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from bson import ObjectId

from app.repositories.chats import ChatRepository
from app.repositories.games import GameRepository
from app.repositories.participants import ParticipantRepository
from app.bot.handlers import update_game_message


class MockUser:
    def __init__(self, uid: int, name: str):
        self.id = uid
        self.full_name = name
        self.username = f"user_{uid}"


class AsyncCursorMock:
    def __init__(self, docs):
        self.docs = docs
    def __aiter__(self):
        self._iter = iter(self.docs)
        return self
    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class TestE2EMultiGroupSimulation(unittest.IsolatedAsyncioTestCase):
    @patch("app.bot.handlers.get_db")
    async def test_full_multigroup_lifecycle(self, mock_get_db):
        # In-memory collections state
        db_chats = {}
        db_games = {}
        db_participants = {}

        db = MagicMock()
        mock_get_db.return_value = db

        # Mock db.chats
        async def mock_chat_update_one(flt, update, upsert=False):
            cid = flt["chat_id"]
            if cid not in db_chats and upsert:
                db_chats[cid] = {"_id": ObjectId(), "chat_id": cid}
            if "$set" in update:
                db_chats[cid].update(update["$set"])
        db.chats.update_one = AsyncMock(side_effect=mock_chat_update_one)
        def mock_chats_find(flt=None):
            active = [c for c in db_chats.values() if flt is None or c.get("is_active") == flt.get("is_active")]
            mock_c = MagicMock()
            mock_c.sort = MagicMock(return_value=AsyncCursorMock(active))
            return mock_c
        db.chats.find = MagicMock(side_effect=mock_chats_find)

        # Mock db.games
        async def mock_game_insert_one(doc):
            gid = ObjectId()
            doc["_id"] = gid
            db_games[gid] = doc
            return MagicMock(inserted_id=gid)
        db.games.insert_one = AsyncMock(side_effect=mock_game_insert_one)

        async def mock_game_find_one(flt, sort=None):
            if "_id" in flt:
                return db_games.get(flt["_id"])
            if "messages.chat_id" in flt:
                cid = flt["messages.chat_id"]
                for g in reversed(list(db_games.values())):
                    if any(m["chat_id"] == cid for m in g.get("messages", [])):
                        return g
            return None
        db.games.find_one = AsyncMock(side_effect=mock_game_find_one)

        async def mock_game_update_one(flt, update):
            gid = flt["_id"]
            if gid in db_games:
                if "$push" in update:
                    for k, v in update["$push"].items():
                        db_games[gid].setdefault(k, []).append(v)
                if "$pull" in update:
                    for k, v in update["$pull"].items():
                        if k in db_games[gid]:
                            db_games[gid][k] = [
                                item for item in db_games[gid][k]
                                if not all(item.get(fk) == fv for fk, fv in v.items())
                            ]
                if "$set" in update:
                    db_games[gid].update(update["$set"])
        db.games.update_one = AsyncMock(side_effect=mock_game_update_one)

        # Mock db.participants
        async def mock_part_insert_one(doc):
            pid = ObjectId()
            doc["_id"] = pid
            db_participants[pid] = doc
            return MagicMock(inserted_id=pid)
        db.participants.insert_one = AsyncMock(side_effect=mock_part_insert_one)

        def mock_part_find(flt=None):
            gid = flt.get("game_id")
            items = [p for p in db_participants.values() if p.get("game_id") == gid]
            items.sort(key=lambda x: x.get("position", 0))
            mock_c = MagicMock()
            mock_c.sort = MagicMock(return_value=AsyncCursorMock(items))
            return mock_c
        db.participants.find = MagicMock(side_effect=mock_part_find)

        async def mock_part_find_one(flt, sort=None):
            for p in db_participants.values():
                match = True
                for k, v in flt.items():
                    if p.get(k) != v:
                        match = False
                        break
                if match:
                    return p
            return None
        db.participants.find_one = AsyncMock(side_effect=mock_part_find_one)

        async def mock_part_count(flt):
            gid = flt.get("game_id")
            status = flt.get("status")
            return len([p for p in db_participants.values() if p.get("game_id") == gid and p.get("status") == status])
        db.participants.count_documents = AsyncMock(side_effect=mock_part_count)

        # 1. Register 2 groups
        chat_repo = ChatRepository(db)
        await chat_repo.upsert_chat(-100111, "Основа (Суббота)", "supergroup")
        await chat_repo.upsert_chat(-100222, "Резерв (Пятница)", "supergroup")
        active_chats = await chat_repo.list_active_chats()
        self.assertEqual(len(active_chats), 2)

        # 2. Admin creates game in DM
        game_repo = GameRepository(db)
        game = await game_repo.create_game(
            title="Футбол Суперкубок",
            start_at=datetime(2026, 11, 5, 20, 0, tzinfo=timezone.utc),
            teams_count=2,
            players_per_team=2,
            price=200,
            duration_minutes=90,
            friends_open_after_hours=6,
            created_by=999,
        )
        game_id = str(game["_id"])
        self.assertEqual(game["max_players"], 4)
        self.assertEqual(game["messages"], [])

        # 3. Publish to Group 1 and Group 2
        await game_repo.add_linked_message(game_id, -100111, 1001, "Основа (Суббота)")
        await game_repo.add_linked_message(game_id, -100222, 2002, "Резерв (Пятница)")

        # Verify lookup from both groups finds this game
        found_g1 = await game_repo.get_active_for_chat(-100111)
        found_g2 = await game_repo.get_active_for_chat(-100222)
        self.assertIsNotNone(found_g1)
        self.assertIsNotNone(found_g2)
        self.assertEqual(str(found_g1["_id"]), game_id)
        self.assertEqual(str(found_g2["_id"]), game_id)

        # 4. Player 1 joins in Group 1
        part_repo = ParticipantRepository(db)
        user1 = MockUser(101, "Игрок Один")
        fresh_game = await game_repo.get(game_id)
        await part_repo.join_player(fresh_game, user1)

        # Trigger sync across groups
        bot = MagicMock()
        bot.edit_message_text = AsyncMock()
        await update_game_message(bot, fresh_game)

        # Both group cards must be updated in parallel
        self.assertEqual(bot.edit_message_text.call_count, 2)
        call_texts = [call.kwargs["text"] for call in bot.edit_message_text.call_args_list]
        for t in call_texts:
            self.assertIn("Игрок Один", t)
            self.assertIn("1 / 4", t)

        # 5. Player 2 joins in Group 2
        bot.edit_message_text.reset_mock()
        user2 = MockUser(102, "Игрок Два")
        await part_repo.join_player(fresh_game, user2)
        await update_game_message(bot, fresh_game)

        self.assertEqual(bot.edit_message_text.call_count, 2)
        call_texts = [call.kwargs["text"] for call in bot.edit_message_text.call_args_list]
        for t in call_texts:
            self.assertIn("Игрок Один", t)
            self.assertIn("Игрок Два", t)
            self.assertIn("2 / 4", t)

        # 6. Admin unpublishes from Group 2
        await game_repo.remove_linked_message(game_id, -100222)
        fresh_game = await game_repo.get(game_id)
        self.assertEqual(len(fresh_game["messages"]), 1)
        self.assertEqual(fresh_game["messages"][0]["chat_id"], -100111)

        bot.edit_message_text.reset_mock()
        await update_game_message(bot, fresh_game)
        # Now only Group 1 is edited
        self.assertEqual(bot.edit_message_text.call_count, 1)
        self.assertEqual(bot.edit_message_text.call_args[1]["chat_id"], -100111)


if __name__ == "__main__":
    unittest.main()
