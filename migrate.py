"""FinVue MySQL migration runner, aligned with 直播带新SOP."""
from __future__ import annotations

from pathlib import Path

import pymysql

import config
import db


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sql" / "migrations"


def _ensure_tracking_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS finvue_schema_migrations (
            filename   VARCHAR(128) NOT NULL PRIMARY KEY,
            applied_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
        """
    )


def _applied_filenames(cursor) -> set[str]:
    cursor.execute("SELECT filename FROM finvue_schema_migrations")
    return {row["filename"] for row in cursor.fetchall()}


def _pending_files(applied: set[str]) -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.name not in applied]


def _remove_leading_comments(sql: str) -> str:
    """移除 SQL 开头的注释行，保留实际 SQL 语句."""
    lines = sql.split("\n")
    first_non_comment_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            first_non_comment_idx = i
            break
    return "\n".join(lines[first_non_comment_idx:]).strip()


def _execute_sql_with_error_handling(cursor, sql: str, filename: str) -> int:
    """执行SQL语句，处理索引已存在等错误."""
    statements = []
    for part in sql.split(";"):
        part = part.strip()
        if not part:
            continue
        # 移除开头的注释，保留实际 SQL
        clean_stmt = _remove_leading_comments(part)
        if clean_stmt:
            statements.append(clean_stmt)
    executed = 0

    for stmt in statements:
        if not stmt:
            continue
        try:
            cursor.execute(stmt)
            executed += 1
        except pymysql.err.MySQLError as e:
            # 跳过索引已存在错误 (1061) 和表已存在错误 (1050)
            if e.args[0] in (1061, 1050, 1068):  # Duplicate key name, Table exists, Multiple primary key
                print(f"[migrate] 跳过已存在对象: {stmt[:60]}...")
                continue
            # 其他错误需要抛出
            print(f"[migrate] SQL执行错误 {e.args[0]}: {e.args[1]}")
            raise

    return executed


def run_migrations() -> list[str]:
    if not config.has_mysql_config():
        print("[migrate] MySQL 未配置，跳过数据库迁移")
        return []
    conn = db.get_connection(autocommit=True, multi_statements=True)
    try:
        with conn.cursor() as cursor:
            _ensure_tracking_table(cursor)
            applied = _applied_filenames(cursor)
            pending = _pending_files(applied)
            if not pending:
                print("[migrate] 无待执行迁移")
                return []
            ran: list[str] = []
            for path in pending:
                print(f"[migrate] 执行 {path.name} ...")
                sql = path.read_text(encoding="utf-8")
                executed = _execute_sql_with_error_handling(cursor, sql, path.name)
                cursor.execute("INSERT INTO finvue_schema_migrations (filename) VALUES (%s)", (path.name,))
                ran.append(path.name)
                print(f"[migrate] ✓ {path.name} ({executed} 语句)")
            print(f"[migrate] 完成，共应用 {len(ran)} 个迁移")
            return ran
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
