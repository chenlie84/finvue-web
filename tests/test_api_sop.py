"""/api/sop/* 端点集成测试。

使用 fastapi TestClient 直接打 HTTP，走真 MySQL（清理 fixture 在 conftest.py）。
"""
import pytest
from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


# ============================================================
# GET /api/sop/anchors
# ============================================================

def test_get_anchors_empty():
    resp = client.get("/api/sop/anchors")
    assert resp.status_code == 200
    assert resp.json() == {"anchors": []}


# ============================================================
# PUT /api/sop/anchors/{name}
# ============================================================

def test_put_anchor_creates_new():
    resp = client.put(
        "/api/sop/anchors/王老师",
        json={"operatorName": "阿杰"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["anchorName"] == "王老师"
    assert body["operatorName"] == "阿杰"
    assert body["currentWeek"] == 1
    assert body["status"] == "进行中"
    assert body["warning"] is False


def test_put_anchor_updates_existing_fields():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    resp = client.put(
        "/api/sop/anchors/王老师",
        json={"operatorName": "阿杰", "note": "镜头感偏弱"},
    )
    assert resp.status_code == 200
    assert resp.json()["note"] == "镜头感偏弱"


def test_put_anchor_missing_operator_returns_422():
    resp = client.put("/api/sop/anchors/王老师", json={})
    assert resp.status_code == 422


# ============================================================
# GET /api/sop/anchors/{name}
# ============================================================

def test_get_anchor_detail():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    resp = client.get("/api/sop/anchors/王老师")
    assert resp.status_code == 200
    assert resp.json()["anchorName"] == "王老师"


def test_get_anchor_missing_returns_404():
    resp = client.get("/api/sop/anchors/不存在")
    assert resp.status_code == 404


# ============================================================
# DELETE /api/sop/anchors/{name}
# ============================================================

def test_delete_anchor():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    resp = client.delete("/api/sop/anchors/王老师")
    assert resp.status_code == 204
    assert client.get("/api/sop/anchors/王老师").status_code == 404
