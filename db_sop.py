"""SOP 执行台数据访问层。

封装 sop_anchors / sop_action_progress / sop_week_completion 三张表的 CRUD。
复用 db_utils.db_cursor() 做事务管理。
"""
from datetime import date
from typing import Dict, List, Optional

from db_utils import db_cursor


# ============================================================
# sop_anchors
# ============================================================

def upsert_anchor(
    anchor_name: str,
    operator_name: str,
    note: Optional[str] = None,
    current_blocker: Optional[str] = None,
) -> None:
    """UPSERT 主播元数据。首次插入时 start_date 自动填当天。

    None 值不覆盖已有字段。
    """
    sql = """
        INSERT INTO sop_anchors
            (anchor_name, operator_name, start_date, last_saved_date, note, current_blocker)
        VALUES (%s, %s, CURDATE(), CURDATE(), %s, %s) AS new_row
        ON DUPLICATE KEY UPDATE
            operator_name   = new_row.operator_name,
            last_saved_date = CURDATE(),
            note            = COALESCE(new_row.note, sop_anchors.note),
            current_blocker = COALESCE(new_row.current_blocker, sop_anchors.current_blocker)
    """
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name, operator_name, note, current_blocker))


def get_anchor(anchor_name: str) -> Optional[Dict]:
    """按主播名查询元数据，不存在返回 None。"""
    sql = "SELECT * FROM sop_anchors WHERE anchor_name = %s"
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name,))
        return cursor.fetchone()


def list_anchors() -> List[Dict]:
    """列出所有主播元数据（按创建时间降序）。"""
    sql = "SELECT * FROM sop_anchors ORDER BY created_at DESC"
    with db_cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


def delete_anchor(anchor_name: str) -> None:
    """删除主播（级联删除 progress 和 week_completion 行）。"""
    sql = "DELETE FROM sop_anchors WHERE anchor_name = %s"
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name,))


# ============================================================
# sop_action_progress（占位，下一 Task 实现）
# ============================================================

def upsert_progress(
    anchor_name: str,
    week: int,
    action_index: int,
    sub_index: int = -1,
    child_index: int = -1,
    checked: Optional[bool] = None,
    note: Optional[str] = None,
) -> None:
    raise NotImplementedError


def list_progress(anchor_name: str) -> List[Dict]:
    raise NotImplementedError
