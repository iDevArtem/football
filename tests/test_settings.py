# tests/test_settings.py
def test_new_settings_fields():
    from app.config.settings import Settings
    s = Settings(
        bot_token="test_token",
        admin_telegram_ids="12345, 67890",
        webapp_url="https://football.idev.wtf",
        jwt_secret="super-secret-key-32-chars-minimum-length!",
        card_number="4149 0000 0000 0000",
        card_recipient="Организатор"
    )
    assert s.webapp_url == "https://football.idev.wtf"
    assert s.jwt_secret == "super-secret-key-32-chars-minimum-length!"
    assert s.card_number == "4149 0000 0000 0000"
    assert s.card_recipient == "Организатор"
    assert s.admin_ids == {12345, 67890}
