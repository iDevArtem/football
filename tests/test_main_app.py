# tests/test_main_app.py
from fastapi.testclient import TestClient
from app.main import app


def test_api_unauthorized():
    client = TestClient(app)
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_spa_fallback_route():
    client = TestClient(app)
    # Root path should return 200 (HTML or placeholder if static not yet built)
    response = client.get("/")
    assert response.status_code == 200
