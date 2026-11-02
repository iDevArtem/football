from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from typing import Optional

from app.config.settings import get_settings, Settings
from app.db.mongo import get_db
from app.repositories.users import UserRepository
from app.api.auth import validate_init_data, validate_widget_data, create_access_token
from app.api.dependencies import get_current_user

router = APIRouter(tags=["auth"])


class TMALoginRequest(BaseModel):
    init_data: str


class TelegramUserObj:
    def __init__(self, d: dict):
        self.id = int(d.get("id"))
        self.first_name = d.get("first_name", "")
        self.last_name = d.get("last_name")
        self.username = d.get("username")

    @property
    def full_name(self) -> str:
        parts = [p.strip() for p in (self.first_name, self.last_name) if p and p.strip()]
        return " ".join(parts)


@router.post("/tma")
async def login_tma(
    req: TMALoginRequest,
    settings: Settings = Depends(get_settings),
):
    try:
        validated = validate_init_data(req.init_data, settings.bot_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    user_raw = validated.get("user")
    if not user_raw or "id" not in user_raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No user data in initData")

    tg_user = TelegramUserObj(user_raw)
    is_admin = tg_user.id in settings.admin_ids

    db = get_db()
    user_repo = UserRepository(db)
    user_doc = await user_repo.upsert_from_telegram(tg_user, is_admin=is_admin)

    role = "admin" if is_admin else "player"
    payload = {
        "sub": str(tg_user.id),
        "telegram_id": tg_user.id,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "username": tg_user.username,
        "role": role,
    }
    token = create_access_token(payload, settings.jwt_secret)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "telegram_id": tg_user.id,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "username": tg_user.username,
            "role": role,
        },
    }


@router.post("/widget")
async def login_widget(
    data: dict,
    settings: Settings = Depends(get_settings),
):
    try:
        validated = validate_widget_data(data, settings.bot_token)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    tg_user = TelegramUserObj(validated)
    is_admin = tg_user.id in settings.admin_ids

    db = get_db()
    user_repo = UserRepository(db)
    user_doc = await user_repo.upsert_from_telegram(tg_user, is_admin=is_admin)

    role = "admin" if is_admin else "player"
    payload = {
        "sub": str(tg_user.id),
        "telegram_id": tg_user.id,
        "first_name": tg_user.first_name,
        "last_name": tg_user.last_name,
        "username": tg_user.username,
        "role": role,
    }
    token = create_access_token(payload, settings.jwt_secret)

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "telegram_id": tg_user.id,
            "first_name": tg_user.first_name,
            "last_name": tg_user.last_name,
            "username": tg_user.username,
            "role": role,
        },
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    if "last_name" not in user:
        try:
            db = get_db()
            user_repo = UserRepository(db)
            user_doc = await user_repo.get_by_telegram_id(user["telegram_id"])
            if user_doc:
                user["last_name"] = user_doc.get("last_name")
        except Exception:
            pass
    return user


@router.get("/config")
async def get_public_config(settings: Settings = Depends(get_settings)):
    return {
        "bot_username": settings.bot_username,
        "webapp_url": settings.webapp_url,
    }
