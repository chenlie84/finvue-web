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
            `今日填写客户数`,
            `距离目标gap`,
            `完成度`,
            `时间`
        FROM crs_tianxieshuju
        ORDER BY
            CASE WHEN `区域` = '合计' THEN 1 ELSE 0 END,
            `完成度` DESC
    """
    with db_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
    return rows


def fetch_customer_activity(customer_code: str | None = None) -> List[Dict]:
    """
    查询 cl_customer_activity 表，返回 customer_code, flag_activity, dt

    Args:
        customer_code: 可选, 按 customer_code 过滤
    """
    if customer_code:
        sql = """
            SELECT customer_code, flag_activity, dt
            FROM cl_customer_activity
            WHERE customer_code = %s
        """
        params = (customer_code,)
    else:
        sql = """
            SELECT customer_code, flag_activity, dt
            FROM cl_customer_activity
        """
        params = None

    with db_cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
    return rows
