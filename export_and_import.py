#!/usr/bin/env python3
"""
一体化脚本：导出本地数据 + 导入线上数据库
用法: python export_and_import.py [选项]
选项:
  --export-only    仅导出CSV，不导入线上
  --import-only    仅导入CSV到线上（需要先有CSV文件）
  --full           完整流程：导出 + 导入
"""

import csv
import sys
import hashlib
import json
import argparse
from datetime import datetime
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
    # MySQL datetime 已经是 UTC，需要 +8 小时
    from datetime import timedelta
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
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                customer_id,
                customer_name,
                latest_anchor_name,
                latest_analyzed_at,
                latest_live_theme,
                latest_rank,
                best_rank,
                avg_watch_seconds,
                labels,
                tags
            FROM customer_profiles
            ORDER BY updated_at DESC
        """)
        
        rows = cursor.fetchall()
        print(f"  查询结果: {len(rows)} 条")
        
        # 写入 CSV（字段名兼容 import_csv_to_production.py）
        output_path = f"{OUTPUT_DIR}/customer_profiles_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("客户ID,客户姓名,主播名称,分析时间,直播主题,排名,最高排名,平均观看时长,标签,标记\n")
            
            for r in rows:
                labels = r[8] if r[8] else "[]"
                tags = r[9] if r[9] else "[]"
                if isinstance(labels, str):
                    labels = labels
                else:
                    labels = json.dumps(labels)
                if isinstance(tags, str):
                    tags = tags
                else:
                    tags = json.dumps(tags)
                
                f.write(",".join([
                    str(r[0] or ""),
                    csv_escape(r[1]),
                    csv_escape(r[2]),
                    format_beijing_time(r[3]),
                    csv_escape(r[4]),
                    str(r[5] or 0),
                    str(r[6] or 0),
                    str(r[7] or 0),
                    csv_escape(labels),
                    csv_escape(tags),
                ]) + "\n")
        
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        
        return {"count": len(rows), "path": output_path, "size": size_mb}
        
    finally:
        cursor.close()
        conn.close()


def export_customer_sessions():
    """导出客户会话"""
    print("\n[2/3] 导出 customer_sessions...")
    
    conn = pymysql.connect(**LOCAL_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                session_id,
                customer_id,
                anchor_name,
                room_id,
                live_theme,
                report_type,
                metric_type,
                metric_value,
                watch_rank,
                watch_duration_seconds,
                analyzed_at,
                source_file
            FROM customer_sessions
            ORDER BY analyzed_at DESC
        """)
        
        rows = cursor.fetchall()
        print(f"  查询结果: {len(rows)} 条")
        
        output_path = f"{OUTPUT_DIR}/customer_sessions_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("会话ID,客户ID,主播名称,直播间ID,直播主题,报告类型,指标类型,指标值,观看排名,观看时长,分析时间,来源文件\n")
            
            for r in rows:
                f.write(",".join([
                    str(r[0] or ""),
                    str(r[1] or ""),
                    csv_escape(r[2]),
                    str(r[3] or ""),
                    csv_escape(r[4]),
                    str(r[5] or ""),
                    str(r[6] or ""),
                    str(r[7] or ""),
                    str(r[8] or 0),
                    str(r[9] or 0),
                    format_beijing_time(r[10]),
                    csv_escape(r[11]),
                ]) + "\n")
        
        size_mb = round(len(open(output_path).read()) / 1024 / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_mb} MB)")
        
        return {"count": len(rows), "path": output_path, "size": size_mb}
        
    finally:
        cursor.close()
        conn.close()


def export_live_data():
    """导出直播数据"""
    print("\n[3/3] 导出 live_data...")
    
    conn = pymysql.connect(**REMOTE_DB)
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            SELECT 
                account,
                room_id,
                title,
                startTime,
                endTime,
                duration,
                pcu,
                acu,
                earnScore,
                fansEarnScore,
                nonFansEarnScore,
                consumeUcnt,
                fansConsumeUcnt,
                nonFansConsumeUcnt,
                showUcnt,
                watchUcnt,
                fansWatchUcnt,
                nonFansWatchUcnt,
                followUcnt,
                unfollowUcnt,
                joinFansClubUcnt,
                avgWatchDuration,
                fansAvgWatchDuration,
                nonFansAvgWatchDuration,
                commentUcnt,
                fansCommentUcnt,
                nonFansCommentUcnt,
                likeCnt,
                fansLikeCnt,
                nonFansLikeCnt,
                shareCnt,
                fansShareCnt,
                nonFansShareCnt
            FROM douyin_creator_live_overview
            ORDER BY startTime DESC
        """)
        
        rows = cursor.fetchall()
        print(f"  查询结果: {len(rows)} 条")
        
        output_path = f"{OUTPUT_DIR}/live_data_export.csv"
        with open(output_path, "w", encoding="utf-8-sig") as f:
            f.write("主播账号,直播间ID,直播标题,开播时间,关播时间,直播时长,峰值在线人数,平均在线人数,收入积分,粉丝收入积分,非粉收入积分,付费人数,粉丝付费人数,非粉付费人数,曝光人数,观看人数,观看粉丝人数,观看非粉人数,涨粉人数,掉粉人数,加入粉丝团人数,人均停留时长,粉丝人均停留时长,非粉人均停留时长,评论人数,粉丝评论人数,非粉评论人数,点赞次数,粉丝点赞次数,非粉点赞次数,分享次数,粉丝分享次数,非粉分享次数\n")
            
            for r in rows:
                f.write(",".join([
                    csv_escape(r[0]),
                    str(r[1] or ""),
                    csv_escape(r[2]),
                    format_beijing_time(r[3]),
                    format_beijing_time(r[4]),
                    str(r[5] or 0),
                    str(r[6] or 0),
                    str(r[7] or 0),
                    str(r[8] or 0),
                    str(r[9] or 0),
                    str(r[10] or 0),
                    str(r[11] or 0),
                    str(r[12] or 0),
                    str(r[13] or 0),
                    str(r[14] or 0),
                    str(r[15] or 0),
                    str(r[16] or 0),
                    str(r[17] or 0),
                    str(r[18] or 0),
                    str(r[19] or 0),
                    str(r[20] or 0),
                    str(r[21] or 0),
                    str(r[22] or 0),
                    str(r[23] or 0),
                    str(r[24] or 0),
                    str(r[25] or 0),
                    str(r[26] or 0),
                    str(r[27] or 0),
                    str(r[28] or 0),
                    str(r[29] or 0),
                    str(r[30] or 0),
                    str(r[31] or 0),
                    str(r[32] or 0),
                ]) + "\n")
        
        size_kb = round(len(open(output_path).read()) / 1024, 1)
        print(f"  ✅ 导出完成: {output_path} ({size_kb} KB)")
        
        # 统计主播
        anchor_stats = {}
        for r in rows:
            name = r[0] or "未知"
            anchor_stats[name] = anchor_stats.get(name, 0) + 1
        
        print("\n=== 各主播直播场次 ===")
        for name, count in sorted(anchor_stats.items(), key=lambda x: -x[1]):
            print(f"  {name}: {count}场")
        
        return {"count": len(rows), "path": output_path, "size": size_kb, "anchors": anchor_stats}
        
    finally:
        cursor.close()
        conn.close()


# ============== 导入函数 ==============

def import_customer_profiles_to_production(csv_path):
    """导入客户档案到线上"""
    print(f"\n导入客户档案到线上数据库...")
    print(f"  CSV: {csv_path}")
    print(f"  目标: {PRODUCTION_DB['host']}:{PRODUCTION_DB['port']}/{PRODUCTION_DB['database']}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    cursor = conn.cursor()
    imported, skipped, errors = 0, 0, []
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    customer_id = str(row.get("客户ID") or row.get("customer_id") or "").strip()
                    customer_name = str(row.get("客户姓名") or row.get("customer_name") or "").strip()
                    
                    if not customer_id:
                        skipped += 1
                        continue
                    
                    # 检查重复
                    cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                    if cursor.fetchone():
                        skipped += 1
                        print(f"  跳过(已存在): {customer_id}")
                        continue
                    
                    # 构建数据
                    data = {
                        "customer_id": customer_id,
                        "customer_name": customer_name or customer_id,
                        "labels": "[]",
                        "tags": "[]",
                        "raw": "{}"
                    }
                    
                    # 解析字段
                    anchor_name = str(row.get("主播名称") or row.get("anchor_name") or "").strip()
                    if anchor_name:
                        data["latest_anchor_name"] = anchor_name
                    
                    analyzed_at = parse_datetime(row.get("分析时间") or row.get("analyzed_at"))
                    if analyzed_at:
                        data["latest_analyzed_at"] = analyzed_at
                    
                    live_theme = str(row.get("直播主题") or row.get("live_theme") or "").strip()
                    if live_theme:
                        data["latest_live_theme"] = live_theme
                    
                    rank = parse_number(row.get("排名") or row.get("latest_rank"))
                    if rank:
                        data["latest_rank"] = int(rank)
                    
                    best_rank = parse_number(row.get("最高排名") or row.get("best_rank"))
                    if best_rank:
                        data["best_rank"] = int(best_rank)
                    
                    avg_watch = parse_number(row.get("平均观看时长") or row.get("avg_watch_seconds"))
                    if avg_watch:
                        data["avg_watch_seconds"] = int(avg_watch)
                    
                    # 插入
                    fields = list(data.keys())
                    sql = f"INSERT INTO finvue_customer_profiles ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})"
                    cursor.execute(sql, list(data.values()))
                    imported += 1
                    
                    if imported % 1000 == 0:
                        print(f"  进度: {imported} 条...")
                        conn.commit()
            
            conn.commit()
            
    except Exception as e:
        errors.append(str(e))
        print(f"  错误: {e}")
    finally:
        cursor.close()
        conn.close()
    
    print(f"\n  导入结果: 成功 {imported} 条, 跳过 {skipped} 条")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_customer_sessions_to_production(csv_path):
    """导入客户会话到线上"""
    print(f"\n导入客户会话到线上数据库...")
    print(f"  CSV: {csv_path}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    cursor = conn.cursor()
    imported, skipped, errors = 0, 0, []
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    customer_id = str(row.get("客户ID") or row.get("customer_id") or "").strip()
                    
                    if not customer_id:
                        skipped += 1
                        continue
                    
                    # 检查客户是否存在
                    cursor.execute("SELECT customer_id FROM finvue_customer_profiles WHERE customer_id = %s", (customer_id,))
                    if not cursor.fetchone():
                        skipped += 1
                        print(f"  跳过(客户不存在): {customer_id}")
                        continue
                    
                    # 生成或获取 session_id
                    session_id = str(row.get("会话ID") or row.get("session_id") or "").strip()
                    anchor = str(row.get("主播名称") or row.get("anchor_name") or "").strip()
                    analyzed = parse_datetime(row.get("分析时间") or row.get("analyzed_at")) or ""
                    
                    if not session_id:
                        session_id = generate_id(customer_id, anchor, analyzed)
                    
                    # 检查会话重复
                    cursor.execute("SELECT session_id FROM finvue_customer_sessions WHERE session_id = %s", (session_id,))
                    if cursor.fetchone():
                        skipped += 1
                        continue
                    
                    # 构建数据
                    data = {
                        "session_id": session_id,
                        "customer_id": customer_id,
                        "raw": "{}"
                    }
                    
                    # 解析字段
                    if anchor:
                        data["anchor_name"] = anchor
                    
                    room_id = str(row.get("直播间ID") or row.get("room_id") or "").strip()
                    if room_id:
                        data["room_id"] = room_id
                    
                    live_theme = str(row.get("直播主题") or row.get("live_theme") or "").strip()
                    if live_theme:
                        data["live_theme"] = live_theme
                    
                    report_type = str(row.get("报告类型") or row.get("report_type") or "").strip()
                    if report_type:
                        data["report_type"] = report_type
                    
                    metric_type = str(row.get("指标类型") or row.get("metric_type") or "").strip()
                    if metric_type:
                        data["metric_type"] = metric_type
                    
                    metric_value = str(row.get("指标值") or row.get("metric_value") or "").strip()
                    if metric_value:
                        data["metric_value"] = metric_value
                    
                    watch_rank = parse_number(row.get("观看排名") or row.get("watch_rank"))
                    if watch_rank:
                        data["watch_rank"] = int(watch_rank)
                    
                    watch_duration = parse_number(row.get("观看时长") or row.get("watch_duration_seconds"))
                    if watch_duration:
                        data["watch_duration_seconds"] = int(watch_duration)
                    
                    if analyzed:
                        data["analyzed_at"] = analyzed
                    
                    source_file = str(row.get("来源文件") or row.get("source_file") or "").strip()
                    if source_file:
                        data["source_file"] = source_file
                    
                    # 插入
                    fields = list(data.keys())
                    sql = f"INSERT INTO finvue_customer_sessions ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})"
                    cursor.execute(sql, list(data.values()))
                    imported += 1
                    
                    if imported % 5000 == 0:
                        print(f"  进度: {imported} 条...")
                        conn.commit()
            
            conn.commit()
            
    except Exception as e:
        errors.append(str(e))
        print(f"  错误: {e}")
    finally:
        cursor.close()
        conn.close()
    
    print(f"\n  导入结果: 成功 {imported} 条, 跳过 {skipped} 条")
    return {"imported": imported, "skipped": skipped, "errors": errors}


def import_live_data_to_production(csv_path):
    """导入直播数据到线上"""
    print(f"\n导入直播数据到线上数据库...")
    print(f"  CSV: {csv_path}")
    
    conn = pymysql.connect(**PRODUCTION_DB)
    cursor = conn.cursor()
    imported, skipped, errors = 0, 0, []
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                try:
                    account = str(row.get("主播账号") or row.get("account") or "").strip()
                    room_id = str(row.get("直播间ID") or row.get("room_id") or "").strip()
                    
                    if not account:
                        skipped += 1
                        continue
                    
                    start_time = parse_datetime(row.get("开播时间") or row.get("start_time") or row.get("startTime"))
                    
                    if not room_id and start_time:
                        room_id = generate_id(account, start_time)
                    if not room_id:
                        skipped += 1
                        continue
                    
                    # 检查重复
                    cursor.execute("SELECT id FROM finvue_operation_live_stats WHERE room_id = %s", (room_id,))
                    if cursor.fetchone():
                        skipped += 1
                        print(f"  跳过(已存在): {room_id}")
                        continue
                    
                    # 构建数据
                    data = {"account": account, "room_id": room_id}
                    
                    # 解析字段
                    title = str(row.get("直播标题") or row.get("title") or "").strip()
                    if title:
                        data["title"] = title
                    
                    if start_time:
                        data["start_time"] = start_time
                    
                    end_time = parse_datetime(row.get("关播时间") or row.get("end_time") or row.get("endTime"))
                    if end_time:
                        data["end_time"] = end_time
                    
                    duration = parse_number(row.get("直播时长") or row.get("duration"))
                    if duration:
                        data["duration"] = int(duration)
                    
                    # 人数字段
                    num_fields = ["峰值在线人数", "平均在线人数", "曝光人数", "观看人数", 
                                  "观看粉丝人数", "观看非粉人数", "涨粉人数", "掉粉人数",
                                  "加入粉丝团人数", "评论人数", "粉丝评论人数", "非粉评论人数",
                                  "点赞次数", "粉丝点赞次数", "非粉点赞次数", "分享次数",
                                  "粉丝分享次数", "非粉分享次数", "付费人数", "粉丝付费人数",
                                  "非粉付费人数", "收入积分", "粉丝收入积分", "非粉收入积分"]
                    db_fields = ["pcu", "acu", "show_ucnt", "watch_ucnt", 
                                 "fans_watch_ucnt", "non_fans_watch_ucnt", "follow_ucnt", "unfollow_ucnt",
                                 "join_fansclub_ucnt", "comment_ucnt", "fans_comment_ucnt", "non_fans_comment_ucnt",
                                 "like_cnt", "fans_like_cnt", "non_fans_like_cnt", "share_cnt",
                                 "fans_share_cnt", "non_fans_share_cnt", "consume_ucnt", "fans_consume_ucnt",
                                 "non_fans_consume_ucnt", "earn_score", "fans_earn_score", "non_fans_earn_score"]
                    
                    for i, csv_field in enumerate(num_fields):
                        val = parse_number(row.get(csv_field) or row.get(db_fields[i]))
                        if val:
                            data[db_fields[i]] = int(val)
                    
                    # 时长字段
                    duration_fields = ["人均停留时长", "粉丝人均停留时长", "非粉人均停留时长"]
                    duration_db = ["avg_watch_duration", "fans_avg_watch_duration", "non_fans_avg_watch_duration"]
                    
                    for i, csv_field in enumerate(duration_fields):
                        val = parse_number(row.get(csv_field) or row.get(duration_db[i]))
                        if val:
                            data[duration_db[i]] = val
                    
                    # 插入
                    fields = list(data.keys())
                    sql = f"INSERT INTO finvue_operation_live_stats ({','.join(fields)}) VALUES ({','.join(['%s']*len(fields))})"
                    cursor.execute(sql, list(data.values()))
                    imported += 1
                    
                    if imported % 100 == 0:
                        print(f"  进度: {imported} 条...")
                        conn.commit()
            
            conn.commit()
            
    except Exception as e:
        errors.append(str(e))
        print(f"  错误: {e}")
    finally:
        cursor.close()
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
    
    print("=" * 60)
    print("一体化脚本：导出 + 导入")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 默认执行完整流程
    if not args.export_only and not args.import_only:
        args.full = True
    
    results = {}
    
    if args.export_only or args.full:
        print("\n>>> 导出阶段")
        results["profiles"] = export_customer_profiles()
        results["sessions"] = export_customer_sessions()
        results["live"] = export_live_data()
    
    if args.import_only or args.full:
        print("\n>>> 导入阶段")
        
        if args.full:
            csv_files = {
                "profiles": results["profiles"]["path"],
                "sessions": results["sessions"]["path"],
                "live": results["live"]["path"]
            }
        else:
            # 从默认路径读取
            csv_files = {
                "profiles": f"{OUTPUT_DIR}/customer_profiles_export.csv",
                "sessions": f"{OUTPUT_DIR}/customer_sessions_export.csv",
                "live": f"{OUTPUT_DIR}/live_data_export.csv"
            }
        
        print("\n--- 导入客户档案 ---")
        results["import_profiles"] = import_customer_profiles_to_production(csv_files["profiles"])
        
        print("\n--- 导入客户会话 ---")
        results["import_sessions"] = import_customer_sessions_to_production(csv_files["sessions"])
        
        print("\n--- 导入直播数据 ---")
        results["import_live"] = import_live_data_to_production(csv_files["live"])
    
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