#!/usr/bin/env python3
"""
CSV数据导入脚本 - 导入直播/短视频数据到线上数据库
用法: python import_csv_to_production.py <csv文件> [live|video]
"""

import csv
import sys
import hashlib
import re
from datetime import datetime
import pymysql

# 线上数据库配置
DB_CONFIG = {
    "host": "mysql0200.3337-wm.db.idc",
    "port": 3337,
    "database": "process_analysis",
    "user": "process_analysis",
    "password": "ns7ubvy96ncHncOTOeHS",
    "charset": "utf8mb4",
}

# 字段映射 - CSV中文列名 -> 数据库字段名
LIVE_FIELD_MAP = {
    "主播账号": "account",
    "account": "account",
    "直播间ID": "room_id",
    "roomId": "room_id",
    "直播标题": "title",
    "title": "title",
    "开播时间": "start_time",
    "startTime": "start_time",
    "直播时长": "duration",
    "duration": "duration",
    "直播时长(分钟)": "duration",
    "直播时长（分钟）": "duration",
    "峰值在线人数": "pcu",
    "pcu": "pcu",
    "平均在线人数": "acu",
    "acu": "acu",
    "曝光人数": "show_ucnt",
    "showUcnt": "show_ucnt",
    "观看人数": "watch_ucnt",
    "watchUcnt": "watch_ucnt",
    "观看粉丝人数": "fans_watch_ucnt",
    "fansWatchUcnt": "fans_watch_ucnt",
    "观看非粉人数": "non_fans_watch_ucnt",
    "nonFansWatchUcnt": "non_fans_watch_ucnt",
    "人均停留时长": "avg_watch_duration",
    "avgWatchDuration": "avg_watch_duration",
    "粉丝人均停留时长": "fans_avg_watch_duration",
    "fansAvgWatchDuration": "fans_avg_watch_duration",
    "非粉人均停留时长": "non_fans_avg_watch_duration",
    "nonFansAvgWatchDuration": "non_fans_avg_watch_duration",
    "涨粉人数": "follow_ucnt",
    "followUcnt": "follow_ucnt",
    "涨粉率": "follow_u_rate",
    "followURate": "follow_u_rate",
    "掉粉人数": "unfollow_ucnt",
    "unfollowUcnt": "unfollow_ucnt",
    "加入粉丝团人数": "join_fansclub_ucnt",
    "joinFansclubUcnt": "join_fansclub_ucnt",
    "评论人数": "comment_ucnt",
    "commentUcnt": "comment_ucnt",
    "点赞次数": "like_cnt",
    "likeCnt": "like_cnt",
    "分享次数": "share_cnt",
    "shareCnt": "share_cnt",
    "收入积分": "earn_score",
    "earnScore": "earn_score",
    "付费人数": "consume_ucnt",
    "consumeUcnt": "consume_ucnt",
}

VIDEO_FIELD_MAP = {
    "主播账号": "account",
    "account": "account",
    "视频ID": "video_id",
    "videoId": "video_id",
    "作品名称": "title",
    "title": "title",
    "发布时间": "publish_time",
    "publishTime": "publish_time",
    "体裁": "duration_type",
    "durationType": "duration_type",
    "播放量": "play_count",
    "playCount": "play_count",
    "点赞数": "like_count",
    "likeCount": "like_count",
    "评论数": "comment_count",
    "commentCount": "comment_count",
    "分享数": "share_count",
    "shareCount": "share_count",
    "完播率": "completion_rate",
    "completionRate": "completion_rate",
    "5秒完播率": "5s_completion_rate",
    "5sCompletionRate": "5s_completion_rate",
    "2秒流失率": "2s_exit_rate",
    "2sExitRate": "2s_exit_rate",
    "互动率": "interaction_rate",
    "interactionRate": "interaction_rate",
    "涨粉数": "follow_count",
    "followCount": "follow_count",
}


def normalize_field_name(name: str) -> str:
    """标准化字段名"""
    name = str(name or "").strip()
    return name


def parse_number(value: str) -> int | float | None:
    """解析数字"""
    if not value:
        return None
    value = str(value).strip()
    # 移除百分号
    if "%" in value:
        value = value.replace("%", "")
        try:
            return float(value)
        except:
            return None
    # 移除逗号
    value = value.replace(",", "")
    try:
        if "." in value:
            return float(value)
        return int(value)
    except:
        return None


def parse_datetime(value: str) -> str | None:
    """解析日期时间"""
    if not value:
        return None
    value = str(value).strip()
    # 尝试多种格式
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            continue
    return None


def generate_room_id(account: str, start_time: str) -> str:
    """生成唯一room_id"""
    key = f"{account}_{start_time}"
    return hashlib.md5(key.encode()).hexdigest()[:19]


def import_live_csv(csv_path: str) -> dict:
    """导入直播CSV"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    imported = 0
    skipped = 0
    errors = []
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            # 映射CSV列名到数据库字段
            field_mapping = {}
            for h in headers or []:
                h_norm = normalize_field_name(h)
                if h_norm in LIVE_FIELD_MAP:
                    field_mapping[h] = LIVE_FIELD_MAP[h_norm]
            
            print(f"CSV列: {headers}")
            print(f"映射字段: {field_mapping}")
            
            for row in reader:
                try:
                    # 获取account
                    account = None
                    for k, v in field_mapping.items():
                        if v == "account":
                            account = str(row.get(k) or "").strip()
                            break
                    
                    if not account:
                        skipped += 1
                        continue
                    
                    # 获取/生成room_id
                    room_id = None
                    for k, v in field_mapping.items():
                        if v == "room_id":
                            room_id = str(row.get(k) or "").strip()
                            break
                    
                    # 获取start_time
                    start_time = None
                    for k, v in field_mapping.items():
                        if v == "start_time":
                            start_time = parse_datetime(row.get(k))
                            break
                    
                    if not room_id:
                        if start_time:
                            room_id = generate_room_id(account, start_time)
                        else:
                            skipped += 1
                            continue
                    
                    # 检查是否已存在
                    cursor.execute(
                        "SELECT id FROM finvue_operation_live_stats WHERE room_id = %s",
                        (room_id,)
                    )
                    if cursor.fetchone():
                        skipped += 1
                        print(f"跳过已存在: {room_id}")
                        continue
                    
                    # 构建INSERT数据
                    data = {
                        "account": account,
                        "room_id": room_id,
                        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    
                    for csv_col, db_field in field_mapping.items():
                        if db_field in ["account", "room_id", "imported_at"]:
                            continue
                        value = row.get(csv_col)
                        if not value:
                            continue
                        
                        if db_field in ["start_time", "end_time"]:
                            data[db_field] = parse_datetime(value)
                        elif db_field in ["duration", "pcu", "acu", "show_ucnt", "watch_ucnt",
                                         "fans_watch_ucnt", "non_fans_watch_ucnt", "follow_ucnt",
                                         "unfollow_ucnt", "join_fansclub_ucnt", "comment_ucnt",
                                         "like_cnt", "share_cnt", "earn_score", "consume_ucnt"]:
                            num = parse_number(value)
                            if num is not None:
                                data[db_field] = int(num) if isinstance(num, float) and num == int(num) else num
                        elif db_field in ["avg_watch_duration", "fans_avg_watch_duration",
                                         "non_fans_avg_watch_duration", "follow_u_rate"]:
                            num = parse_number(value)
                            if num is not None:
                                data[db_field] = num
                        elif db_field == "title":
                            data[db_field] = str(value).strip()
                    
                    # 插入数据
                    fields = list(data.keys())
                    values = list(data.values())
                    placeholders = ["%s"] * len(fields)
                    
                    sql = f"""
                        INSERT INTO finvue_operation_live_stats ({', '.join(fields)})
                        VALUES ({', '.join(placeholders)})
                    """
                    cursor.execute(sql, values)
                    imported += 1
                    
                except Exception as e:
                    errors.append(str(e))
                    print(f"错误: {e}")
        
        conn.commit()
        
    finally:
        cursor.close()
        conn.close()
    
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


def import_video_csv(csv_path: str) -> dict:
    """导入短视频CSV"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    imported = 0
    skipped = 0
    errors = []
    
    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames
            
            # 映射CSV列名到数据库字段
            field_mapping = {}
            for h in headers or []:
                h_norm = normalize_field_name(h)
                if h_norm in VIDEO_FIELD_MAP:
                    field_mapping[h] = VIDEO_FIELD_MAP[h_norm]
            
            print(f"CSV列: {headers}")
            print(f"映射字段: {field_mapping}")
            
            for row in reader:
                try:
                    # 获取account
                    account = None
                    for k, v in field_mapping.items():
                        if v == "account":
                            account = str(row.get(k) or "").strip()
                            break
                    
                    if not account:
                        skipped += 1
                        continue
                    
                    # 获取publish_time
                    publish_time = None
                    for k, v in field_mapping.items():
                        if v == "publish_time":
                            publish_time = parse_datetime(row.get(k))
                            break
                    
                    # 获取title
                    title = None
                    for k, v in field_mapping.items():
                        if v == "title":
                            title = str(row.get(k) or "").strip()
                            break
                    
                    # 构建INSERT数据
                    data = {
                        "account": account,
                        "imported_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    
                    if publish_time:
                        data["publish_time"] = publish_time
                    if title:
                        data["title"] = title
                    
                    for csv_col, db_field in field_mapping.items():
                        if db_field in ["account", "imported_at", "publish_time", "title"]:
                            continue
                        value = row.get(csv_col)
                        if not value:
                            continue
                        
                        if db_field in ["play_count", "like_count", "comment_count", 
                                        "share_count", "follow_count"]:
                            num = parse_number(value)
                            if num is not None:
                                data[db_field] = int(num)
                        elif db_field in ["completion_rate", "5s_completion_rate",
                                         "2s_exit_rate", "interaction_rate"]:
                            num = parse_number(value)
                            if num is not None:
                                data[db_field] = num
                        elif db_field in ["video_id", "duration_type"]:
                            data[db_field] = str(value).strip()
                    
                    # 检查是否已存在（根据account + title + publish_time）
                    if data.get("title") and data.get("publish_time"):
                        cursor.execute(
                            "SELECT id FROM finvue_operation_video_stats "
                            "WHERE account = %s AND title = %s AND publish_time = %s",
                            (account, data["title"], data["publish_time"])
                        )
                        if cursor.fetchone():
                            skipped += 1
                            print(f"跳过已存在: {account} - {data['title']}")
                            continue
                    
                    # 插入数据
                    fields = list(data.keys())
                    values = list(data.values())
                    placeholders = ["%s"] * len(fields)
                    
                    sql = f"""
                        INSERT INTO finvue_operation_video_stats ({', '.join(fields)})
                        VALUES ({', '.join(placeholders)})
                    """
                    cursor.execute(sql, values)
                    imported += 1
                    
                except Exception as e:
                    errors.append(str(e))
                    print(f"错误: {e}")
        
        conn.commit()
        
    finally:
        cursor.close()
        conn.close()
    
    return {
        "ok": True,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
    }


def main():
    if len(sys.argv) < 2:
        print("用法: python import_csv_to_production.py <csv文件> [live|video]")
        print("示例: python import_csv_to_production.py live_data.csv live")
        print("示例: python import_csv_to_production.py video_data.csv video")
        sys.exit(1)
    
    csv_path = sys.argv[1]
    import_type = sys.argv[2] if len(sys.argv) > 2 else "live"
    
    print(f"导入类型: {import_type}")
    print(f"CSV文件: {csv_path}")
    print(f"数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}")
    print("-" * 50)
    
    if import_type == "live":
        result = import_live_csv(csv_path)
    elif import_type == "video":
        result = import_video_csv(csv_path)
    else:
        print(f"未知导入类型: {import_type}")
        sys.exit(1)
    
    print("-" * 50)
    print(f"导入完成!")
    print(f"成功导入: {result['imported']} 条")
    print(f"跳过: {result['skipped']} 条")
    if result['errors']:
        print(f"错误数: {len(result['errors'])}")
        for e in result['errors'][:5]:
            print(f"  - {e}")


if __name__ == "__main__":
    main()