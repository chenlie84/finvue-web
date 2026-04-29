"""MySQL data access helpers."""
from __future__ import annotations

import contextlib
from typing import Any, Iterator
from urllib.parse import unquote, urlparse

import pymysql
from pymysql.constants import CLIENT
from pymysql.cursors import DictCursor

import config


def _connection_kwargs(*, autocommit: bool = False, multi_statements: bool = False) -> dict[str, Any]:
    if config.MYSQL_URL:
        parsed = urlparse(config.MYSQL_URL)
        kwargs = {
            "host": parsed.hostname or "127.0.0.1",
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": parsed.path.lstrip("/"),
        }
    else:
        kwargs = {
            "host": config.MYSQL_HOST,
            "port": config.MYSQL_PORT,
            "user": config.MYSQL_USER,
            "password": config.MYSQL_PASSWORD,
            "database": config.MYSQL_DATABASE,
        }
    kwargs.update(
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=autocommit,
    )
    if multi_statements:
        kwargs["client_flag"] = CLIENT.MULTI_STATEMENTS
    return kwargs


def get_connection(*, autocommit: bool = False, multi_statements: bool = False):
    if not config.has_mysql_config():
        raise RuntimeError("MySQL is not configured")
    return pymysql.connect(**_connection_kwargs(autocommit=autocommit, multi_statements=multi_statements))


@contextlib.contextmanager
def cursor() -> Iterator[DictCursor]:
    conn = get_connection()
    try:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cur.close()
    finally:
        conn.close()


def fetch_one(sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(sql, args)
        return cur.fetchone()


def fetch_all(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with cursor() as cur:
        cur.execute(sql, args)
        return list(cur.fetchall())


def execute(sql: str, args: tuple[Any, ...] = ()) -> int:
    with cursor() as cur:
        return cur.execute(sql, args)
