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


def test_upsert_progress_inserts_new_row():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=True, note="OK",
    )
    rows = db_sop.list_progress("王老师")
    assert len(rows) == 1
    assert rows[0]["week"] == 1
    assert rows[0]["action_index"] == 0
    assert rows[0]["sub_index"] == -1
    assert rows[0]["child_index"] == -1
    assert rows[0]["checked"] == 1
    assert rows[0]["note"] == "OK"


def test_upsert_progress_updates_existing():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=True,
    )
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=False,
    )
    rows = db_sop.list_progress("王老师")
    assert len(rows) == 1
    assert rows[0]["checked"] == 0


def test_upsert_progress_preserves_unset_fields():
    """checked 和 note 分别传，另一个字段不应被清空。"""
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=True, note="初始备注",
    )
    # 只更新 checked，不传 note
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=False,
    )
    rows = db_sop.list_progress("王老师")
    assert rows[0]["checked"] == 0
    assert rows[0]["note"] == "初始备注"  # note 保留


def test_upsert_progress_three_levels_coexist():
    """同 (week, action_index) 下 action / substep / child 三层互不冲突。"""
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    # action 层
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, checked=True,
    )
    # substep 层
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, sub_index=0, checked=True,
    )
    # child 层
    db_sop.upsert_progress(
        anchor_name="王老师", week=1, action_index=0, sub_index=0, child_index=0,
        checked=True,
    )
    rows = db_sop.list_progress("王老师")
    assert len(rows) == 3


def test_mark_week_complete_inserts_row():
    from datetime import date
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.mark_week_complete(anchor_name="王老师", week=1)
    completions = db_sop.list_week_completions("王老师")
    assert completions == {1: date.today()}


def test_mark_week_complete_is_idempotent():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.mark_week_complete(anchor_name="王老师", week=1)
    db_sop.mark_week_complete(anchor_name="王老师", week=1)  # 重复
    completions = db_sop.list_week_completions("王老师")
    assert list(completions.keys()) == [1]  # 仍然只有一条


def test_advance_week_increments_and_marks_complete():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    # 初始 current_week=1
    db_sop.advance_week("王老师")
    anchor = db_sop.get_anchor("王老师")
    assert anchor["current_week"] == 2
    assert 1 in db_sop.list_week_completions("王老师")


def test_advance_week_caps_at_4_and_marks_done():
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    for _ in range(5):
        db_sop.advance_week("王老师")  # 1→2→3→4→4（封顶）
    anchor = db_sop.get_anchor("王老师")
    assert anchor["current_week"] == 4
    assert anchor["status"] == "已完成"


def test_advance_week_to_week_4_keeps_status_in_progress():
    """从 week 3 advance 到 week 4 时，status 应保持'进行中'（week 4 还在做）。"""
    db_sop.upsert_anchor(anchor_name="王老师", operator_name="阿杰")
    db_sop.advance_week("王老师")  # 1→2
    db_sop.advance_week("王老师")  # 2→3
    db_sop.advance_week("王老师")  # 3→4
    anchor = db_sop.get_anchor("王老师")
    assert anchor["current_week"] == 4
    assert anchor["status"] == "进行中"  # 不能是'已完成'

    db_sop.advance_week("王老师")  # 4→4，此时 status 才标完成
    anchor = db_sop.get_anchor("王老师")
    assert anchor["status"] == "已完成"
