"""Create or update the initial FinVue administrator account."""
from __future__ import annotations

import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import migrate  # noqa: E402
import security  # noqa: E402
import store  # noqa: E402


def main() -> None:
    username = security.normalize_username(os.environ.get("ADMIN_USERNAME") or "admin")
    password = os.environ.get("ADMIN_PASSWORD") or ""
    if not password:
        raise SystemExit("ADMIN_PASSWORD 未设置，无法初始化管理员")

    migrate.run_migrations()
    existing = store.get_user_by_username(username)
    if existing and existing.get("role") == "admin":
        print(f"[seed-admin] 管理员已存在：{username}")
        return

    salt, password_hash = security.hash_password(password)
    store.save_user(
        {
            "username": username,
            "role": "admin",
            "passwordSalt": salt,
            "passwordHash": password_hash,
        }
    )
    action = "更新为管理员" if existing else "创建管理员"
    print(f"[seed-admin] {action}：{username}")


if __name__ == "__main__":
    main()
