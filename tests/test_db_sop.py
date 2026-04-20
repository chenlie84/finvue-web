"""db_sop 模块的集成测试（跑在本地 DEV MySQL）。"""
import pytest

import db_sop


def test_upsert_anchor_inserts_when_missing():
    db_sop.upsert_anchor(
        anchor_name="王老师",
        operator_name="阿杰",
    )
    anchor = db_sop.get_anchor("王老师")
    assert anchor is not None
    assert anchor["anchor_name"] == "王老师"
    assert anchor["operator_name"] == "阿杰"
    assert anchor["current_week"] == 1
    assert anchor["status"] == "进行中"
    assert anchor["start_date"] is not None  # 自动填当天


def test_upsert_anchor_updates_existing():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.upsert_anchor(
        anchor_name="王老师",
        operator_name="阿杰",
        note="镜头感偏弱",
        current_blocker="试讲观察未完成",
    )
    anchor = db_sop.get_anchor("王老师")
    assert anchor["note"] == "镜头感偏弱"
    assert anchor["current_blocker"] == "试讲观察未完成"


def test_get_anchor_returns_none_when_missing():
    assert db_sop.get_anchor("不存在的主播") is None


def test_delete_anchor_cascades():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=True,
    )
    db_sop.delete_anchor("王老师")
    assert db_sop.get_anchor("王老师") is None
    # 级联：progress 行也被清掉
    assert db_sop.list_progress("王老师") == []


def test_list_anchors_returns_all():
    db_sop.upsert_anchor(anchor_name="主播A", operator_name="阿杰")
    db_sop.upsert_anchor(anchor_name="主播B", operator_name="小美")
    anchors = db_sop.list_anchors()
    names = {a["anchor_name"] for a in anchors}
    assert names == {"主播A", "主播B"}
