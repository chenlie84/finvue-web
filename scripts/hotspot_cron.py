#!/usr/bin/env python3
"""
热搜定时任务脚本
用法: python scripts/hotspot_cron.py [--fetch] [--cleanup]

建议通过 cron 或 systemd timer 定时运行：
- 每 60 分钟执行抓取: python scripts/hotspot_cron.py --fetch
- 每天凌晨清理数据: python scripts/hotspot_cron.py --cleanup

cron 示例：
*/60 * * * * cd /srv/finvue/finvue-web && source .venv/bin/activate && python scripts/hotspot_cron.py --fetch
0 2 * * * cd /srv/finvue/finvue-web && source .venv/bin/activate && python scripts/hotspot_cron.py --cleanup
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import config
import migrate
import db


def run_fetch():
    """执行热搜抓取"""
    from services.hotspot_fetcher import sync_fetch_all_platforms

    print("[hotspot_cron] 开始抓取热搜...")

    # 获取配置的启用平台
    settings_row = db.fetch_one("SELECT enabled_platforms FROM finvue_hotspot_settings WHERE id = 'default'")
    platforms = None
    if settings_row:
        import json
        try:
            platforms = json.loads(settings_row.get("enabled_platforms") or "[]")
        except Exception:
            platforms = None

    result = sync_fetch_all_platforms(platforms)
    print(f"[hotspot_cron] 抓取完成: 共 {result.get('totalItems', 0)} 条")
    print(f"[hotspot_cron] 成功平台: {result.get('successPlatforms', [])}")
    if result.get('failedPlatforms'):
        print(f"[hotspot_cron] 失败平台: {result.get('failedPlatforms')}")

    return result


def run_cleanup():
    """执行数据清理"""
    from services.hotspot_fetcher import cleanup_old_data

    print("[hotspot_cron] 开始清理旧数据...")

    # 获取配置的保留天数
    settings_row = db.fetch_one("SELECT retention_days FROM finvue_hotspot_settings WHERE id = 'default'")
    retention_days = settings_row.get("retention_days") if settings_row else 30

    result = cleanup_old_data(retention_days)
    print(f"[hotspot_cron] 清理完成: 删除 {result.get('deleted', 0)} 条旧数据")

    return result


def main():
    parser = argparse.ArgumentParser(description="热搜定时任务")
    parser.add_argument("--fetch", action="store_true", help="执行热搜抓取")
    parser.add_argument("--cleanup", action="store_true", help="执行数据清理")
    parser.add_argument("--all", action="store_true", help="执行所有任务（抓取+清理）")

    args = parser.parse_args()

    if not args.fetch and not args.cleanup and not args.all:
        parser.print_help()
        sys.exit(1)

    # 检查 MySQL 配置
    if not config.has_mysql_config():
        print("[hotspot_cron] MySQL 未配置，无法执行")
        sys.exit(1)

    # 运行迁移
    print("[hotspot_cron] 检查数据库迁移...")
    migrate.run_migrations()

    results = {}

    if args.fetch or args.all:
        results["fetch"] = run_fetch()

    if args.cleanup or args.all:
        results["cleanup"] = run_cleanup()

    print("[hotspot_cron] 所有任务完成")
    return results


if __name__ == "__main__":
    main()