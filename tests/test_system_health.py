from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import system


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(system.router)
    return app


def test_healthz_alive():
    response = TestClient(_app()).get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_readyz_reports_checks(monkeypatch, tmp_path):
    monkeypatch.setattr(system.config, "has_mysql_config", lambda: False)
    monkeypatch.setattr(system.config, "has_ceph_config", lambda: False)
    monkeypatch.setattr(system.config, "OBJECT_STORAGE_DIR", tmp_path / "objects")
    monkeypatch.setattr(system.config, "IS_PRODUCTION", False)
    response = TestClient(_app()).get("/readyz")
    payload = response.json()
    assert response.status_code == 200
    assert "database" in payload["checks"]
    assert "objectStorage" in payload["checks"]
