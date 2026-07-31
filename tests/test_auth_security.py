from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(auth.router)
    return app


def test_login_failure_rate_limit(monkeypatch):
    auth._LOGIN_FAILURES.clear()
    monkeypatch.setattr(auth.store, "get_user_by_username", lambda username: None)
    monkeypatch.setattr(auth.logger, "log_login", lambda **kwargs: None)
    client = TestClient(_app())

    for _ in range(auth.LOGIN_FAILURE_LIMIT):
        response = client.post("/api/login", json={"username": "demo", "password": "bad"})
        assert response.status_code == 401

    response = client.post("/api/login", json={"username": "demo", "password": "bad"})
    assert response.status_code == 429
    assert "登录失败次数过多" in response.json()["detail"]


def test_login_success_clears_failures(monkeypatch):
    auth._LOGIN_FAILURES.clear()
    user = {"id": "u1", "username": "demo", "passwordSalt": "s", "passwordHash": "h"}
    monkeypatch.setattr(auth.store, "get_user_by_username", lambda username: user)
    monkeypatch.setattr(auth.security, "verify_password", lambda password, salt, hash_value: True)
    monkeypatch.setattr(auth.security, "sanitize_user", lambda value: {"id": value["id"], "username": value["username"]})
    monkeypatch.setattr(auth.security, "set_session_cookie", lambda request, response, user: None)
    monkeypatch.setattr(auth.logger, "log_login", lambda **kwargs: None)
    client = TestClient(_app())

    auth._record_login_failure("testclient", "demo")
    response = client.post("/api/login", json={"username": "demo", "password": "ok"})

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert auth._LOGIN_FAILURES == {}
