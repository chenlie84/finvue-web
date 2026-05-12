#!/usr/bin/env python3
"""
一体化脚本：导出本地数据 + 导入线上数据库
用法:
  python export_and_import.py --export-only    仅导出CSV
  python export_and_import.py --import-only    仅导入CSV到线上
  python export_and_import.py --full           完整流程：导出 + 导入
"""

import csv
import sys
import hashlib
import json
import argparse
from datetime import datetime, timedelta
import pymysql

# ============== 数据库配置 ==============

LOCAL_DB = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "root",
    "password": "Python3.8",
    "database": "finvue",
    "charset": "utf8mb4",
}

REMOTE_DB = {
    "host": "10.170.32.218",
    "port": 3306,
    "user": "root",
    "password": "Python3.8",
    "database": "demo",
    "charset": "utf8mb4",
    "connect_timeout": 30,
}

PRODUCTION_DB = {
    "host": "mysql0200.3337-wm.db.idc",
    "port": 3337,
    "database": "process_analysis",
    "user": "process_analysis",
    "password": "ns7ubvy96ncHncOTOeHS",
    "charset": "utf8mb4",
    "connect_timeout": 30,
}

OUTPUT_DIR = "/Users/beeerjack/Desktop/develop/finvue-web"

# ============== 工具函数 ==============

def format_beijing_time(dt):
    """格式化北京时间"""
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    beijing = dt + timedelta(hours=8)
    return beijing.strftime("%Y-%m-%d %H:%M:%S")

def csv_escape(val):
    """CSV 转义"""
    if val is None:
        return ""
    if isinstance(val, (dict, list)):
        return '"' + json.dumps(val).replace('"', '""') + '"'
    val = str(val)
    return '"' + val.replace('"', '""').replace('\n', '') + '"'

def parse_number(value):
    """解析数字"""
    if not value:
        return None
    value = str(value).strip().replace("%", "").replace(",", "")
    try:
        if "." in value:
            return float(value)
        return int(value)
    except:
        return None

def parse_datetime(value):
    """解析日期时间"""
    if not value:
        return None
    value = str(value).strip()
    formats = [
        "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y-%m-%d", "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d %H:%M:%S")
        except:
            continue
    return None

def generate_id(*args):
    """生成唯一ID"""
    key = "_".join(str(a) for a in args)
    return hashlib.md5(key.encode()).hexdigest()[:19]

# ============== 导出函数 ==============

def export_customer_profiles():
    """导出客户档案"""
    print("\n[1/3] 导出 customer_profiles...")
    
    conn = pymysql.connect(**LOCAL_DB)
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                customer_id, customer_name, latest_anchor_name,
                latest_analyzed_at, latest_live_theme,
                latest_rank, best_rank, avg_watch_seconds, labels, tags
            FROM customer_profiles ORDER BY updated_at DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        
        print(f"  查询结果: {len(rows)} 条")
        
        output_path = f"{OUTPUT_DIR}/customer_profiles_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("客户ID,客户姓名,主播名称,分析时间,直播主题,排名,最高排名,平均观看时长,标签,标记\n")
            for r in rows:
                labels = r[8] if r[8] else "[]"
                tags = r[9] if r[9] else "[]"
                if not isinstance(labels, str):
                    labels = json.dumps(labels)
                if not isinstance(tags, str):
                    tags = json.dumps(tags)
                f.write(",".join([
                    str(r[0] or ""), csv_escape(r[1]), csv_escape(r[2]),
                    format_beijing_time(r[3]), csv_escape(r[4]),
                    str(r[5] or 0), str(r[6] or 0), str(r[7] or 0),
                    csv_escape(labels), csv_escape(tags)
                ]) + "\n")
        
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        return {"count": len(rows), "path": output_path, "size": size_mb}
    finally:
        conn.close()


def export_customer_sessions():
    """导出客户会话"""
    print("\n[2/3] 导出 customer_sessions...")
    
    conn = pymysql.connect(**LOCAL_DB)
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                session_id, customer_id, anchor_name, room_id,
                live_theme, report_type, metric_type, metric_value,
                watch_rank, watch_duration_seconds, analyzed_at, source_file
            FROM customer_sessions ORDER BY analyzed_at DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        
        print(f"  查询结果: {len(rows)} 条")
        
        output_path = f"{OUTPUT_DIR}/customer_sessions_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("会话ID,客户ID,主播名称,直播间ID,直播主题,报告类型,指标类型,指标值,观看排名,观看时长,分析时间,来源文件\n")
            for r in rows:
                f.write(",".join([
                    str(r[0] or ""), str(r[1] or ""), csv_escape(r[2]),
                    str(r[3] or ""), csv_escape(r[4]), str(r[5] or ""),
                    str(r[6] or ""), str(r[7] or ""), str(r[8] or 0),
                    str(r[9] or 0), format_beijing_time(r[10]), csv_escape(r[11])
                ]) + "\n")
        
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        return {"count": len(rows), "path": output_path, "size": size_mb}
    finally:
        conn.close()


def export_live_data():
    """导出直播数据"""
    print("\n[3/3] 导出 live_data...")
    
    conn = pymysql.connect(**REMOTE_DB)
    
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                account, room_id, title, startTime, endTime, duration,
                pcu, acu, earnScore, fansEarnScore, nonFansEarnScore,
                consumeUcnt, fansConsumeUcnt, nonFansConsumeUcnt,
                showUcnt, watchUcnt, fansWatchUcnt, nonFansWatchUcnt,
                followUcnt, unfollowUcnt, joinFansClubUcnt,
                avgWatchDuration, fansAvgWatchDuration, nonFansAvgWatchDuration,
                commentUcnt, fansCommentUcnt, nonFansCommentUcnt,
                likeCnt, fansLikeCnt, nonFansLikeCnt,
                shareCnt, fansShareCnt, nonFansShareCnt
            FROM douyin_creator_live_overview ORDER BY startTime DESC
        """)
        rows = cursor.fetchall()
        cursor.close()
        
        print(f"  查询结果: {len(rows)} 条")
        
        output_path = f"{OUTPUT_DIR}/live_data_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("主播账号,直播间ID,直播标题,开播时间,关播时间,直播时长,峰值在线人数,平均在线人数,收入积分,粉丝收入积分,非粉收入积分,付费人数,粉丝付费人数,非粉付费人数,曝光人数,观看人数,观看粉丝人数,观看非粉人数,涨粉人数,掉粉人数,加入粉丝团人数,人均停留时长,粉丝人均停留时长,非粉人均停留时长,评论人数,粉丝评论人数,非粉评论人数,点赞次数,粉丝点赞次数,非粉点赞次数,分享次数,粉丝分享次数,非粉分享次数\n")
            for r in rows:
                f.write(",".join([
                    csv_escape(r[0]), str(r[1] or ""), csv_escape(r[2]),
                    format_beijing_time(r[3]), format_beijing_time(r[4]),
                    str(r[5] or 0), str(r[6] or 0), str(r[7] or 0),
                    str(r[8] or 0), str(r[9] or 0), str(r[10] or 0),
                    str(r[11] or 0), str(r[12] or 0), str(r[13] or 0),
                    str(r[14] or 0), str(r[15] or 0), str(r[16] or 0),
                    str(r[17] or 0), str(r[18] or 0), str(r[19] or 0),
                    str(r[20] or 0), str(r[21] or 0), str(r[22] or 0),
                    str(r[23] or 0), str(r[24] or 0), str(r[25] or 0),
                    str(r[26] or 0), str(r[27] or 0), str(r[28] or 0),
                    str(r[29] or 0), str(r[30] or 0), str(r[31] or 0),
                    str(r[32] or 0)
                ]) + "\n")
        
        size_kb = round(len(open(output_path).read()) / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_kb} KB)")
        
        anchor_stats = {}
        for r in rows:
            name = r[0] or "未知"
            anchor_stats[name] = anchor_stats.get(name, 0) + 1
        print("\n=== 各主播直播场次 ===")
        for name, count in sorted(anchor_stats.items(), key=lambda x: -x[1]):
            print(f"  {name}: {count}场")
        
        return {"count": len(rows), "path": output_path, "size": size_kb}
    finally:
        conn.close()


# ============== 导入函数 ==============

def import_to_production(csv_path, table_type):
    """导入数据到线上数据库"""
    print(f"\n导入 {table_type} 到线上...")
    print(f"  CSV: {csv_path}")
    print(f"  目标: {PRODUCTION_DB['host']}:{PRODUCTION_DB['port']}/{PRODUCTION_DB['database']}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    imported, skipped, errors = 0, 0, []
    
    try:
        cursor = conn.cursor()
        
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    if table_type == "customer_profile":
                        customer_id = str(row.get("客户ID") or "").strip()
                        if not customer_id:
                            skipped += 1
                            continue
                        
                        cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                        if cursor.fetchone():
                            skipped += 1
                            continue
                        
                        customer_name = str(row.get("客户姓名") or customer_id).strip()
                        data = {
                            "customer_id": customer_id,
                            "customer_name": customer_name,
                            "labels": "[]",
                            "tags": "[]",
                            "raw": "{}"
                        }
                        
                        anchor = str(row.get("主播名称") or "").strip()
                        if anchor: data["latest_anchor_name"] = anchor
                        
                        analyzed = parse_datetime(row.get("分析时间"))
                        if analyzed: data["latest_analyzed_at"] = analyzed
                        
                        theme = str(row.get("直播主题") or "").strip()
                        if theme: data["latest_live_theme"] = theme
                        
                        rank = parse_number(row.get("排名"))
                        if rank: data["latest_rank"] = int(rank)
                        
                        best = parse_number(row.get("最高排名"))
                        if best: data["best_rank"] = int(best)
                        
                        avg_watch = parse_number(row.get("平均观看时长"))
                        if avg_watch: data["avg_watch_seconds"] = int(avg_watch)
                        
                        table = "finvue_customer_profiles"
                    
                    elif table_type == "customer_session":
                        customer_id = str(row.get("客户ID") or "").strip()
                        if not customer_id:
                            skipped += 1
                            continue
                        
                        cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                        if not cursor.fetchone():
                            skipped += 1
                            continue
                        
                        session_id = str(row.get("会话ID") or "").strip()
                        anchor = str(row.get("主播名称") or "").strip()
                        analyzed = parse_datetime(row.get("分析时间")) or ""
                        
                        if not session_id:
                            session_id = generate_id(customer_id, anchor, analyzed)
                        
                        cursor.execute("SELECT session_id FROM finvue_customer_sessions WHERE session_id = %s", (session_id,))
                        if cursor.fetchone():
                            skipped += 1
                            continue
                        
                        data = {"session_id": session_id, "customer_id": customer_id, "raw": "{}"}
                        
                        if anchor: data["anchor_name"] = anchor
                        room = str(row.get("直播间ID") or "").strip()
                        if room: data["room_id"] = room
                        theme = str(row.get("直播主题") or "").strip()
                        if theme: data["live_theme"] = theme
                        report = str(row.get("报告类型") or "").strip()
                        if report: data["report_type"] = report
                        metric = str(row.get("指标类型") or "").strip()
                        if metric: data["metric_type"] = metric
                        value = str(row.get("指标值") or "").strip()
                        if value: data["metric_value"] = value
                        rank = parse_number(row.get("观看排名"))
                        if rank: data["watch_rank"] = int(rank)
                        duration = parse_number(row.get("观看时长"))
                        if duration: data["watch_duration_seconds"] = int(duration)
                        if analyzed: data["analyzed_at"] = analyzed
                        source = str(row.get("来源文件") or "").strip()
                        if source: data["source_file"] = source
                        
                        table = "finvue_customer_sessions"
                    
                    elif table_type == "live":
                        account = str(row.get("主播账号") or "").strip()
                        room_id = str(row.get("直播间ID") or "").strip()
                        
                        if not account:
                            skipped += 1
                            continue
                        
                        start_time = parse_datetime(row.get("开播时间"))
                        if not room_id and start_time:
                            room_id = generate_id(account, start_time)
                        if not room_id:
                            skipped += 1
                            continue
                        
                        cursor.execute("SELECT id FROM finvue_operation_live_stats WHERE room_id = %s", (room_id,))
                        if cursor.fetchone():
                            skipped += 1
                            continue
                        
                        data = {"account": account, "room_id": room_id}
                        
                        title = str(row.get("直播标题") or "").strip()
                        if title: data["title"] = title
                        if start_time: data["start_time"] = start_time
                        end_time = parse_datetime(row.get("关播时间"))
                        if end_time: data["end_time"] = end_time
                        duration = parse_number(row.get("直播时长"))
                        if duration: data["duration"] = int(duration)
                        
                        # 人数字段
                        field_map = {
                            "峰值在线人数": "pcu", "平均在线人数": "acu",
                            "曝光人数": "show_ucnt", "观看人数": "watch_ucnt",
                            "观看粉丝人数": "fans_watch_ucnt", "观看非粉人数": "non_fans_watch_ucnt",
                            "涨粉人数": "follow_ucnt", "掉粉人数": "unfollow_ucnt",
                            "加入粉丝团人数": "join_fansclub_ucnt", "评论人数": "comment_ucnt",
                            "粉丝评论人数": "fans_comment_ucnt", "非粉评论人数": "non_fans_comment_ucnt",
                            "点赞次数": "like_cnt", "粉丝点赞次数": "fans_like_cnt",
                            "非粉点赞次数": "non_fans_like_cnt", "分享次数": "share_cnt",
                            "粉丝分享次数": "fans_share_cnt", "非粉分享次数": "non_fans_share_cnt",
                            "付费人数": "consume_ucnt", "粉丝付费人数": "fans_consume_ucnt",
                            "非粉付费人数": "non_fans_consume_ucnt", "收入积分": "earn_score",
                            "粉丝收入积分": "fans_earn_score", "非粉收入积分": "non_fans_earn_score"
                        }
                        for csv_field, db_field in field_map.items():
                            val = parse_number(row.get(csv_field))
                            if val: data[db_field] = int(val)
                        
                        # 时长字段
                        duration_map = {
                            "人均停留时长": "avg_watch_duration",
                            "粉丝人均停留时长": "fans_avg_watch_duration",
                            "非粉人均停留时长": "non_fans_avg_watch_duration"
                        }
                        for csv_field, db_field in duration_map.items():
                            val = parse_number(row.get(csv_field))
                            if val: data[db_field] = val
                        
                        table = "finvue_operation_live_stats"
                    
                    # 插入数据
                    fields = list(data.keys())
                    sql = f"INSERT INTO {table} ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})"
                    cursor.execute(sql, list(data.values()))
                    imported += 1
                    
                    if imported % 1000 == 0:
                        print(f"  进度: {imported} 条...")
                        conn.commit()
                
                except Exception as e:
                    errors.append(str(e))
                    if len(errors) <= 5:
                        print(f"  错误: {e}")
        
        conn.commit()
        cursor.close()
        
    except Exception as e:
        print(f"  连接错误: {e}")
        return {"imported": 0, "skipped": 0, "errors": [str(e)]}
    finally:
        conn.close()
    
    print(f"\n  导入结果: 成功 {imported} 条, 跳过 {skipped} 条")
    return {"imported": imported, "skipped": skipped, "errors": errors}


# ============== 主函数 ==============

def main():
    parser = argparse.ArgumentParser(description="导出本地数据 + 导入线上数据库")
    parser.add_argument("--export-only", action="store_true", help="仅导出CSV")
    parser.add_argument("--import-only", action="store_true", help="仅导入CSV到线上")
    parser.add_argument("--full", action="store_true", help="完整流程：导出 + 导入")
    
    args = parser.parse_args()
    
    # 默认执行完整流程
    if not args.export_only and not args.import_only:
        args.full = True
    
    print("=" * 60)
    print("一体化脚本：导出 + 导入")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    results = {}
    
    # 导出阶段
    if args.export_only or args.full:
        print("\n>>> 导出阶段")
        results["profiles"] = export_customer_profiles()
        results["sessions"] = export_customer_sessions()
        results["live"] = export_live_data()
    
    # 导入阶段
    if args.import_only or args.full:
        print("\n>>> 导入阶段")
        
        csv_files = {
            "profiles": f"{OUTPUT_DIR}/customer_profiles_export.csv",
            "sessions": f"{OUTPUT_DIR}/customer_sessions_export.csv",
            "live": f"{OUTPUT_DIR}/live_data_export.csv"
        }
        
        results["import_profiles"] = import_to_production(csv_files["profiles"], "customer_profile")
        results["import_sessions"] = import_to_production(csv_files["sessions"], "customer_session")
        results["import_live"] = import_to_production(csv_files["live"], "live")
    
    # 总结
    print("\n" + "=" * 60)
    print("✅ 执行完成！")
    print("=" * 60)
    
    if args.export_only or args.full:
        print("\n导出结果:")
        print(f"  customer_profiles_export.csv: {results['profiles']['count']} 条 ({results['profiles']['size']} MB)")
        print(f"  customer_sessions_export.csv: {results['sessions']['count']} 条 ({results['sessions']['size']} MB)")
        print(f"  live_data_export.csv: {results['live']['count']} 条 ({results['live']['size']} KB)")
    
    if args.import_only or args.full:
        print("\n导入结果:")
        print(f"  客户档案: 成功 {results['import_profiles']['imported']} 条, 跳过 {results['import_profiles']['skipped']} 条")
        print(f"  客户会话: 成功 {results['import_sessions']['imported']} 条, 跳过 {results['import_sessions']['skipped']} 条")
        print(f"  直播数据: 成功 {results['import_live']['imported']} 条, 跳过 {results['import_live']['skipped']} 条")


if __name__ == "__main__":
    main()