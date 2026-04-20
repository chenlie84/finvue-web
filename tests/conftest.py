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
    # 临时关闭外键检查以允许 TRUNCATE 父表（被 FK 引用的表无法 TRUNCATE）
    # try/finally 确保异常时也能恢复 FK 检查
    with db_cursor() as cursor:
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        try:
            cursor.execute("TRUNCATE TABLE sop_week_completion")
            cursor.execute("TRUNCATE TABLE sop_action_progress")
            cursor.execute("TRUNCATE TABLE sop_anchors")
        finally:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
