import contextlib
from typing import Iterator, List, Dict

import pymysql

import config


def get_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


@contextlib.contextmanager
def db_cursor() -> Iterator[pymysql.cursors.Cursor]:
    conn = get_connection()
    try:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()
    finally:
        conn.close()


def fetch_all_rows() -> List[Dict]:
    sql = """
        SELECT
            `区域`,
            `目标填写客户数`,
            `总填写客户数`,
            `上传资产证明图片客户数`,
            `今日填写客户数`,
            `距离目标gap`,
            `填写销售数`,
            `完成度`
        FROM crs_tianxieshuju
        ORDER BY
            CASE WHEN `区域` = '合计' THEN 1 ELSE 0 END,
            `完成度` DESC
    """
    with db_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
    return rows
