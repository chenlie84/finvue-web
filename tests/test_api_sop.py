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
# /api/sop/options
# ============================================================

def test_custom_options_empty():
    resp = client.get("/api/sop/options")
    assert resp.status_code == 200
    assert resp.json() == {"options": []}


def test_post_custom_option_and_list():
    resp = client.post(
        "/api/sop/options",
        json={"week": 1, "actionIndex": 1, "subIndex": 0, "label": "宏观择时"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["week"] == 1
    assert body["actionIndex"] == 1
    assert body["subIndex"] == 0
    assert body["label"] == "宏观择时"

    listed = client.get("/api/sop/options").json()["options"]
    assert len(listed) == 1
    assert listed[0]["label"] == "宏观择时"


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


# ============================================================
# PUT /api/sop/anchors/{name}/progress
# ============================================================

def test_put_progress_on_missing_anchor_returns_404():
    resp = client.put(
        "/api/sop/anchors/不存在/progress",
        json={"week": 1, "actionIndex": 0, "checked": True},
    )
    assert resp.status_code == 404


def test_put_progress_upsert_action_level():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    resp = client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 1, "actionIndex": 0, "checked": True, "note": "OK"},
    )
    assert resp.status_code == 204

    detail = client.get("/api/sop/anchors/王老师").json()
    assert len(detail["progress"]) == 1
    item = detail["progress"][0]
    assert item["week"] == 1 and item["actionIndex"] == 0
    assert item["subIndex"] == -1 and item["childIndex"] == -1
    assert item["checked"] is True and item["note"] == "OK"


def test_put_progress_note_only_preserves_checked():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 1, "actionIndex": 0, "checked": True},
    )
    resp = client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 1, "actionIndex": 0, "note": "备注自动保存"},
    )
    assert resp.status_code == 204

    item = client.get("/api/sop/anchors/王老师").json()["progress"][0]
    assert item["checked"] is True
    assert item["note"] == "备注自动保存"


def test_put_progress_substep_and_child_coexist():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    # substep
    client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 1, "actionIndex": 0, "subIndex": 0, "checked": True},
    )
    # child
    client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 1, "actionIndex": 0, "subIndex": 0, "childIndex": 2, "checked": True},
    )
    detail = client.get("/api/sop/anchors/王老师").json()
    assert len(detail["progress"]) == 2


def test_put_progress_validation():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    # week 超出 1-4
    resp = client.put(
        "/api/sop/anchors/王老师/progress",
        json={"week": 5, "actionIndex": 0, "checked": True},
    )
    assert resp.status_code == 422


# ============================================================
# POST /api/sop/anchors/{name}/advance
# ============================================================

def test_advance_increments_week_and_records_completion():
    client.put("/api/sop/anchors/王老师", json={"operatorName": "阿杰"})
    resp = client.post("/api/sop/anchors/王老师/advance")
    assert resp.status_code == 200
    body = resp.json()
    assert body["currentWeek"] == 2
    assert "1" in body["weekCompletions"]


def test_advance_missing_anchor_returns_404():
    resp = client.post("/api/sop/anchors/不存在/advance")
    assert resp.status_code == 404
