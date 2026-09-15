#!/usr/bin/env python3
"""
一体化脚本：导出本地数据 + 导入/更新线上数据库
用法:
  python export_and_import.py --export-only    仅导出CSV
  python export_and_import.py --import-only    仅导入CSV到线上（更新已有数据）
  python export_and_import.py --truncate       清空线上表后再导入
  python export_and_import.py --full           完整流程：导出 + 导入更新
"""

import csv
import os
import sys
import hashlib
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import pymysql


def _load_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env()


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


# ============== 数据库配置（从环境变量读取） ==============

LOCAL_DB = {
    "host": _env("MYSQL_HOST", "127.0.0.1"),
    "port": int(_env("MYSQL_PORT", "3306")),
    "user": _env("MYSQL_USER", "root"),
    "password": _env("MYSQL_PASSWORD"),
    "database": _env("MYSQL_DATABASE", "finvue"),
    "charset": "utf8mb4",
}

REMOTE_DB = {
    "host": _env("DOUYIN_DB_HOST"),
    "port": int(_env("DOUYIN_DB_PORT", "3306")),
    "user": _env("DOUYIN_DB_USER", "root"),
    "password": _env("DOUYIN_DB_PASSWORD"),
    "database": _env("DOUYIN_DB_DATABASE", "demo"),
    "charset": "utf8mb4",
    "connect_timeout": 30,
}

PRODUCTION_DB = {
    "host": _env("PRODUCTION_DB_HOST"),
    "port": int(_env("PRODUCTION_DB_PORT", "3337")),
    "database": _env("PRODUCTION_DB_DATABASE"),
    "user": _env("PRODUCTION_DB_USER"),
    "password": _env("PRODUCTION_DB_PASSWORD"),
    "charset": "utf8mb4",
    "connect_timeout": 30,
}

OUTPUT_DIR = _env("DATA_OUTPUT_DIR") or str(Path(__file__).resolve().parent / "10-data")

# 线上表名映射
TABLE_NAMES = {
    "customer_profile": "finvue_customer_profiles",
    "customer_session": "finvue_customer_sessions",
    "live": "finvue_operation_live_stats",
}

# ============== 工具函数 ==============

def format_beijing_time(dt):
    """将时间转换为北京时间 (UTC+8)"""
    if not dt: return ""
    # 如果是字符串，先解析成 datetime
    if isinstance(dt, str):
        try:
            dt = datetime.strptime(dt.strip(), "%Y-%m-%d %H:%M:%S")
        except:
            return dt  # 解析失败直接返回
    # 加8小时转换为北京时间
    beijing = dt + timedelta(hours=8)
    return beijing.strftime("%Y-%m-%d %H:%M:%S")

def csv_escape(val):
    if val is None: return ""
    if isinstance(val, (dict, list)):
        return '"' + json.dumps(val).replace('"', '""') + '"'
    return '"' + str(val).replace('"', '""').replace('\n', '') + '"'

def parse_number(value):
    if not value: return None
    value = str(value).strip().replace("%", "").replace(",", "")
    try:
        return float(value) if "." in value else int(value)
    except: return None

def parse_datetime(value):
    if not value: return None
    value = str(value).strip()
    for fmt in ["%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d", "%Y/%m/%d"]:
        try: return datetime.strptime(value, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except: continue
    return None

def generate_id(*args):
    return hashlib.md5("_".join(str(a) for a in args).encode()).hexdigest()[:19]

# ============== 清空表函数 ==============

def truncate_tables():
    """清空线上数据库的三个表"""
    print("\n>>> 清空线上表...")
    print(f"  目标: {PRODUCTION_DB['host']}:{PRODUCTION_DB['port']}/{PRODUCTION_DB['database']}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    try:
        cursor = conn.cursor()
        
        for table_type, table_name in TABLE_NAMES.items():
            # 先查询当前数据量
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count_before = cursor.fetchone()[0]
            
            # TRUNCATE 清空表
            cursor.execute(f"TRUNCATE TABLE {table_name}")
            
            print(f"  ✅ {table_name}: 清空 {count_before} 条")
        
        conn.commit()
        cursor.close()
        print("\n  所有表已清空!")
    except Exception as e:
        print(f"  ❌ 清空失败: {e}")
        return False
    finally:
        conn.close()
    
    return True

# ============== 导出函数 ==============

def export_customer_profiles():
    print("\n[1/3] 导出 customer_profiles...")
    conn = pymysql.connect(**LOCAL_DB)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT customer_id, customer_name, latest_anchor_name, latest_analyzed_at, latest_live_theme, latest_rank, best_rank, avg_watch_seconds, labels, tags FROM customer_profiles ORDER BY updated_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        print(f"  查询结果: {len(rows)} 条")
        output_path = f"{OUTPUT_DIR}/customer_profiles_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("客户ID,客户姓名,主播名称,分析时间,直播主题,排名,最高排名,平均观看时长,标签,标记\n")
            for r in rows:
                labels = json.dumps(r[8]) if r[8] and not isinstance(r[8], str) else (r[8] or "[]")
                tags = json.dumps(r[9]) if r[9] and not isinstance(r[9], str) else (r[9] or "[]")
                f.write(f"{r[0] or ''},{csv_escape(r[1])},{csv_escape(r[2])},{format_beijing_time(r[3])},{csv_escape(r[4])},{r[5] or 0},{r[6] or 0},{r[7] or 0},{csv_escape(labels)},{csv_escape(tags)}\n")
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        return {"count": len(rows), "path": output_path, "size": size_mb}
    finally: conn.close()

def export_customer_sessions():
    print("\n[2/3] 导出 customer_sessions...")
    conn = pymysql.connect(**LOCAL_DB)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, customer_id, anchor_name, room_id, live_theme, report_type, metric_type, metric_value, watch_rank, watch_duration_seconds, analyzed_at, source_file FROM customer_sessions ORDER BY analyzed_at DESC")
        rows = cursor.fetchall()
        cursor.close()
        print(f"  查询结果: {len(rows)} 条")
        output_path = f"{OUTPUT_DIR}/customer_sessions_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("会话ID,客户ID,主播名称,直播间ID,直播主题,报告类型,指标类型,指标值,观看排名,观看时长,分析时间,来源文件\n")
            for r in rows:
                f.write(f"{r[0] or ''},{r[1] or ''},{csv_escape(r[2])},{r[3] or ''},{csv_escape(r[4])},{r[5] or ''},{r[6] or ''},{r[7] or ''},{r[8] or 0},{r[9] or 0},{format_beijing_time(r[10])},{csv_escape(r[11])}\n")
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        return {"count": len(rows), "path": output_path, "size": size_mb}
    finally: conn.close()

def export_live_data():
    print("\n[3/3] 导出 live_data...")
    conn = pymysql.connect(**REMOTE_DB)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT account, room_id, title, startTime, endTime, duration, pcu, acu, earnScore, fansEarnScore, nonFansEarnScore, consumeUcnt, fansConsumeUcnt, nonFansConsumeUcnt, showUcnt, watchUcnt, fansWatchUcnt, nonFansWatchUcnt, followUcnt, unfollowUcnt, joinFansClubUcnt, avgWatchDuration, fansAvgWatchDuration, nonFansAvgWatchDuration, commentUcnt, fansCommentUcnt, nonFansCommentUcnt, likeCnt, fansLikeCnt, nonFansLikeCnt, shareCnt, fansShareCnt, nonFansShareCnt FROM douyin_creator_live_overview ORDER BY startTime DESC")
        rows = cursor.fetchall()
        cursor.close()
        print(f"  查询结果: {len(rows)} 条")
        output_path = f"{OUTPUT_DIR}/live_data_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("主播账号,直播间ID,直播标题,开播时间,关播时间,直播时长,峰值在线人数,平均在线人数,收入积分,粉丝收入积分,非粉收入积分,付费人数,粉丝付费人数,非粉付费人数,曝光人数,观看人数,观看粉丝人数,观看非粉人数,涨粉人数,掉粉人数,加入粉丝团人数,人均停留时长,粉丝人均停留时长,非粉人均停留时长,评论人数,粉丝评论人数,非粉评论人数,点赞次数,粉丝点赞次数,非粉点赞次数,分享次数,粉丝分享次数,非粉分享次数\n")
            for r in rows:
                vals = [csv_escape(r[0]), r[1] or "", csv_escape(r[2]), format_beijing_time(r[3]), format_beijing_time(r[4])] + [str(r[i] or 0) for i in range(5, 33)]
                f.write(",".join(vals) + "\n")
        size_kb = round(len(open(output_path).read()) / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_kb} KB)")
        anchor_stats = {}
        for r in rows: anchor_stats[r[0] or "未知"] = anchor_stats.get(r[0] or "未知", 0) + 1
        print("\n=== 各主播直播场次 ===")
        for name, count in sorted(anchor_stats.items(), key=lambda x: -x[1]): print(f"  {name}: {count}场")
        return {"count": len(rows), "path": output_path, "size": size_kb}
    finally: conn.close()

# ============== 导入函数 ==============

def import_to_production(csv_path, table_type, skip_check=False):
    """导入数据到线上数据库
    skip_check: True 时跳过重复检查（用于清空后导入）
    """
    print(f"\n导入 {table_type} 到线上...")
    print(f"  CSV: {csv_path}")
    print(f"  目标: {PRODUCTION_DB['host']}:{PRODUCTION_DB['port']}/{PRODUCTION_DB['database']}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    inserted, skipped, errors = 0, 0, []
    
    try:
        cursor = conn.cursor()
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    if table_type == "customer_profile":
                        customer_id = str(row.get("客户ID") or "").strip()
                        if not customer_id: skipped += 1; continue
                        customer_name = str(row.get("客户姓名") or customer_id).strip()
                        data = {"customer_id": customer_id, "customer_name": customer_name, "labels": "[]", "tags": "[]", "raw": "{}"}
                        
                        if row.get("主播名称"): data["latest_anchor_name"] = str(row.get("主播名称")).strip()
                        if parse_datetime(row.get("分析时间")): data["latest_analyzed_at"] = parse_datetime(row.get("分析时间"))
                        if row.get("直播主题"): data["latest_live_theme"] = str(row.get("直播主题")).strip()
                        if parse_number(row.get("排名")): data["latest_rank"] = int(parse_number(row.get("排名")))
                        if parse_number(row.get("最高排名")): data["best_rank"] = int(parse_number(row.get("最高排名")))
                        if parse_number(row.get("平均观看时长")): data["avg_watch_seconds"] = int(parse_number(row.get("平均观看时长")))
                        
                        if not skip_check:
                            cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                            if cursor.fetchone(): skipped += 1; continue
                        
                        cursor.execute(f"INSERT INTO finvue_customer_profiles ({','.join(data.keys())}) VALUES ({','.join(['%s']*len(data))})", list(data.values()))
                        inserted += 1
                    
                    elif table_type == "customer_session":
                        customer_id = str(row.get("客户ID") or "").strip()
                        if not customer_id: skipped += 1; continue
                        
                        if not skip_check:
                            cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                            if not cursor.fetchone(): skipped += 1; continue
                        
                        session_id = str(row.get("会话ID") or "").strip()
                        anchor = str(row.get("主播名称") or "").strip()
                        analyzed = parse_datetime(row.get("分析时间")) or ""
                        if not session_id: session_id = generate_id(customer_id, anchor, analyzed)
                        
                        data = {"session_id": session_id, "customer_id": customer_id, "raw": "{}"}
                        if anchor: data["anchor_name"] = anchor
                        if row.get("直播间ID"): data["room_id"] = str(row.get("直播间ID")).strip()
                        if row.get("直播主题"): data["live_theme"] = str(row.get("直播主题")).strip()
                        if row.get("报告类型"): data["report_type"] = str(row.get("报告类型")).strip()
                        if row.get("指标类型"): data["metric_type"] = str(row.get("指标类型")).strip()
                        if row.get("指标值"): data["metric_value"] = str(row.get("指标值")).strip()
                        if parse_number(row.get("观看排名")): data["watch_rank"] = int(parse_number(row.get("观看排名")))
                        if parse_number(row.get("观看时长")): data["watch_duration_seconds"] = int(parse_number(row.get("观看时长")))
                        if analyzed: data["analyzed_at"] = analyzed
                        if row.get("来源文件"): data["source_file"] = str(row.get("来源文件")).strip()
                        
                        if not skip_check:
                            cursor.execute("SELECT session_id FROM finvue_customer_sessions WHERE session_id = %s", (session_id,))
                            if cursor.fetchone(): skipped += 1; continue
                        
                        cursor.execute(f"INSERT INTO finvue_customer_sessions ({','.join(data.keys())}) VALUES ({','.join(['%s']*len(data))})", list(data.values()))
                        inserted += 1
                    
                    elif table_type == "live":
                        account = str(row.get("主播账号") or "").strip()
                        room_id = str(row.get("直播间ID") or "").strip()
                        if not account: skipped += 1; continue
                        start_time = parse_datetime(row.get("开播时间"))
                        if not room_id and start_time: room_id = generate_id(account, start_time)
                        if not room_id: skipped += 1; continue
                        
                        data = {"account": account, "room_id": room_id}
                        if row.get("直播标题"): data["title"] = str(row.get("直播标题")).strip()
                        if start_time: data["start_time"] = start_time
                        if parse_datetime(row.get("关播时间")): data["end_time"] = parse_datetime(row.get("关播时间"))
                        if parse_number(row.get("直播时长")): data["duration"] = int(parse_number(row.get("直播时长")))
                        
                        num_map = {"峰值在线人数":"pcu","平均在线人数":"acu","曝光人数":"show_ucnt","观看人数":"watch_ucnt","观看粉丝人数":"fans_watch_ucnt","观看非粉人数":"non_fans_watch_ucnt","涨粉人数":"follow_ucnt","掉粉人数":"unfollow_ucnt","加入粉丝团人数":"join_fansclub_ucnt","评论人数":"comment_ucnt","粉丝评论人数":"fans_comment_ucnt","非粉评论人数":"non_fans_comment_ucnt","点赞次数":"like_cnt","粉丝点赞次数":"fans_like_cnt","非粉点赞次数":"non_fans_like_cnt","分享次数":"share_cnt","粉丝分享次数":"fans_share_cnt","非粉分享次数":"non_fans_share_cnt","付费人数":"consume_ucnt","粉丝付费人数":"fans_consume_ucnt","非粉付费人数":"non_fans_consume_ucnt","收入积分":"earn_score","粉丝收入积分":"fans_earn_score","非粉收入积分":"non_fans_earn_score"}
                        for csv_f, db_f in num_map.items():
                            if parse_number(row.get(csv_f)): data[db_f] = int(parse_number(row.get(csv_f)))
                        
                        dur_map = {"人均停留时长":"avg_watch_duration","粉丝人均停留时长":"fans_avg_watch_duration","非粉人均停留时长":"non_fans_avg_watch_duration"}
                        for csv_f, db_f in dur_map.items():
                            if parse_number(row.get(csv_f)): data[db_f] = parse_number(row.get(csv_f))
                        
                        if not skip_check:
                            cursor.execute("SELECT id FROM finvue_operation_live_stats WHERE room_id = %s", (room_id,))
                            if cursor.fetchone(): skipped += 1; continue
                        
                        cursor.execute(f"INSERT INTO finvue_operation_live_stats ({','.join(data.keys())}) VALUES ({','.join(['%s']*len(data))})", list(data.values()))
                        inserted += 1
                    
                    if inserted % 1000 == 0:
                        print(f"  进度: 已导入 {inserted} 条...")
                        conn.commit()
                except Exception as e:
                    errors.append(str(e))
                    if len(errors) <= 10: print(f"  错误: {e}")
        
        conn.commit()
        cursor.close()
    except Exception as e:
        print(f"  连接错误: {e}")
        return {"imported": 0, "skipped": 0, "errors": [str(e)]}
    finally: conn.close()
    
    print(f"\n  导入结果: 成功 {inserted} 条, 跳过 {skipped} 条")
    return {"imported": inserted, "skipped": skipped, "errors": errors}

# ============== 主函数 ==============

def main():
    parser = argparse.ArgumentParser(description="导出本地数据 + 导入线上数据库")
    parser.add_argument("--export-only", action="store_true", help="仅导出CSV")
    parser.add_argument("--import-only", action="store_true", help="仅导入CSV到线上（跳过已存在）")
    parser.add_argument("--truncate", action="store_true", help="清空线上表后再导入")
    parser.add_argument("--full", action="store_true", help="完整流程：导出 + 导入更新")
    args = parser.parse_args()
    
    print("=" * 60)
    print("一体化脚本：导出 + 导入")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # 导出阶段
    if args.export_only or args.truncate or args.full:
        print("\n>>> 导出阶段")
        results["profiles"] = export_customer_profiles()
        results["sessions"] = export_customer_sessions()
        results["live"] = export_live_data()
    
    # 清空表
    if args.truncate:
        if not truncate_tables():
            print("\n❌ 清空表失败，终止导入")
            return
    
    # 导入阶段
    if args.import_only or args.truncate or args.full:
        print("\n>>> 导入阶段")
        csv_files = {
            "profiles": f"{OUTPUT_DIR}/customer_profiles_export.csv",
            "sessions": f"{OUTPUT_DIR}/customer_sessions_export.csv",
            "live": f"{OUTPUT_DIR}/live_data_export.csv"
        }
        
        # truncate 模式跳过重复检查
        skip_check = args.truncate
        
        results["import_profiles"] = import_to_production(csv_files["profiles"], "customer_profile", skip_check)
        results["import_sessions"] = import_to_production(csv_files["sessions"], "customer_session", skip_check)
        results["import_live"] = import_to_production(csv_files["live"], "live", skip_check)
    
    # 总结
    print("\n" + "=" * 60)
    print("✅ 执行完成！")
    print("=" * 60)
    
    if args.export_only or args.truncate or args.full:
        print("\n导出结果:")
        print(f"  customer_profiles_export.csv: {results['profiles']['count']} 条 ({results['profiles']['size']} MB)")
        print(f"  customer_sessions_export.csv: {results['sessions']['count']} 条 ({results['sessions']['size']} MB)")
        print(f"  live_data_export.csv: {results['live']['count']} 条 ({results['live']['size']} KB)")
    
    if args.import_only or args.truncate or args.full:
        print("\n导入结果:")
        ip = results['import_profiles']
        print(f"  客户档案: 成功 {ip['imported']} 条, 跳过 {ip['skipped']} 条")
        iss = results['import_sessions']
        print(f"  客户会话: 成功 {iss['imported']} 条, 跳过 {iss['skipped']} 条")
        il = results['import_live']
        print(f"  直播数据: 成功 {il['imported']} 条, 跳过 {il['skipped']} 条")

if __name__ == "__main__":
    main()
