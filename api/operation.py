"""运营数据看板 API 接口."""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, Depends
from fastapi.responses import StreamingResponse

import db
import security
import logger


router = APIRouter()


def get_client_ip(request: Request) -> str:
    """获取客户端IP地址."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""

# 字段映射：CSV 字段名 -> 数据库字段名
LIVE_FIELD_MAP = {
    "账号名称": "account",
    "直播id": "room_id",
    "room_id": "room_id",
    "account": "account",
    "直播标题": "title",
    "title": "title",
    "开播时间": "start_time",
    "startTime": "start_time",
    "关播时间": "end_time",
    "endTime": "end_time",
    "直播时长": "duration",
    "duration": "duration",
    "峰值人数": "pcu",
    "pcu": "pcu",
    "平均人数": "acu",
    "acu": "acu",
    "收获音浪": "earn_score",
    "earnScore": "earn_score",
    "粉丝音浪": "fans_earn_score",
    "fansEarnScore": "fans_earn_score",
    "非粉音浪": "non_fans_earn_score",
    "nonFansEarnScore": "non_fans_earn_score",
    "首次送礼用户音浪": "first_earn_score",
    "firstEarnScore": "first_earn_score",
    "送礼人数": "consume_ucnt",
    "consumeUcnt": "consume_ucnt",
    "送礼粉丝人数": "fans_consume_ucnt",
    "fansConsumeUcnt": "fans_consume_ucnt",
    "送礼非粉人数": "non_fans_consume_ucnt",
    "nonFansConsumeUcnt": "non_fans_consume_ucnt",
    "首次送礼人数": "first_consume_ucnt",
    "firstConsumeUcnt": "first_consume_ucnt",
    "预计收入": "expected_total_income",
    "expectedTotalIncome": "expected_total_income",
    "曝光人数": "show_ucnt",
    "showUcnt": "show_ucnt",
    "观看人数": "watch_ucnt",
    "watchUcnt": "watch_ucnt",
    "观看粉丝人数": "fans_watch_ucnt",
    "fansWatchUcnt": "fans_watch_ucnt",
    "观看非粉人数": "non_fans_watch_ucnt",
    "nonFansWatchUcnt": "non_fans_watch_ucnt",
    "涨粉人数": "follow_ucnt",
    "followUcnt": "follow_ucnt",
    "掉粉人数": "unfollow_ucnt",
    "unfollowUcnt": "unfollow_ucnt",
    "加团人数": "join_fansclub_ucnt",
    "joinFansClubUcnt": "join_fansclub_ucnt",
    "人均停留时长": "avg_watch_duration",
    "avgWatchDuration": "avg_watch_duration",
    "粉丝人均停留时长": "fans_avg_watch_duration",
    "fansAvgWatchDuration": "fans_avg_watch_duration",
    "非粉人均停留时长": "non_fans_avg_watch_duration",
    "nonFansAvgWatchDuration": "non_fans_avg_watch_duration",
    "评论人数": "comment_ucnt",
    "commentUcnt": "comment_ucnt",
    "评论粉丝人数": "fans_comment_ucnt",
    "fansCommentUcnt": "fans_comment_ucnt",
    "评论非粉人数": "non_fans_comment_ucnt",
    "nonFansCommentUcnt": "non_fans_comment_ucnt",
    "点赞次数": "like_cnt",
    "likeCnt": "like_cnt",
    "点赞粉丝次数": "fans_like_cnt",
    "fansLikeCnt": "fans_like_cnt",
    "点赞非粉次数": "non_fans_like_cnt",
    "nonFansLikeCnt": "non_fans_like_cnt",
    "分享次数": "share_cnt",
    "shareCnt": "share_cnt",
    "分享粉丝次数": "fans_share_cnt",
    "fansShareCnt": "fans_share_cnt",
    "分享非粉次数": "non_fans_share_cnt",
    "nonFansShareCnt": "non_fans_share_cnt",
    "曝光分布": "show_cnt_dist",
    "showCntDist": "show_cnt_dist",
    "观看分布": "watch_ucnt_dist",
    "watchUcntDist": "watch_ucnt_dist",
    "群内粉丝": "fans_in_group",
    "fansInGroup": "fans_in_group",
    "群外粉丝": "fans_out_group",
    "fansOutGroup": "fans_out_group",
    "观看率": "watch_u_rate",
    "watchURate": "watch_u_rate",
    "涨粉率": "follow_u_rate",
    "followURate": "follow_u_rate",
    "评论率": "comment_u_rate",
    "commentURate": "comment_u_rate",
    "送礼率": "consume_u_rate",
    "consumeURate": "consume_u_rate",
    "粉丝观看率": "fans_watch_u_rate",
    "fansWatchURate": "fans_watch_u_rate",
    "粉丝评论率": "fans_comment_u_rate",
    "fansCommentURate": "fans_comment_u_rate",
    "粉丝点赞率": "fans_like_rate",
    "fansLikeRate": "fans_like_rate",
    "粉丝分享率": "fans_share_rate",
    "fansShareRate": "fans_share_rate",
    "粉丝送礼率": "fans_consume_u_rate",
    "fansConsumeURate": "fans_consume_u_rate",
    "群内粉丝率": "fans_in_group_rate",
    "fansInGroupRate": "fans_in_group_rate",
    "创建时间": "created_at",
    "created_at": "created_at",
}

VIDEO_FIELD_MAP = {
    "账号名称": "account",
    "主播账号": "account",
    "account": "account",
    "视频ID": "video_id",
    "video_id": "video_id",
    "作品名称": "title",
    "视频标题": "title",
    "title": "title",
    "发布时间": "publish_time",
    "publish_time": "publish_time",
    "体裁": "duration_type",
    "duration_type": "duration_type",
    "播放量": "play_count",
    "play_count": "play_count",
    "播放量(万)": "play_count",
    "点赞数": "like_count",
    "like_count": "like_count",
    "评论数": "comment_count",
    "comment_count": "comment_count",
    "分享数": "share_count",
    "share_count": "share_count",
    "完播率": "completion_rate",
    "completion_rate": "completion_rate",
    "5s完播率": "5s_completion_rate",
    "5s_completion_rate": "5s_completion_rate",
    "2s跳出率": "2s_exit_rate",
    "2s_exit_rate": "2s_exit_rate",
    "互动率": "interaction_rate",
    "interaction_rate": "interaction_rate",
    "涨粉": "follow_count",
    "涨粉数": "follow_count",
    "粉丝增量": "follow_count",
    "follow_count": "follow_count",
}


def _parse_csv_field(value: str, field_name: str) -> Any:
    """解析 CSV 字段值."""
    value = str(value or "").strip()
    # 去掉值周围可能存在的额外引号
    if value.startswith('"') and value.endswith('"'):
        value = value[1:-1].strip()
    if not value or value in ("nan", "NaN", "null", "NULL", "-"):
        return None

    # 处理百分比
    if "%" in value:
        try:
            return float(value.replace("%", "").strip())
        except ValueError:
            return None

    # 处理带单位的数字 (如 "0.96万")
    if "万" in value:
        try:
            num = float(value.replace("万", "").strip())
            return int(num * 10000)
        except ValueError:
            return None

    # 处理时间字段
    time_fields = ("start_time", "end_time", "publish_time", "created_at")
    if field_name in time_fields:
        try:
            # 支持多种时间格式
            # 先处理 ISO 8601 格式带毫秒 (如 2026-05-09T07:41:21.000Z)
            if "T" in value and value.endswith("Z"):
                # 去掉 Z 和毫秒部分
                value_clean = value.rstrip("Z")
                if "." in value_clean:
                    value_clean = value_clean.split(".")[0]
                try:
                    dt = datetime.strptime(value_clean, "%Y-%m-%dT%H:%M:%S")
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    pass

            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(value, fmt)
                    if fmt == "%m-%d %H:%M:%S":
                        # 补充年份
                        dt = dt.replace(year=datetime.now().year)
                    return dt.strftime("%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            return None
        except Exception:
            return None

    # 尝试数字解析
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _import_live_csv(content: str) -> dict:
    """导入直播数据 CSV."""
    reader = csv.DictReader(io.StringIO(content))
    records = []
    skipped = 0

    for row in reader:
        mapped = {}
        for csv_key, value in row.items():
            db_key = LIVE_FIELD_MAP.get(csv_key.strip())
            if db_key:
                parsed = _parse_csv_field(value, db_key)
                if parsed is not None:
                    mapped[db_key] = parsed

        # 必要字段检查
        if not mapped.get("room_id") or not mapped.get("account"):
            skipped += 1
            continue

        # 默认值填充
        for col in ("duration", "pcu", "acu", "earn_score", "watch_ucnt", "follow_ucnt"):
            if mapped.get(col) is None:
                mapped[col] = 0

        records.append(mapped)

    if not records:
        return {"ok": False, "error": "无有效数据", "imported": 0, "skipped": skipped}

    # 批量插入 (先删除相同 room_id 的记录)
    conn = db.get_connection(autocommit=True)
    try:
        cur = conn.cursor()
        room_ids = [r["room_id"] for r in records]
        cur.execute(
            "DELETE FROM finvue_operation_live_stats WHERE room_id IN (%s)" % ",".join(["%s"] * len(room_ids)),
            room_ids
        )

        # 插入新数据
        cols = list(records[0].keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO finvue_operation_live_stats ({col_names}) VALUES ({placeholders})"

        for rec in records:
            values = [rec.get(c) for c in cols]
            cur.execute(sql, values)

        cur.close()
    finally:
        conn.close()

    accounts = len(set(r["account"] for r in records))
    return {"ok": True, "imported": len(records), "skipped": skipped, "accounts": accounts}


def _import_video_csv(content: str) -> dict:
    """导入短视频数据 CSV."""
    reader = csv.DictReader(io.StringIO(content))
    records = []
    skipped = 0

    for row in reader:
        mapped = {}
        for csv_key, value in row.items():
            db_key = VIDEO_FIELD_MAP.get(csv_key.strip())
            if db_key:
                parsed = _parse_csv_field(value, db_key)
                if parsed is not None:
                    mapped[db_key] = parsed

        # 必要字段检查
        if not mapped.get("account") or not mapped.get("title"):
            skipped += 1
            continue

        # 默认值填充
        for col in ("play_count", "like_count", "follow_count"):
            if mapped.get(col) is None:
                mapped[col] = 0

        records.append(mapped)

    if not records:
        return {"ok": False, "error": "无有效数据", "imported": 0, "skipped": skipped}

    # 批量插入 (按 video_id 或 account+title+publish_time 去重)
    conn = db.get_connection(autocommit=True)
    try:
        cur = conn.cursor()

        # 收集有 video_id 的记录
        with_video_id = [r for r in records if r.get("video_id")]
        without_video_id = [r for r in records if not r.get("video_id")]

        # 按 video_id 删除再插入
        if with_video_id:
            video_ids = list(set(r["video_id"] for r in with_video_id))
            cur.execute(
                "DELETE FROM finvue_operation_video_stats WHERE video_id IN (%s)" % ",".join(["%s"] * len(video_ids)),
                video_ids
            )

        # 按 account+title+publish_time 删除再插入（用于无 video_id 的情况）
        if without_video_id:
            for rec in without_video_id:
                cur.execute(
                    "DELETE FROM finvue_operation_video_stats WHERE account = %s AND title = %s AND publish_time = %s",
                    (rec["account"], rec["title"], rec.get("publish_time"))
                )

        cols = list(records[0].keys())
        col_names = ", ".join(cols)
        placeholders = ", ".join(["%s"] * len(cols))
        sql = f"INSERT INTO finvue_operation_video_stats ({col_names}) VALUES ({placeholders})"

        for rec in records:
            values = [rec.get(c) for c in cols]
            cur.execute(sql, values)

        cur.close()
    finally:
        conn.close()

    accounts_count = len(set(r["account"] for r in records))
    return {"ok": True, "imported": len(records), "skipped": skipped, "accounts": accounts_count}


# === CSV 上传接口 ===

@router.post("/api/operation/import-live")
async def import_live_data(
    request: Request,
    file: UploadFile = File(...),
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """上传直播数据 CSV."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # 支持 BOM
    except UnicodeDecodeError:
        text = content.decode("gbk")

    result = _import_live_csv(text)

    session = security.require_auth(request)
    username = session.get("username")
    user_id = session.get("user_id")
    ip = get_client_ip(request)

    # 记录导入日志
    if result.get("ok"):
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, account_count, status, imported_by)
            VALUES ('live', %s, %s, %s, 'success', %s)
            """,
            (file.filename, result["imported"], result.get("accounts", 0), username)
        )
        # 记录操作日志
        logger.log_import(
            module="operation",
            title=f"导入直播数据: {file.filename}",
            description=f"导入 {result['imported']} 条直播记录，涉及 {result.get('accounts', 0)} 个主播账号",
            username=username,
            user_id=user_id,
            record_count=result["imported"],
            status="success",
            request_ip=ip,
        )
    else:
        # 记录导入失败日志
        logger.log_import(
            module="operation",
            title=f"导入直播数据失败: {file.filename}",
            description=f"导入直播数据失败",
            username=username,
            user_id=user_id,
            status="failed",
            error_message=result.get("error"),
            request_ip=ip,
        )

    return result


@router.post("/api/operation/import-video")
async def import_video_data(
    request: Request,
    file: UploadFile = File(...),
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """上传短视频数据 CSV."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传 CSV 文件")

    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("gbk")

    result = _import_video_csv(text)

    session = security.require_auth(request)
    username = session.get("username")
    user_id = session.get("user_id")
    ip = get_client_ip(request)

    if result.get("ok"):
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, account_count, status, imported_by)
            VALUES ('video', %s, %s, %s, 'success', %s)
            """,
            (file.filename, result["imported"], result.get("accounts", 0), username)
        )
        # 记录操作日志
        logger.log_import(
            module="operation",
            title=f"导入短视频数据: {file.filename}",
            description=f"导入 {result['imported']} 条短视频记录，涉及 {result.get('accounts', 0)} 个主播账号",
            username=username,
            user_id=user_id,
            record_count=result["imported"],
            status="success",
            request_ip=ip,
        )
    else:
        logger.log_import(
            module="operation",
            title=f"导入短视频数据失败: {file.filename}",
            description=f"导入短视频数据失败",
            username=username,
            user_id=user_id,
            status="failed",
            error_message=result.get("error"),
            request_ip=ip,
        )

    return result


@router.delete("/api/operation/live/{room_id}")
def delete_live_record(
    room_id: str,
    request: Request,
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """删除直播记录（仅限手工录入的记录）."""
    session = security.require_auth(request)
    username = session.get("username")
    user_id = session.get("user_id")
    ip = get_client_ip(request)
    
    # 检查记录是否存在且为手工录入
    existing = db.fetch_one(
        "SELECT id, account, start_time, notes FROM finvue_operation_live_stats WHERE room_id = %s",
        (room_id,)
    )
    if not existing:
        logger.log_delete(
            module="operation",
            target_type="live_record",
            target_id=room_id,
            title="删除直播记录失败",
            description=f"删除直播记录 {room_id} 失败",
            username=username,
            user_id=user_id,
            status="failed",
            error_message="记录不存在",
            request_ip=ip,
        )
        return {"ok": False, "error": "记录不存在"}

    # 检查是否为手工录入（notes字段包含"[手工录入]"）
    notes = existing.get("notes") or ""
    if "[手工录入]" not in notes:
        logger.log_delete(
            module="operation",
            target_type="live_record",
            target_id=room_id,
            title="删除直播记录失败",
            description=f"删除直播记录 {room_id} 失败：非手工录入",
            username=username,
            user_id=user_id,
            status="failed",
            error_message="只能删除手工录入的记录",
            request_ip=ip,
        )
        return {"ok": False, "error": "只能删除手工录入的记录，CSV导入的记录不可删除"}

    # 删除记录
    db.execute(
        "DELETE FROM finvue_operation_live_stats WHERE room_id = %s",
        (room_id,)
    )
    
    # 记录删除成功
    logger.log_delete(
        module="operation",
        target_type="live_record",
        target_id=room_id,
        title=f"删除直播记录: {existing['account']}",
        description=f"删除主播 {existing['account']} 的直播记录（开播时间：{existing.get('start_time')}）",
        username=username,
        user_id=user_id,
        status="success",
        request_ip=ip,
    )

    return {"ok": True, "deleted": room_id, "account": existing["account"]}


# === 报表查询接口 ===

@router.get("/api/operation/accounts")
def get_accounts(_: dict = Depends(security.require_permission("home"))) -> dict:
    """获取所有主播账号列表."""
    try:
        rows = db.fetch_all(
            """
            SELECT DISTINCT account, COUNT(*) as live_count,
                   MAX(start_time) as last_live_time,
                   MIN(start_time) as first_live_time
            FROM finvue_operation_live_stats
            GROUP BY account
            ORDER BY live_count DESC
            """
        )

        # 获取整体数据时间范围
        total_info = db.fetch_one(
            """
            SELECT COUNT(*) as total_count,
                   MAX(start_time) as max_time,
                   MIN(start_time) as min_time
            FROM finvue_operation_live_stats
            """
        )

        return {
            "ok": True,
            "accounts": rows or [],
            "total_count": total_info.get("total_count", 0) if total_info else 0,
            "data_range": {
                "min": total_info.get("min_time") if total_info else None,
                "max": total_info.get("max_time") if total_info else None
            }
        }
    except Exception as e:
        # 检查是否是表不存在错误
        err_msg = str(e)
        if "doesn't exist" in err_msg.lower() or "1146" in err_msg:
            return {
                "ok": True,
                "accounts": [],
                "total_count": 0,
                "data_range": {"min": None, "max": None},
                "warning": "数据库表尚未初始化，请检查迁移是否执行"
            }
        # 其他数据库错误
        raise HTTPException(status_code=500, detail=f"数据库查询失败: {err_msg}")


@router.get("/api/operation/weekly-report")
def get_weekly_report(
    account: Optional[str] = None,
    weekStart: Optional[str] = None,
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """获取周报数据."""
    try:
        # 默认本周
        today = datetime.now()
        if not weekStart:
            # 计算本周周一
            week_start = today - timedelta(days=today.weekday())
            week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            week_start = datetime.strptime(weekStart, "%Y-%m-%d")

        # 周结束时间：下周一0点（包含完整一周数据）
        week_end = week_start + timedelta(days=7)

        where_clause = "start_time >= %s AND start_time < %s"
        params = [week_start.strftime("%Y-%m-%d %H:%M:%S"), week_end.strftime("%Y-%m-%d %H:%M:%S")]

        if account:
            where_clause += " AND account = %s"
            params.append(account)

        # 直播数据
        live_rows = db.fetch_all(
            f"""
            SELECT account, room_id, title, start_time, duration, pcu, acu,
                   show_ucnt, watch_ucnt, fans_watch_ucnt, non_fans_watch_ucnt,
                   avg_watch_duration, fans_avg_watch_duration, non_fans_avg_watch_duration,
                   follow_ucnt, follow_u_rate
            FROM finvue_operation_live_stats
            WHERE {where_clause}
            ORDER BY account, start_time
            """,
            tuple(params)
        )

        # 短视频数据
        video_rows = db.fetch_all(
            f"""
            SELECT account, title, publish_time, duration_type, play_count,
                   like_count, completion_rate,
                   `5s_completion_rate` as five_s_completion_rate,
                   `2s_exit_rate` as two_s_exit_rate,
                   interaction_rate, follow_count
            FROM finvue_operation_video_stats
            WHERE publish_time >= %s AND publish_time < %s
            {f"AND account = %s" if account else ""}
            ORDER BY account, publish_time
            """,
            tuple(params)
        )

        # 按账号分组
        accounts_data = {}
        for row in live_rows or []:
            acc = row["account"]
            if acc not in accounts_data:
                accounts_data[acc] = {"account": acc, "live": [], "video": [], "stats": {"liveCount": 0, "totalFollow": 0}}
            # 转换 datetime 为字符串
            if row.get("start_time"):
                if isinstance(row["start_time"], datetime):
                    row["start_time"] = row["start_time"].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    row["start_time"] = str(row["start_time"])
            accounts_data[acc]["live"].append(row)
            accounts_data[acc]["stats"]["liveCount"] += 1
            accounts_data[acc]["stats"]["totalFollow"] += int(row.get("follow_ucnt") or 0)

        for row in video_rows or []:
            acc = row["account"]
            if acc not in accounts_data:
                accounts_data[acc] = {"account": acc, "live": [], "video": [], "stats": {"liveCount": 0, "totalFollow": 0}}
            accounts_data[acc]["video"].append(row)

        return {
            "ok": True,
            "weekStart": week_start.strftime("%Y-%m-%d"),
            "weekEnd": (week_start + timedelta(days=6)).strftime("%Y-%m-%d"),
            "accounts": list(accounts_data.values())
        }
    except Exception as e:
        err_msg = str(e)
        if "doesn't exist" in err_msg.lower() or "1146" in err_msg:
            return {"ok": True, "accounts": [], "warning": "数据库表尚未初始化"}
        raise HTTPException(status_code=500, detail=f"查询失败: {err_msg}")


@router.get("/api/operation/monthly-report")
def get_monthly_report(
    account: Optional[str] = None,
    month: Optional[str] = None,
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """获取月报数据."""
    try:
        if not month:
            month = datetime.now().strftime("%Y-%m")

        year, mon = month.split("-")
        month_start = datetime(int(year), int(mon), 1)
        if int(mon) == 12:
            month_end = datetime(int(year) + 1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(int(year), int(mon) + 1, 1) - timedelta(seconds=1)

        where_clause = "start_time >= %s AND start_time <= %s"
        params = [month_start.strftime("%Y-%m-%d %H:%M:%S"), month_end.strftime("%Y-%m-%d %H:%M:%S")]

        if account:
            where_clause += " AND account = %s"
            params.append(account)

        # 直播数据
        live_rows = db.fetch_all(
            f"""
            SELECT account, room_id, title, start_time, duration, pcu, acu,
                   show_ucnt, watch_ucnt, fans_watch_ucnt, non_fans_watch_ucnt,
                   avg_watch_duration, fans_avg_watch_duration, non_fans_avg_watch_duration,
                   follow_ucnt, follow_u_rate, earn_score, consume_ucnt
            FROM finvue_operation_live_stats
            WHERE {where_clause}
            ORDER BY account, start_time
            """,
            tuple(params)
        )

        # 短视频数据
        video_rows = db.fetch_all(
            f"""
            SELECT account, title, publish_time, duration_type, play_count,
                   like_count, completion_rate,
                   `5s_completion_rate` as five_s_completion_rate,
                   `2s_exit_rate` as two_s_exit_rate,
                   interaction_rate, follow_count
            FROM finvue_operation_video_stats
            WHERE publish_time >= %s AND publish_time < %s
            {f"AND account = %s" if account else ""}
            ORDER BY account, publish_time
            """,
            tuple(params)
        )

        # 转换 datetime 为字符串
        for row in live_rows or []:
            if row.get("start_time"):
                if isinstance(row["start_time"], datetime):
                    row["start_time"] = row["start_time"].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    row["start_time"] = str(row["start_time"])

        for row in video_rows or []:
            if row.get("publish_time"):
                if isinstance(row["publish_time"], datetime):
                    row["publish_time"] = row["publish_time"].strftime("%Y-%m-%d %H:%M:%S")
                else:
                    row["publish_time"] = str(row["publish_time"])

        # 历史分月统计
        history_rows = db.fetch_all(
            f"""
            SELECT account, DATE_FORMAT(start_time, '%%Y-%%m') as month,
                   COUNT(*) as live_count,
                   AVG(acu) as avg_acu,
                   AVG(watch_ucnt) as avg_watch,
                   AVG(fans_watch_ucnt) as avg_fans_watch,
                   AVG(non_fans_watch_ucnt) as avg_non_fans_watch,
                   AVG(avg_watch_duration) as avg_duration,
                   AVG(fans_avg_watch_duration) as avg_fans_duration,
                   AVG(non_fans_avg_watch_duration) as avg_non_fans_duration,
                   SUM(follow_ucnt) as total_follow
            FROM finvue_operation_live_stats
            {f"WHERE account = %s" if account else ""}
            GROUP BY account, DATE_FORMAT(start_time, '%%Y-%%m')
            ORDER BY account, month DESC
            """,
            tuple([account] if account else [])
        )

        # 累计场次统计
        total_rows = db.fetch_all(
            f"""
            SELECT account, COUNT(*) as total_live_count
            FROM finvue_operation_live_stats
            {f"WHERE account = %s" if account else ""}
            GROUP BY account
            """,
            tuple([account] if account else [])
        )

        # 当月每日在线人数统计（按主播分组，用于折线图）
        daily_rows_by_anchor = db.fetch_all(
            f"""
            SELECT account, DATE(start_time) as day,
                   AVG(acu) as avg_acu,
                   MAX(pcu) as max_pcu,
                   COUNT(*) as live_count,
                   AVG(avg_watch_duration) as avg_duration,
                   AVG(fans_avg_watch_duration) as fans_avg_duration,
                   AVG(non_fans_avg_watch_duration) as non_fans_avg_duration
            FROM finvue_operation_live_stats
            WHERE {where_clause}
            GROUP BY account, DATE(start_time)
            ORDER BY account, day
            """,
            tuple(params)
        )

        # 按主播组织每日数据（包含在线人数和停留时长）
        daily_by_anchor = {}
        for row in daily_rows_by_anchor or []:
            acc = row["account"] or "未知主播"
            if acc not in daily_by_anchor:
                daily_by_anchor[acc] = []
            daily_by_anchor[acc].append({
                "day": str(row["day"]),
                "avg_acu": float(row["avg_acu"] or 0),
                "max_pcu": int(row["max_pcu"] or 0),
                "live_count": int(row["live_count"] or 0),
                "avg_duration": round(float(row["avg_duration"] or 0), 1),
                "fans_avg_duration": round(float(row["fans_avg_duration"] or 0), 1),
                "non_fans_avg_duration": round(float(row["non_fans_avg_duration"] or 0), 1)
            })

        return {
            "ok": True,
            "month": month,
            "live": live_rows or [],
            "video": video_rows or [],
            "history": history_rows or [],
            "totals": total_rows or [],
            "daily_by_anchor": daily_by_anchor
        }
    except Exception as e:
        err_msg = str(e)
        if "doesn't exist" in err_msg.lower() or "1146" in err_msg:
            return {"ok": True, "live": [], "video": [], "warning": "数据库表尚未初始化"}
        raise HTTPException(status_code=500, detail=f"查询失败: {err_msg}")


@router.get("/api/operation/calendar")
def get_calendar(
    year: int,
    month: int,
    account: Optional[str] = None,
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """获取直播日历数据."""
    try:
        month_start = datetime(year, month, 1)
        if month == 12:
            month_end = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            month_end = datetime(year, month + 1, 1) - timedelta(seconds=1)

        where_clause = "start_time >= %s AND start_time <= %s"
        params = [month_start.strftime("%Y-%m-%d %H:%M:%S"), month_end.strftime("%Y-%m-%d %H:%M:%S")]

        if account:
            where_clause += " AND account = %s"
            params.append(account)

        rows = db.fetch_all(
            f"""
            SELECT account, room_id, title, start_time, duration, pcu, acu,
                   watch_ucnt, follow_ucnt, earn_score
            FROM finvue_operation_live_stats
            WHERE {where_clause}
            ORDER BY start_time
            """,
            tuple(params)
        )

        # 按日期分组
        days = {}
        for row in rows or []:
            start_time = row.get("start_time")
            if start_time:
                # 处理 datetime 对象或字符串，确保格式为 "YYYY-MM-DD HH:MM:SS"
                if isinstance(start_time, datetime):
                    start_time_str = start_time.strftime("%Y-%m-%d %H:%M:%S")
                    date_str = start_time.strftime("%Y-%m-%d")
                else:
                    start_time_str = str(start_time)
                    date_str = start_time_str.split(" ")[0]
                # 更新 row 中的 start_time 为字符串格式
                row["start_time"] = start_time_str
            else:
                continue
            if date_str not in days:
                days[date_str] = {"count": 0, "lives": []}
            days[date_str]["count"] += 1
            days[date_str]["lives"].append(row)

        return {"ok": True, "year": year, "month": month, "days": days}
    except Exception as e:
        import traceback
        print(f"[calendar] Error: {e}")
        traceback.print_exc()
        return {"ok": False, "error": str(e), "year": year, "month": month, "days": {}}


@router.post("/api/operation/add-live")
async def add_live_record(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """手工添加直播记录."""
    body = await request.json()
    account = str(body.get("account") or "").strip()
    live_date = str(body.get("live_date") or "").strip()
    live_time = str(body.get("live_time") or "").strip()
    duration = int(body.get("duration") or 0)
    title = str(body.get("title") or "").strip()
    notes = str(body.get("notes") or "").strip()

    if not account or not live_date:
        return {"ok": False, "error": "主播和直播日期必填"}

    # 组合开始时间
    if live_time:
        start_time = f"{live_date} {live_time}:00"
    else:
        start_time = f"{live_date} 00:00:00"

    # 生成一个唯一的 room_id (用于手工录入的记录)
    import hashlib
    room_id = hashlib.md5(f"{account}{live_date}{live_time}".encode()).hexdigest()[:19]

    # 给notes添加手工录入标识（用于区分可删除的记录）
    if notes:
        notes = f"[手工录入] {notes}"
    else:
        notes = "[手工录入]"

    try:
        db.execute(
            """
            INSERT INTO finvue_operation_live_stats
            (account, room_id, title, start_time, duration, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (account, room_id, title, start_time, duration, notes)
        )
        
        # 记录操作日志
        session = security.require_auth(request)
        username = session.get("username")
        user_id = session.get("user_id")
        ip = get_client_ip(request)
        
        logger.log_create(
            module="operation",
            target_type="live_record",
            target_id=room_id,
            title=f"手工添加直播记录: {account}",
            description=f"为主播 {account} 手工添加直播记录，开播时间：{start_time}，时长：{duration}分钟",
            username=username,
            user_id=user_id,
            status="success",
            request_ip=ip,
        )
        
        return {"ok": True, "message": "添加成功"}
    except Exception as e:
        # 记录失败日志
        session = security.require_auth(request)
        username = session.get("username") if session else None
        user_id = session.get("user_id") if session else None
        ip = get_client_ip(request)
        
        logger.log_create(
            module="operation",
            target_type="live_record",
            target_id=room_id,
            title=f"手工添加直播记录失败: {account}",
            description=f"为主播 {account} 手工添加直播记录失败",
            username=username,
            user_id=user_id,
            status="failed",
            error_message=str(e),
            request_ip=ip,
        )
        return {"ok": False, "error": str(e)}


@router.get("/api/operation/import-logs")
def get_import_logs(
    importType: Optional[str] = None,
    limit: int = 20,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """获取导入日志."""
    where = "1=1"
    params = []
    if importType:
        where = "import_type = %s"
        params.append(importType)

    rows = db.fetch_all(
        f"""
        SELECT id, import_type, file_name, record_count, account_count,
               status, error_message, imported_by, imported_at, mode
        FROM finvue_operation_import_logs
        WHERE {where}
        ORDER BY imported_at DESC
        LIMIT %s
        """,
        tuple(params + [limit])
    )
    return {"ok": True, "logs": rows or []}


@router.get("/api/operation/anchor-summary")
def get_anchor_summary(
    account: str,
    _: dict = Depends(security.require_permission("home"))
) -> dict:
    """获取单个主播的直播数据汇总（用于主播资料库、主播画像等页面）."""
    if not account:
        return {"ok": False, "error": "缺少主播账号参数"}

    # 汇总统计
    summary = db.fetch_one(
        """
        SELECT
            COUNT(*) as total_lives,
            SUM(duration) as total_duration,
            AVG(duration) as avg_duration,
            MAX(pcu) as max_pcu,
            AVG(acu) as avg_acu,
            SUM(watch_ucnt) as total_watch,
            AVG(watch_ucnt) as avg_watch,
            SUM(follow_ucnt) as total_follow,
            AVG(follow_ucnt) as avg_follow,
            SUM(earn_score) as total_earn,
            AVG(earn_score) as avg_earn,
            MIN(start_time) as first_live,
            MAX(start_time) as last_live
        FROM finvue_operation_live_stats
        WHERE account = %s
        """,
        (account,)
    )

    # 最近10场直播
    recent_lives = db.fetch_all(
        """
        SELECT
            start_time, duration, pcu, acu, watch_ucnt, follow_ucnt, earn_score, title
        FROM finvue_operation_live_stats
        WHERE account = %s
        ORDER BY start_time DESC
        LIMIT 10
        """,
        (account,)
    )

    # 转换 datetime 为字符串
    if summary and summary.get("first_live"):
        if isinstance(summary["first_live"], datetime):
            summary["first_live"] = summary["first_live"].strftime("%Y-%m-%d")
    if summary and summary.get("last_live"):
        if isinstance(summary["last_live"], datetime):
            summary["last_live"] = summary["last_live"].strftime("%Y-%m-%d")

    for row in recent_lives or []:
        if row.get("start_time"):
            if isinstance(row["start_time"], datetime):
                row["start_time"] = row["start_time"].strftime("%Y-%m-%d %H:%M")

    return {
        "ok": True,
        "account": account,
        "summary": summary or {},
        "recent_lives": recent_lives or []
    }


@router.get("/api/operation/home-overview")
def get_home_overview(_: dict = Depends(security.require_permission("home"))) -> dict:
    """获取工作台概览数据（一次性获取所有数据，减少前端请求次数）."""
    try:
        now = datetime.now()
        current_month = now.strftime("%Y-%m")
        current_week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")

        # 1. 主播列表（带汇总数据）
        anchors = db.fetch_all(
            """
            SELECT
                account,
                COUNT(*) as live_count,
                SUM(duration) as total_duration,
                AVG(duration) as avg_duration,
                MAX(pcu) as max_pcu,
                AVG(acu) as avg_acu,
                SUM(watch_ucnt) as total_watch,
                AVG(watch_ucnt) as avg_watch,
                SUM(follow_ucnt) as total_follow,
                AVG(follow_ucnt) as avg_follow,
                SUM(earn_score) as total_earn,
                MAX(start_time) as last_live_time,
                MIN(start_time) as first_live_time,
                SUM(CASE WHEN DATE_FORMAT(start_time, '%%Y-%%m') = %s THEN 1 ELSE 0 END) as month_live_count,
                SUM(CASE WHEN DATE_FORMAT(start_time, '%%Y-%%m') = %s THEN watch_ucnt ELSE 0 END) as month_watch,
                SUM(CASE WHEN DATE_FORMAT(start_time, '%%Y-%%m') = %s THEN follow_ucnt ELSE 0 END) as month_follow
            FROM finvue_operation_live_stats
            GROUP BY account
            ORDER BY live_count DESC
            """,
            (current_month, current_month, current_month)
        )

        # 2. 本月汇总
        month_summary = db.fetch_one(
            """
            SELECT
                COUNT(*) as month_live_count,
                SUM(duration) as month_duration,
                SUM(watch_ucnt) as month_watch,
                SUM(follow_ucnt) as month_follow,
                SUM(earn_score) as month_earn,
                AVG(acu) as month_avg_acu
            FROM finvue_operation_live_stats
            WHERE DATE_FORMAT(start_time, '%%Y-%%m') = %s
            """,
            (current_month,)
        )

        # 3. 本周汇总
        week_summary = db.fetch_one(
            """
            SELECT
                COUNT(*) as week_live_count,
                SUM(duration) as week_duration,
                SUM(watch_ucnt) as week_watch,
                SUM(follow_ucnt) as week_follow,
                SUM(earn_score) as week_earn
            FROM finvue_operation_live_stats
            WHERE DATE(start_time) >= %s
            """,
            (current_week_start,)
        )

        # 4. 数据总体信息
        total_info = db.fetch_one(
            """
            SELECT
                COUNT(*) as total_count,
                COUNT(DISTINCT account) as anchor_count,
                MAX(start_time) as max_time,
                MIN(start_time) as min_time
            FROM finvue_operation_live_stats
            """
        )

        # 5. 最近7天每日数据（用于趋势图）
        daily_trend = db.fetch_all(
            """
            SELECT
                DATE(start_time) as date,
                COUNT(*) as live_count,
                SUM(watch_ucnt) as watch,
                SUM(follow_ucnt) as follow,
                AVG(acu) as avg_acu
            FROM finvue_operation_live_stats
            WHERE DATE(start_time) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY DATE(start_time)
            ORDER BY date
            """
        )

        # 6. 最近活跃主播（7天内直播过的）
        active_anchors = db.fetch_all(
            """
            SELECT DISTINCT account, MAX(start_time) as last_live
            FROM finvue_operation_live_stats
            WHERE DATE(start_time) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
            GROUP BY account
            ORDER BY last_live DESC
            """
        )

        return {
            "ok": True,
            "anchors": anchors or [],
            "month_summary": month_summary or {},
            "week_summary": week_summary or {},
            "total_info": total_info or {},
            "daily_trend": daily_trend or [],
            "active_anchors": active_anchors or [],
            "current_month": current_month
        }
    except Exception as e:
        import traceback
        print(f"[home-overview] Error: {e}")
        traceback.print_exc()
        return {"ok": False, "error": str(e), "anchors": [], "month_summary": {}, "week_summary": {}, "total_info": {}, "daily_trend": [], "active_anchors": []}

# ═══════════════════════════════════════════════════════════════
# 在线导入接口：从远程数据库直接拉取数据导入到本地数据库
# ═══════════════════════════════════════════════════════════════

import config

def _get_remote_db_connection():
    """获取远程数据库连接."""
    import pymysql
    return pymysql.connect(
        host=config.REMOTE_DB_HOST,
        port=config.REMOTE_DB_PORT,
        user=config.REMOTE_DB_USER,
        password=config.REMOTE_DB_PASSWORD,
        database=config.REMOTE_DB_DATABASE,
        connect_timeout=30,
        charset='utf8mb4'
    )


@router.post("/api/operation/online-import-live")
async def online_import_live_data(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """从远程数据库在线导入直播数据."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    session = security.require_auth(request)
    username = session.get("username")
    ip = get_client_ip(request)

    try:
        # 判断本地表状态：是否为空、最新数据时间
        local_count = db.fetch_one("SELECT COUNT(*) AS count FROM finvue_operation_live_stats")["count"]
        local_max_time = None
        if local_count > 0:
            result = db.fetch_one("SELECT MAX(start_time) AS max_time FROM finvue_operation_live_stats")
            local_max_time = result.get("max_time")
        
        is_full_import = local_count == 0
        import_mode = "全量导入" if is_full_import else "增量导入"
        
        # 连接远程数据库
        remote_conn = _get_remote_db_connection()
        remote_cursor = remote_conn.cursor()

        # 构建查询：全量导入不加时间条件，增量导入只查比本地最新时间更新的数据
        if is_full_import:
            remote_cursor.execute("""
                SELECT account, room_id, title, startTime, endTime, duration,
                       pcu, acu, earnScore, fansEarnScore, nonFansEarnScore, firstEarnScore,
                       consumeUcnt, fansConsumeUcnt, nonFansConsumeUcnt, firstConsumeUcnt,
                       expectedTotalIncome, showUcnt, watchUcnt, fansWatchUcnt, nonFansWatchUcnt,
                       followUcnt, unfollowUcnt, joinFansClubUcnt,
                       avgWatchDuration, fansAvgWatchDuration, nonFansAvgWatchDuration,
                       commentUcnt, fansCommentUcnt, nonFansCommentUcnt,
                       likeCnt, fansLikeCnt, nonFansLikeCnt,
                       shareCnt, fansShareCnt, nonFansShareCnt,
                       fansInGroup, fansOutGroup,
                       watchURate, followURate, commentURate, consumeURate,
                       fansWatchURate, fansCommentURate, fansLikeRate, fansShareRate, fansConsumeURate, fansInGroupRate,
                       created_at
                FROM douyin_creator_live_overview
                ORDER BY startTime DESC
            """)
        else:
            remote_cursor.execute("""
                SELECT account, room_id, title, startTime, endTime, duration,
                       pcu, acu, earnScore, fansEarnScore, nonFansEarnScore, firstEarnScore,
                       consumeUcnt, fansConsumeUcnt, nonFansConsumeUcnt, firstConsumeUcnt,
                       expectedTotalIncome, showUcnt, watchUcnt, fansWatchUcnt, nonFansWatchUcnt,
                       followUcnt, unfollowUcnt, joinFansClubUcnt,
                       avgWatchDuration, fansAvgWatchDuration, nonFansAvgWatchDuration,
                       commentUcnt, fansCommentUcnt, nonFansCommentUcnt,
                       likeCnt, fansLikeCnt, nonFansLikeCnt,
                       shareCnt, fansShareCnt, nonFansShareCnt,
                       fansInGroup, fansOutGroup,
                       watchURate, followURate, commentURate, consumeURate,
                       fansWatchURate, fansCommentURate, fansLikeRate, fansShareRate, fansConsumeURate, fansInGroupRate,
                       created_at
                FROM douyin_creator_live_overview
                WHERE startTime > %s
                ORDER BY startTime DESC
            """, (local_max_time,))
        rows = remote_cursor.fetchall()
        remote_cursor.close()
        remote_conn.close()

        # 批量插入本地数据库
        count = 0
        batch = []
        for row in rows:
            batch.append((
                row[0] or '',  # account
                str(row[1]) if row[1] else '',  # room_id
                row[2] or '',  # title
                row[3],  # start_time
                row[4],  # end_time
                row[5] or 0,  # duration
                row[6] or 0,  # pcu
                row[7] or 0,  # acu
                row[8] or 0,  # earn_score
                row[9] or 0,  # fans_earn_score
                row[10] or 0,  # non_fans_earn_score
                row[11] or 0,  # first_earn_score
                row[12] or 0,  # consume_ucnt
                row[13] or 0,  # fans_consume_ucnt
                row[14] or 0,  # non_fans_consume_ucnt
                row[15] or 0,  # first_consume_ucnt
                row[16] or 0,  # expected_total_income
                row[17] or 0,  # show_ucnt
                row[18] or 0,  # watch_ucnt
                row[19] or 0,  # fans_watch_ucnt
                row[20] or 0,  # non_fans_watch_ucnt
                row[21] or 0,  # follow_ucnt
                row[22] or 0,  # unfollow_ucnt
                row[23] or 0,  # join_fansclub_ucnt
                row[24] or 0,  # avg_watch_duration
                row[25] or 0,  # fans_avg_watch_duration
                row[26] or 0,  # non_fans_avg_watch_duration
                row[27] or 0,  # comment_ucnt
                row[28] or 0,  # fans_comment_ucnt
                row[29] or 0,  # non_fans_comment_ucnt
                row[30] or 0,  # like_cnt
                row[31] or 0,  # fans_like_cnt
                row[32] or 0,  # non_fans_like_cnt
                row[33] or 0,  # share_cnt
                row[34] or 0,  # fans_share_cnt
                row[35] or 0,  # non_fans_share_cnt
                row[36] or 0,  # fans_in_group
                row[37] or 0,  # fans_out_group
                float(row[38] or 0),  # watch_u_rate
                float(row[39] or 0),  # follow_u_rate
                float(row[40] or 0),  # comment_u_rate
                float(row[41] or 0),  # consume_u_rate
                float(row[42] or 0),  # fans_watch_u_rate
                float(row[43] or 0),  # fans_comment_rate
                float(row[44] or 0),  # fans_like_rate
                float(row[45] or 0),  # fans_share_rate
                float(row[46] or 0),  # fans_consume_u_rate
                float(row[47] or 0),  # fans_in_group_rate
                row[48]  # created_at
            ))
            count += 1

            if len(batch) >= 500:
                _insert_live_batch(batch)
                batch = []

        if batch:
            _insert_live_batch(batch)

        # 记录导入日志
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, status, imported_by, mode)
            VALUES ('live', '在线导入', %s, 'success', %s, 'online')
            """,
            (count, username)
        )

        logger.log_import(
            module="operation",
            title=f"在线导入直播数据（{import_mode})",
            description=f"从远程数据库{import_mode} {count} 条直播记录" + (f"，截止时间 {local_max_time}" if local_max_time else ""),
            username=username,
            record_count=count,
            status="success",
            request_ip=ip,
        )

        return {"ok": True, "message": f"成功{import_mode} {count} 条直播数据", "count": count, "mode": import_mode}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


def _insert_live_batch(batch: list) -> None:
    """批量插入直播数据."""
    db.executemany(
        """
        INSERT INTO finvue_operation_live_stats
        (account, room_id, title, start_time, end_time, duration,
         pcu, acu, earn_score, fans_earn_score, non_fans_earn_score, first_earn_score,
         consume_ucnt, fans_consume_ucnt, non_fans_consume_ucnt, first_consume_ucnt,
         expected_total_income, show_ucnt, watch_ucnt, fans_watch_ucnt, non_fans_watch_ucnt,
         follow_ucnt, unfollow_ucnt, join_fansclub_ucnt,
         avg_watch_duration, fans_avg_watch_duration, non_fans_avg_watch_duration,
         comment_ucnt, fans_comment_ucnt, non_fans_comment_ucnt,
         like_cnt, fans_like_cnt, non_fans_like_cnt,
         share_cnt, fans_share_cnt, non_fans_share_cnt,
         fans_in_group, fans_out_group,
         watch_u_rate, follow_u_rate, comment_u_rate, consume_u_rate,
         fans_watch_u_rate, fans_comment_u_rate, fans_like_rate, fans_share_rate, fans_consume_u_rate, fans_in_group_rate,
         created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        duration = VALUES(duration),
        pcu = VALUES(pcu),
        acu = VALUES(acu),
        earn_score = VALUES(earn_score),
        watch_ucnt = VALUES(watch_ucnt),
        follow_ucnt = VALUES(follow_ucnt)
        """,
        batch
    )


@router.post("/api/operation/online-import-video")
async def online_import_video_data(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """从远程数据库在线导入短视频数据."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    session = security.require_auth(request)
    username = session.get("username")
    ip = get_client_ip(request)

    try:
        # 判断本地表状态：是否为空、最新数据时间
        local_count = db.fetch_one("SELECT COUNT(*) AS count FROM finvue_operation_video_stats")["count"]
        local_max_time = None
        if local_count > 0:
            result = db.fetch_one("SELECT MAX(publish_time) AS max_time FROM finvue_operation_video_stats")
            local_max_time = result.get("max_time")
        
        is_full_import = local_count == 0
        import_mode = "全量导入" if is_full_import else "增量导入"
        
        # 连接远程数据库
        remote_conn = _get_remote_db_connection()
        remote_cursor = remote_conn.cursor()

        # 查询远程短视频数据（匹配远程表实际字段）
        if is_full_import:
            remote_cursor.execute("""
                SELECT account, id, video_title, publish_time, genre,
                       play_count, like_count, comment_count, share_count,
                       completion_rate, five_second_completion_rate, two_second_bounce_rate,
                       fan_increment, created_at
                FROM douyin_video_list
                ORDER BY publish_time DESC
            """)
        else:
            remote_cursor.execute("""
                SELECT account, id, video_title, publish_time, genre,
                       play_count, like_count, comment_count, share_count,
                       completion_rate, five_second_completion_rate, two_second_bounce_rate,
                       fan_increment, created_at
                FROM douyin_video_list
                WHERE publish_time > %s
                ORDER BY publish_time DESC
            """, (local_max_time,))
        rows = remote_cursor.fetchall()
        remote_cursor.close()
        remote_conn.close()

        # 批量插入本地数据库（远程字段映射到本地表）
        count = 0
        batch = []
        for row in rows:
            batch.append((
                row[0] or '',  # account
                str(row[1]) if row[1] else '',  # video_id (来自远程 id)
                row[2] or '',  # title (来自远程 video_title)
                row[3],  # publish_time
                row[4] or '',  # duration_type (来自远程 genre)
                row[5] or 0,  # play_count
                row[6] or 0,  # like_count
                row[7] or 0,  # comment_count
                row[8] or 0,  # share_count
                float(row[9] or 0),  # completion_rate
                float(row[10] or 0),  # 5s_completion_rate (来自远程 five_second_completion_rate)
                float(row[11] or 0),  # 2s_exit_rate (来自远程 two_second_bounce_rate)
                0.0,  # interaction_rate (远程无此字段，默认0)
                row[12] or 0,  # follow_count (来自远程 fan_increment)
                row[13]  # created_at
            ))
            count += 1

            if len(batch) >= 500:
                _insert_video_batch(batch)
                batch = []

        if batch:
            _insert_video_batch(batch)

        # 记录导入日志
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, status, imported_by, mode)
            VALUES ('video', '在线导入', %s, 'success', %s, 'online')
            """,
            (count, username)
        )

        logger.log_import(
            module="operation",
            title=f"在线导入短视频数据（{import_mode})",
            description=f"从远程数据库{import_mode} {count} 条短视频记录" + (f"，截止时间 {local_max_time}" if local_max_time else ""),
            username=username,
            record_count=count,
            status="success",
            request_ip=ip,
        )

        return {"ok": True, "message": f"成功{import_mode} {count} 条短视频数据", "count": count, "mode": import_mode}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


def _insert_video_batch(batch: list) -> None:
    """批量插入短视频数据."""
    db.executemany(
        """
        INSERT INTO finvue_operation_video_stats
        (account, video_id, title, publish_time, duration_type,
         play_count, like_count, comment_count, share_count,
         completion_rate, 5s_completion_rate, 2s_exit_rate,
         interaction_rate, follow_count, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        title = VALUES(title),
        play_count = VALUES(play_count),
        like_count = VALUES(like_count),
        comment_count = VALUES(comment_count),
        share_count = VALUES(share_count),
        completion_rate = VALUES(completion_rate),
        follow_count = VALUES(follow_count)
        """,
        batch
    )


@router.post("/api/operation/online-import-all")
async def online_import_all_data(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """一键在线导入所有数据（直播+短视频）."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    # 调用两个导入接口
    live_result = await online_import_live_data(request, _)
    video_result = await online_import_video_data(request, _)

    live_count = live_result.get("count", 0) if live_result.get("ok") else 0
    video_count = video_result.get("count", 0) if video_result.get("ok") else 0

    errors = []
    if not live_result.get("ok"):
        errors.append(f"直播数据导入失败: {live_result.get('error')}")
    if not video_result.get("ok"):
        errors.append(f"短视频数据导入失败: {video_result.get('error')}")

    if errors:
        return {
            "ok": False,
            "error": "; ".join(errors),
            "live_count": live_count,
            "video_count": video_count
        }

    return {
        "ok": True,
        "message": f"成功导入直播 {live_count} 条，短视频 {video_count} 条",
        "live_count": live_count,
        "video_count": video_count
    }


@router.post("/api/operation/online-import-customer-profiles")
async def online_import_customer_profiles(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """从远程数据库在线导入客户档案数据（从 rank_watch 字段解析）."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    session = security.require_auth(request)
    username = session.get("username")
    ip = get_client_ip(request)

    try:
        import_mode = "在线导入"  # 客户档案直接导入
        
        # 连接远程数据库
        remote_conn = _get_remote_db_connection()
        remote_cursor = remote_conn.cursor()

        # 直接查询数据（不排序，避免缓冲区溢出）
        remote_cursor.execute("""
            SELECT account, room_id, rank_watch, rank_like, rank_first, created_at
            FROM douyin_creator_live_room_analytics_data
            WHERE (rank_watch IS NOT NULL AND rank_watch != '')
               OR (rank_like IS NOT NULL AND rank_like != '')
               OR (rank_first IS NOT NULL AND rank_first != '')
        """)
        rows = remote_cursor.fetchall()
        remote_cursor.close()
        remote_conn.close()

        # 解析 rank_watch 数据并聚合客户档案
        import json
        customer_profiles = {}  # customer_id -> profile data
        
        # 解析三个榜单数据并聚合客户档案
        rank_fields = [
            ('rank_watch', '观看榜', 2),
            ('rank_like', '点赞榜', 3),
            ('rank_first', '首关榜', 4),
        ]

        for row in rows:
            anchor_name = row[0] or ''  # account 就是主播名称
            room_id = str(row[1]) if row[1] else ''
            created_at = row[5]

            # 解析三个榜单
            for field_name, metric_type, field_idx in rank_fields:
                rank_raw = row[field_idx] or ''
                if not rank_raw:
                    continue

                # 解析榜单 JSON
                try:
                    rank_data = json.loads(rank_raw) if isinstance(rank_raw, str) else rank_raw
                    if not isinstance(rank_data, list):
                        continue
                except:
                    continue

                for rank_item in rank_data:
                    # 用户信息在 rank_item.user 中
                    user = rank_item.get('user') or {}
                    customer_id = str(user.get('id_str') or user.get('id') or '').strip()
                    if not customer_id:
                        continue

                    customer_name = str(user.get('nickname') or '').strip()
                    watch_rank = int(rank_item.get('rank') or 0)
                    watch_duration = int(rank_item.get('watch_time') or 0)

                # 获取或创建客户档案
                if customer_id not in customer_profiles:
                    customer_profiles[customer_id] = {
                        'customer_id': customer_id,
                        'customer_name': customer_name,
                        'latest_anchor_name': anchor_name,
                        'latest_analyzed_at': created_at,
                        'latest_live_theme': '',
                        'latest_rank': watch_rank,
                        'best_rank': watch_rank,
                        'avg_watch_seconds': watch_duration,
                        'labels': [],
                        'tags': [],
                    }
                else:
                    # 更新档案（保留最新数据）
                    profile = customer_profiles[customer_id]
                    if created_at and (not profile['latest_analyzed_at'] or created_at > profile['latest_analyzed_at']):
                        profile['latest_analyzed_at'] = created_at
                        profile['latest_anchor_name'] = anchor_name
                        profile['latest_rank'] = watch_rank
                        profile['customer_name'] = customer_name or profile['customer_name']
                    # 更新最佳排名
                    if watch_rank > 0 and (profile['best_rank'] == 0 or watch_rank < profile['best_rank']):
                        profile['best_rank'] = watch_rank
                    # 累计观看时长（用于计算平均）
                    profile['avg_watch_seconds'] = (profile['avg_watch_seconds'] + watch_duration) // 2

        # 批量插入客户档案
        count = 0
        batch = []
        for customer_id, profile in customer_profiles.items():
            batch.append((
                profile['customer_id'],
                profile['customer_name'],
                profile['latest_anchor_name'],
                profile['latest_analyzed_at'],
                profile['latest_live_theme'],
                profile['latest_rank'],
                profile['best_rank'],
                profile['avg_watch_seconds'],
                json.dumps(profile['labels']),
                json.dumps(profile['tags']),
                '{}',
            ))
            count += 1

            if len(batch) >= 500:
                _insert_customer_profiles_batch(batch)
                batch = []

        if batch:
            _insert_customer_profiles_batch(batch)

        # 记录导入日志
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, status, imported_by, mode)
            VALUES ('customer_profiles', '在线导入', %s, 'success', %s, 'online')
            """,
            (count, username)
        )

        logger.log_import(
            module="operation",
            title="在线导入客户档案",
            description=f"从远程数据库导入 {count} 条客户档案",
            username=username,
            record_count=count,
            status="success",
            request_ip=ip,
        )

        return {"ok": True, "message": f"成功{import_mode} {count} 条客户档案", "count": count, "mode": import_mode}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


def _insert_customer_profiles_batch(batch: list) -> None:
    """批量插入客户档案."""
    db.executemany(
        """
        INSERT INTO finvue_customer_profiles
        (customer_id, customer_name, latest_anchor_name, latest_analyzed_at,
         latest_live_theme, latest_rank, best_rank, avg_watch_seconds, labels, tags, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        customer_name = VALUES(customer_name),
        latest_anchor_name = VALUES(latest_anchor_name),
        latest_analyzed_at = VALUES(latest_analyzed_at),
        latest_live_theme = VALUES(latest_live_theme),
        latest_rank = VALUES(latest_rank),
        best_rank = IF(VALUES(best_rank) > 0 AND (best_rank = 0 OR VALUES(best_rank) < best_rank), VALUES(best_rank), best_rank),
        avg_watch_seconds = VALUES(avg_watch_seconds)
        """,
        batch
    )


@router.post("/api/operation/online-import-customer-sessions")
async def online_import_customer_sessions(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """从远程数据库在线导入客户会话数据（从 rank_watch 字段解析）."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    session = security.require_auth(request)
    username = session.get("username")
    ip = get_client_ip(request)

    try:
        # 判断本地表状态：是否为空、最新数据时间
        local_count = db.fetch_one("SELECT COUNT(*) AS count FROM finvue_customer_sessions")["count"]
        local_max_time = None
        if local_count > 0:
            result = db.fetch_one("SELECT MAX(analyzed_at) AS max_time FROM finvue_customer_sessions")
            local_max_time = result.get("max_time")
        
        is_full_import = local_count == 0
        import_mode = "全量导入" if is_full_import else "增量导入"
        
        # 连接远程数据库
        remote_conn = _get_remote_db_connection()
        remote_cursor = remote_conn.cursor()

        # 构建查询：全量导入不加时间条件，增量导入只查比本地最新时间更新的数据
        # 直接查询数据（不排序，避免缓冲区溢出）
        if is_full_import:
            remote_cursor.execute("""
                SELECT account, room_id, rank_watch, rank_like, rank_first, created_at
                FROM douyin_creator_live_room_analytics_data
                WHERE (rank_watch IS NOT NULL AND rank_watch != '')
                   OR (rank_like IS NOT NULL AND rank_like != '')
                   OR (rank_first IS NOT NULL AND rank_first != '')
            """)
        else:
            remote_cursor.execute("""
                SELECT account, room_id, rank_watch, rank_like, rank_first, created_at
                FROM douyin_creator_live_room_analytics_data
                WHERE created_at > %s
                  AND ((rank_watch IS NOT NULL AND rank_watch != '')
                   OR (rank_like IS NOT NULL AND rank_like != '')
                   OR (rank_first IS NOT NULL AND rank_first != ''))
            """, (local_max_time,))
        rows = remote_cursor.fetchall()
        remote_cursor.close()
        remote_conn.close()

        # 解析三个榜单数据生成客户会话记录
        import json
        count = 0
        batch = []
        rank_fields = [
            ('rank_watch', '观看榜', 2),
            ('rank_like', '点赞榜', 3),
            ('rank_first', '首关榜', 4),
        ]

        for row in rows:
            anchor_name = row[0] or ''  # account 就是主播名称
            room_id = str(row[1]) if row[1] else ''
            created_at = row[5]

            # 解析三个榜单
            for field_name, metric_type, field_idx in rank_fields:
                rank_raw = row[field_idx] or ''
                if not rank_raw:
                    continue

                # 解析榜单 JSON（格式：[{user: {id, nickname, ...}, value, rank, watch_time, ...}]）
                try:
                    rank_data = json.loads(rank_raw) if isinstance(rank_raw, str) else rank_raw
                    if not isinstance(rank_data, list):
                        continue
                except:
                    continue

                for rank_item in rank_data:
                    # 用户信息在 rank_item.user 中
                    user = rank_item.get('user') or {}
                    customer_id = str(user.get('id_str') or user.get('id') or '').strip()
                    if not customer_id:
                        continue

                    customer_name = str(user.get('nickname') or '').strip()
                    watch_rank = int(rank_item.get('rank') or 0)
                    watch_duration = int(rank_item.get('watch_time') or 0)

                    # 生成 session_id
                    session_id = f"db::{room_id}::{metric_type}::{customer_id}"

                    batch.append((
                        session_id,
                        customer_id,
                        anchor_name,
                        room_id,
                        '',  # live_theme（远程表无此字段）
                        'dbLiveAnalytics',  # report_type
                        metric_type,
                        str(rank_item.get('value') or watch_rank),  # metric_value
                        watch_rank,
                        watch_duration,
                        created_at,
                        'douyin_creator_live_room_analytics_data',
                        '{}',
                    ))
                    count += 1

                    if len(batch) >= 500:
                        _insert_customer_sessions_batch(batch)
                        batch = []

        if batch:
            _insert_customer_sessions_batch(batch)

        # 记录导入日志
        db.execute(
            """
            INSERT INTO finvue_operation_import_logs
            (import_type, file_name, record_count, status, imported_by, mode)
            VALUES ('customer_sessions', '在线导入', %s, 'success', %s, 'online')
            """,
            (count, username)
        )

        logger.log_import(
            module="operation",
            title="在线导入客户会话",
            description=f"从远程数据库导入 {count} 条客户会话",
            username=username,
            record_count=count,
            status="success",
            request_ip=ip,
        )

        return {"ok": True, "message": f"成功{import_mode} {count} 条客户会话", "count": count, "mode": import_mode}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "error": str(e)}


def _insert_customer_sessions_batch(batch: list) -> None:
    """批量插入客户会话."""
    db.executemany(
        """
        INSERT INTO finvue_customer_sessions
        (session_id, customer_id, anchor_name, room_id, live_theme,
         report_type, metric_type, metric_value, watch_rank, watch_duration_seconds,
         analyzed_at, source_file, raw)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
        anchor_name = VALUES(anchor_name),
        live_theme = VALUES(live_theme),
        watch_rank = VALUES(watch_rank),
        watch_duration_seconds = VALUES(watch_duration_seconds),
        analyzed_at = VALUES(analyzed_at)
        """,
        batch
    )


@router.post("/api/operation/online-import-all")
async def online_import_all_data(
    request: Request,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """一键在线导入所有数据（直播+短视频+客户档案+客户会话）."""
    if not config.has_remote_db_config():
        return {"ok": False, "error": "远程数据库未配置"}

    # 调用四个导入接口
    live_result = await online_import_live_data(request, _)
    video_result = await online_import_video_data(request, _)
    profile_result = await online_import_customer_profiles(request, _)
    session_result = await online_import_customer_sessions(request, _)

    live_count = live_result.get("count", 0) if live_result.get("ok") else 0
    video_count = video_result.get("count", 0) if video_result.get("ok") else 0
    profile_count = profile_result.get("count", 0) if profile_result.get("ok") else 0
    session_count = session_result.get("count", 0) if session_result.get("ok") else 0

    errors = []
    if not live_result.get("ok"):
        errors.append(f"直播数据导入失败: {live_result.get('error')}")
    if not video_result.get("ok"):
        errors.append(f"短视频数据导入失败: {video_result.get('error')}")
    if not profile_result.get("ok"):
        errors.append(f"客户档案导入失败: {profile_result.get('error')}")
    if not session_result.get("ok"):
        errors.append(f"客户会话导入失败: {session_result.get('error')}")

    if errors:
        return {
            "ok": False,
            "error": "; ".join(errors),
            "live_count": live_count,
            "video_count": video_count,
            "profile_count": profile_count,
            "session_count": session_count
        }

    return {
        "ok": True,
        "message": f"成功导入直播 {live_count} 条，短视频 {video_count} 条，客户档案 {profile_count} 条，客户会话 {session_count} 条",
        "live_count": live_count,
        "video_count": video_count,
        "profile_count": profile_count,
        "session_count": session_count
    }




# ============= 直播明细 API =============

@router.get("/api/operation/live-details")
async def get_live_details(
    request: Request,
    account: str = "",
    start_date: str = "",
    end_date: str = "",
    page: int = 1,
    limit: int = 50,
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """获取直播明细列表（分页）."""
    try:
        # 构建查询条件
        where_clauses = []
        params = []
        
        if account:
            where_clauses.append("account = %s")
            params.append(account)
        
        if start_date:
            where_clauses.append("start_time >= %s")
            params.append(start_date)
        
        if end_date:
            where_clauses.append("start_time <= %s")
            params.append(end_date + " 23:59:59")
        
        where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) AS total FROM finvue_operation_live_stats{where_sql}"
        total = db.fetch_one(count_sql, params)["total"]
        
        # 分页查询
        offset = (page - 1) * limit
        detail_sql = f"""
            SELECT 
                account, room_id, title, start_time, end_time, duration,
                pcu, acu, show_ucnt, watch_ucnt, fans_watch_ucnt, non_fans_watch_ucnt,
                follow_ucnt, join_fansclub_ucnt,
                avg_watch_duration, fans_avg_watch_duration, non_fans_avg_watch_duration,
                like_cnt, comment_ucnt, fans_comment_ucnt, fans_like_cnt,
                watch_u_rate, follow_u_rate, comment_u_rate,
                fans_watch_u_rate, fans_comment_u_rate, fans_like_rate,
                fans_in_group, fans_out_group, fans_in_group_rate,
                earn_score, consume_ucnt
            FROM finvue_operation_live_stats
            {where_sql}
            ORDER BY start_time DESC
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        rows = db.fetch_all(detail_sql, params)
        
        # 格式化数据
        details = []
        for row in rows:
            details.append({
                "account": row.get("account") or "",
                "room_id": row.get("room_id") or "",
                "title": row.get("title") or "",
                "start_time": str(row.get("start_time") or ""),
                "end_time": str(row.get("end_time") or ""),
                "duration": row.get("duration") or 0,
                "pcu": row.get("pcu") or 0,
                "acu": row.get("acu") or 0,
                "show_ucnt": row.get("show_ucnt") or 0,
                "watch_ucnt": row.get("watch_ucnt") or 0,
                "fans_watch_ucnt": row.get("fans_watch_ucnt") or 0,
                "non_fans_watch_ucnt": row.get("non_fans_watch_ucnt") or 0,
                "follow_ucnt": row.get("follow_ucnt") or 0,
                "join_fansclub_ucnt": row.get("join_fansclub_ucnt") or 0,
                "avg_watch_duration": round(float(row.get("avg_watch_duration") or 0), 1),
                "fans_avg_watch_duration": round(float(row.get("fans_avg_watch_duration") or 0), 1),
                "non_fans_avg_watch_duration": round(float(row.get("non_fans_avg_watch_duration") or 0), 1),
                "like_cnt": row.get("like_cnt") or 0,
                "comment_ucnt": row.get("comment_ucnt") or 0,
                "fans_comment_ucnt": row.get("fans_comment_ucnt") or 0,
                "fans_like_cnt": row.get("fans_like_cnt") or 0,
                "watch_u_rate": round(float(row.get("watch_u_rate") or 0), 2),
                "follow_u_rate": round(float(row.get("follow_u_rate") or 0), 2),
                "comment_u_rate": round(float(row.get("comment_u_rate") or 0), 2),
                "fans_watch_u_rate": round(float(row.get("fans_watch_u_rate") or 0), 2),
                "fans_comment_u_rate": round(float(row.get("fans_comment_u_rate") or 0), 2),
                "fans_like_rate": round(float(row.get("fans_like_rate") or 0), 2),
                "fans_in_group": round(float(row.get("fans_in_group") or 0), 1),
                "fans_out_group": round(float(row.get("fans_out_group") or 0), 1),
                "fans_in_group_rate": round(float(row.get("fans_in_group_rate") or 0), 2),
                "earn_score": row.get("earn_score") or 0,
                "consume_ucnt": row.get("consume_ucnt") or 0,
            })
        
        return {
            "ok": True,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit,
            "details": details
        }
        
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/api/operation/live-detail-stats")
async def get_live_detail_stats(
    request: Request,
    account: str = "",
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """获取直播明细统计汇总."""
    try:
        # 构建查询条件
        where_sql = " WHERE account = %s" if account else ""
        params = [account] if account else []
        
        # 统计汇总
        stats_sql = f"""
            SELECT 
                COUNT(*) AS total_sessions,
                SUM(follow_ucnt) AS total_follow,
                AVG(duration) AS avg_duration,
                AVG(pcu) AS avg_pcu,
                AVG(watch_ucnt) AS avg_watch,
                AVG(follow_u_rate) AS avg_follow_rate
            FROM finvue_operation_live_stats
            {where_sql}
        """
        stats = db.fetch_one(stats_sql, params)
        
        return {
            "ok": True,
            "total_sessions": stats.get("total_sessions", 0),
            "total_follow": stats.get("total_follow", 0) or 0,
            "avg_duration": round(float(stats.get("avg_duration", 0) or 0), 1),
            "avg_pcu": round(float(stats.get("avg_pcu", 0) or 0), 1),
            "avg_watch": round(float(stats.get("avg_watch", 0) or 0), 1),
            "avg_follow_rate": round(float(stats.get("avg_follow_rate", 0) or 0), 2)
        }
        
    except Exception as e:
        return {"ok": False, "error": str(e)}
