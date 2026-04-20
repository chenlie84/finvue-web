"""pytest 公共 fixture：SOP 表清理。

所有 SOP 集成测试共享一个 session 级 engine，
每个测试函数前后清空 sop_anchors（级联清空其它两表）。
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
    # sop_anchors 被 CASCADE 删除会带走子表，但显式删除顺序更清晰
    with db_cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("TRUNCATE TABLE sop_week_completion")
        cursor.execute("TRUNCATE TABLE sop_action_progress")
        cursor.execute("TRUNCATE TABLE sop_anchors")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
