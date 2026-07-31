from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import daily_review


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(daily_review.router)
    for route in app.routes:
        if getattr(route, "path", "") == "/api/daily-review/generate":
            dependant = getattr(route, "dependant", None)
            for dependency in getattr(dependant, "dependencies", []):
                app.dependency_overrides[dependency.call] = lambda: {"username": "tester"}
    return app


def test_daily_review_generate_creates_job(monkeypatch):
    monkeypatch.setattr(daily_review, "_reports", lambda: [])
    monkeypatch.setattr(daily_review, "_run_generation_job", lambda job_id, trade_date, username: None)

    response = TestClient(_app()).post("/api/daily-review/generate", json={"date": "2026-07-20"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "running"
    assert payload["jobId"]
