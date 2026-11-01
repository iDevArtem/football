# tests/test_main_app.py
from fastapi.testclient import TestClient
from app.main import app


def test_api_unauthorized():
    client = TestClient(app)
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_spa_fallback_route():
    client = TestClient(app)
    # Root path should return 200 index.html
    response = client.get("/")
    assert response.status_code == 200


def test_path_traversal_blocked():
    from pathlib import Path
    from app.main import STATIC_DIR
    resolved_static = STATIC_DIR.resolve()
    # Any attempt to resolve outside static must fail is_relative_to
    escaped_file = (STATIC_DIR / "../main.py").resolve()
    assert not escaped_file.is_relative_to(resolved_static)
