import logging
from typing import Any, Optional, Union

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.methods.base import TelegramMethod
from aiogram.types import (
    InlineKeyboardMarkup,
    InputMediaPhoto,
    InputMediaVideo,
    LinkPreviewOptions,
    Message,
)
from pydantic import BaseModel

from app.services.render import (
    format_game_caption,
    format_game_message,
    format_game_rich_blocks,
    format_game_rich_html,
)

logger = logging.getLogger(__name__)


class LocationCoords(BaseModel):
    latitude: float
    longitude: float


class InputRichBlockMap(BaseModel):
    type: str = "map"
    location: LocationCoords
    zoom: int = 15
    width: Optional[int] = 600
    height: Optional[int] = 260
    caption: Optional[str] = None


class InputRichMessage(BaseModel):
    blocks: Optional[list[dict[str, Any]]] = None
    html: Optional[str] = None
    markdown: Optional[str] = None


class SendRichMessage(TelegramMethod[Message]):
    __returning__ = Message
    __api_method__ = "sendRichMessage"

    chat_id: Union[int, str]
    rich_message: Union[InputRichMessage, dict[str, Any]]
    reply_markup: Optional[InlineKeyboardMarkup] = None
    disable_notification: Optional[bool] = None
    protect_content: Optional[bool] = None


class EditMessageRich(TelegramMethod[Union[Message, bool]]):
    __returning__ = Message
    __api_method__ = "editMessageText"

    chat_id: Optional[Union[int, str]] = None
    message_id: Optional[int] = None
    inline_message_id: Optional[str] = None
    rich_message: Union[InputRichMessage, dict[str, Any]]
    reply_markup: Optional[InlineKeyboardMarkup] = None


def build_game_rich_message(
    game: dict,
    participants: list[dict],
    payments: list[dict] | None = None,
) -> dict[str, Any] | None:
    """Формирует InputRichMessage с блоком карты RichBlockMap, если заданы координаты."""
    blocks = format_game_rich_blocks(game, participants, payments)
    if not blocks:
        return None
    return {"blocks": blocks}


async def send_game_message(
    bot: Bot,
    chat_id: int | str,
    game: dict,
    participants: list[dict],
    reply_markup: InlineKeyboardMarkup | None = None,
    link_preview_options: LinkPreviewOptions | None = None,
    message: Message | None = None,
) -> Message:
    """Отправляет карточку игры с форматированным HTML-описанием и кнопками."""
    text = format_game_message(game, participants)
    if message and hasattr(message, "answer"):
        res = message.answer(
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            link_preview_options=link_preview_options,
        )
        if hasattr(res, "__await__"):
            return await res
        return res

    res = bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode="HTML",
        link_preview_options=link_preview_options,
    )
    if hasattr(res, "__await__"):
        return await res
    return res


async def edit_game_message(
    bot: Bot,
    chat_id: int | str,
    message_id: int,
    game: dict,
    participants: list[dict],
    payments: list[dict] | None = None,
    reply_markup: InlineKeyboardMarkup | None = None,
    link_preview_options: LinkPreviewOptions | None = None,
) -> Message | bool:
    """Редактирует карточку игры через стандартный edit_message_text или edit_message_media, если прикреплено фото/видео."""
    media_file_id = game.get("media_file_id")
    if media_file_id:
        caption = format_game_caption(game, participants, payments, max_length=1024)
        media_type = game.get("media_type", "photo")
        MediaClass = InputMediaVideo if media_type == "video" else InputMediaPhoto
        media_obj = MediaClass(media=media_file_id, caption=caption, parse_mode="HTML")
        try:
            res = bot.edit_message_media(
                chat_id=chat_id,
                message_id=message_id,
                media=media_obj,
                reply_markup=reply_markup,
            )
            if hasattr(res, "__await__"):
                return await res
            return res
        except TelegramBadRequest as e:
            err_text = str(e).lower()
            if "not modified" in err_text:
                return True
            # Fallback to text editing if media replacement is rejected
            pass

    text = format_game_message(game, participants, payments)
    try:
        res = bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode="HTML",
            link_preview_options=link_preview_options,
        )
        if hasattr(res, "__await__"):
            return await res
        return res
    except TelegramBadRequest as e:
        err_text = str(e).lower()
        if "not modified" in err_text:
            return True
        raise
