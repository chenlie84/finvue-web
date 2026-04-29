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
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def _applied_filenames(cursor) -> set[str]:
    cursor.execute("SELECT filename FROM finvue_schema_migrations")
    return {row["filename"] for row in cursor.fetchall()}


def _pending_files(applied: set[str]) -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    return [path for path in sorted(MIGRATIONS_DIR.glob("*.sql")) if path.name not in applied]


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
                cursor.execute(path.read_text(encoding="utf-8"))
                while cursor.nextset():
                    pass
                cursor.execute("INSERT INTO finvue_schema_migrations (filename) VALUES (%s)", (path.name,))
                ran.append(path.name)
                print(f"[migrate] ✓ {path.name}")
            print(f"[migrate] 完成，共应用 {len(ran)} 个迁移")
            return ran
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
