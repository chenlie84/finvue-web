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
    """UPSERT 一条进度行。

    三层层级用 (sub_index, child_index) 编码：
      action 层    = (-1, -1)
      substep 层   = (>=0, -1)
      child 层     = (>=0, >=0)

    checked / note 传 None 表示"不更新此字段"。
    """
    sql = """
        INSERT INTO sop_action_progress
            (anchor_name, week, action_index, sub_index, child_index, checked, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s) AS new_row
        ON DUPLICATE KEY UPDATE
            checked = COALESCE(new_row.checked, sop_action_progress.checked),
            note    = COALESCE(new_row.note, sop_action_progress.note)
    """
    checked_int = None if checked is None else (1 if checked else 0)
    with db_cursor() as cursor:
        cursor.execute(
            sql,
            (anchor_name, week, action_index, sub_index, child_index, checked_int, note),
        )


def list_progress(anchor_name: str) -> List[Dict]:
    """列出某主播全部进度行。"""
    sql = """
        SELECT week, action_index, sub_index, child_index, checked, note, updated_at
        FROM sop_action_progress
        WHERE anchor_name = %s
        ORDER BY week, action_index, sub_index, child_index
    """
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name,))
        return list(cursor.fetchall())


# ============================================================
# sop_week_completion
# ============================================================

def mark_week_complete(anchor_name: str, week: int) -> None:
    """记录某周的达标日期（幂等，重复调用覆盖日期）。"""
    sql = """
        INSERT INTO sop_week_completion (anchor_name, week, completed_at)
        VALUES (%s, %s, CURDATE()) AS new_row
        ON DUPLICATE KEY UPDATE completed_at = new_row.completed_at
    """
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name, week))


def list_week_completions(anchor_name: str) -> Dict[int, date]:
    """返回 {week: completed_at} 字典。"""
    sql = """
        SELECT week, completed_at
        FROM sop_week_completion
        WHERE anchor_name = %s
    """
    with db_cursor() as cursor:
        cursor.execute(sql, (anchor_name,))
        return {row["week"]: row["completed_at"] for row in cursor.fetchall()}


# ============================================================
# 复合操作
# ============================================================

def advance_week(anchor_name: str) -> None:
    """本周达标，进入下一周。current_week 封顶 4；达到 4 时 status = '已完成'。"""
    with db_cursor() as cursor:
        # 查当前周
        cursor.execute(
            "SELECT current_week FROM sop_anchors WHERE anchor_name = %s",
            (anchor_name,),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(f"anchor not found: {anchor_name}")
        current_week = row["current_week"]

        # 标记本周完成
        cursor.execute(
            """
            INSERT INTO sop_week_completion (anchor_name, week, completed_at)
            VALUES (%s, %s, CURDATE()) AS new_row
            ON DUPLICATE KEY UPDATE completed_at = new_row.completed_at
            """,
            (anchor_name, current_week),
        )

        # 推进 current_week（封顶 4）；若 advance 调用时 current_week 已是 4，则把 status 标为"已完成"
        # 用 Python 变量 current_week（调用前的值）判断，避免 MySQL 在同一 UPDATE 里读到已修改的值
        new_status_expr = "已完成" if current_week >= 4 else None
        if new_status_expr is not None:
            cursor.execute(
                """
                UPDATE sop_anchors
                SET current_week = LEAST(current_week + 1, 4),
                    status = %s
                WHERE anchor_name = %s
                """,
                (new_status_expr, anchor_name),
            )
        else:
            cursor.execute(
                """
                UPDATE sop_anchors
                SET current_week = LEAST(current_week + 1, 4)
                WHERE anchor_name = %s
                """,
                (anchor_name,),
            )
