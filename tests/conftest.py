"""pytest 公共 fixture：SOP 表清理。

每个测试函数前后 TRUNCATE SOP 三张表，
通过 db_utils.db_cursor() 直接操作本地 DEV MySQL。
"""
import pytest

from db_utils import db_cursor


@pytest.fixture(autouse=True)
def clean_sop_tables():
    """每个测试前后清空 SOP 三张表。"""
    _truncate_all()
    yield
    _truncate_all()


def _truncate_all():
    # 顺序：子表先（避免触发 FK 约束），父表后
    with db_cursor() as cursor:
        cursor.execute("TRUNCATE TABLE sop_week_completion")
        cursor.execute("TRUNCATE TABLE sop_action_progress")
        cursor.execute("TRUNCATE TABLE sop_anchors")
