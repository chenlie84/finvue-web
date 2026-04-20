"""数据库迁移运行器。

使用方式：
- 自动：应用启动时由 main.py 的 startup 事件调用 run_migrations()
- 手动：`python migrate.py` 直接执行

约定：
- 所有迁移文件放在 sql/migrations/ 下
- 文件名用时间戳 + 序号前缀，按字典序即为执行顺序
  例：20260420_001_init.sql、20260505_002_add_xxx.sql
- 每个文件内多条 SQL 用 ; 分隔（支持 -- 行注释）
- 已应用的迁移记录在 schema_migrations 表里，再次启动自动跳过
"""
from pathlib import Path

import pymysql

import config


MIGRATIONS_DIR = Path(__file__).resolve().parent / "sql" / "migrations"


def _connect():
    """专用连接：开启 MULTI_STATEMENTS 以便一次执行多条 DDL。"""
    return pymysql.connect(
        host=config.MYSQL_HOST,
        port=config.MYSQL_PORT,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASSWORD,
        database=config.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        client_flag=pymysql.constants.CLIENT.MULTI_STATEMENTS,
    )


def _ensure_tracking_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename    VARCHAR(128) NOT NULL PRIMARY KEY,
            applied_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
        """
    )


def _applied_filenames(cursor) -> set[str]:
    cursor.execute("SELECT filename FROM schema_migrations")
    return {row[0] for row in cursor.fetchall()}


def _pending_files(applied: set[str]) -> list[Path]:
    if not MIGRATIONS_DIR.exists():
        return []
    all_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return [f for f in all_files if f.name not in applied]


def run_migrations() -> list[str]:
    """应用所有未执行的迁移。返回本次跑过的文件名列表。"""
    conn = _connect()
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
                sql_text = path.read_text(encoding="utf-8")
                cursor.execute(sql_text)
                # MULTI_STATEMENTS 下必须消费所有结果集
                while cursor.nextset():
                    pass
                cursor.execute(
                    "INSERT INTO schema_migrations (filename) VALUES (%s)",
                    (path.name,),
                )
                ran.append(path.name)
                print(f"[migrate] ✓ {path.name}")

            print(f"[migrate] 完成，共应用 {len(ran)} 个迁移")
            return ran
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
