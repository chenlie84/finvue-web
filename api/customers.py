from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, UploadFile, File

import db
import security
import store


router = APIRouter()


@router.get("/api/customer-library")
def get_customer_library(page: Optional[int] = None, pageSize: Optional[int] = None, q: str = "", mode: str = "", _: dict = Depends(security.require_permission("customer-library"))) -> dict:
    return store.get_customer_library(page, pageSize, q, mode)


@router.post("/api/customer-library")
async def post_customer_library(request: Request, _: dict = Depends(security.require_permission("customer-library"))) -> dict:
    return store.save_customer_library(await request.json())


@router.get("/api/customer-trends-summary")
def get_customer_trends(anchorName: str = "", _: dict = Depends(security.require_permission("customer-library"))) -> dict:
    return store.get_customer_trends_summary(anchorName)


@router.post("/api/customer-library/import-profiles")
async def import_customer_profiles(
    file: UploadFile = File(...),
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """导入客户档案 CSV（批量插入优化）."""
    if not file.filename.endswith('.csv'):
        return {"ok": False, "error": "请上传 CSV 文件"}

    try:
        content = await file.read()
        text = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text))

        count = 0
        batch = []
        batch_size = 500
        
        for row in reader:
            customer_id = row.get('客户ID') or row.get('customer_id')
            if not customer_id:
                continue

            customer_name = row.get('客户名称') or row.get('customer_name') or ''
            anchor_name = row.get('主播名称') or row.get('latest_anchor_name') or ''
            analyzed_at = row.get('最近分析时间') or row.get('latest_analyzed_at')
            live_theme = row.get('最近直播主题') or row.get('latest_live_theme') or ''
            latest_rank = int(row.get('最近排名') or row.get('latest_rank') or 0)
            best_rank = int(row.get('最佳排名') or row.get('best_rank') or 0)
            avg_watch = int(row.get('平均观看时长') or row.get('avg_watch_seconds') or 0)

            analyzed_at_dt = None
            if analyzed_at:
                try:
                    analyzed_at_dt = datetime.strptime(analyzed_at, '%Y-%m-%d %H:%M:%S')
                except:
                    pass

            batch.append((customer_id, customer_name, anchor_name, analyzed_at_dt,
                         live_theme, latest_rank, best_rank, avg_watch))
            count += 1

            if len(batch) >= batch_size:
                # 批量插入
                values_list = []
                for b in batch:
                    cid = b[0].replace("'", "''")
                    cname = b[1].replace("'", "''")
                    aname = b[2].replace("'", "''")
                    theme = b[4].replace("'", "''")
                    atime = f"'{b[3].strftime('%Y-%m-%d %H:%M:%S')}'" if b[3] else 'NULL'
                    values_list.append(f"('{cid}', '{cname}', '{aname}', {atime}, '{theme}', {b[5]}, {b[6]}, {b[7]}, '[]', '[]', '{{}}')")
                
                db.execute(f"""
                    INSERT INTO finvue_customer_profiles
                    (customer_id, customer_name, latest_anchor_name, latest_analyzed_at,
                     latest_live_theme, latest_rank, best_rank, avg_watch_seconds, labels, tags, raw)
                    VALUES {','.join(values_list)}
                    ON DUPLICATE KEY UPDATE
                    customer_name = VALUES(customer_name),
                    latest_anchor_name = VALUES(latest_anchor_name),
                    latest_analyzed_at = VALUES(latest_analyzed_at),
                    latest_live_theme = VALUES(latest_live_theme),
                    latest_rank = VALUES(latest_rank),
                    best_rank = VALUES(best_rank),
                    avg_watch_seconds = VALUES(avg_watch_seconds),
                    updated_at = NOW()
                """)
                batch = []

        # 处理剩余批次
        if batch:
            values_list = []
            for b in batch:
                cid = b[0].replace("'", "''")
                cname = b[1].replace("'", "''")
                aname = b[2].replace("'", "''")
                theme = b[4].replace("'", "''")
                atime = f"'{b[3].strftime('%Y-%m-%d %H:%M:%S')}'" if b[3] else 'NULL'
                values_list.append(f"('{cid}', '{cname}', '{aname}', {atime}, '{theme}', {b[5]}, {b[6]}, {b[7]}, '[]', '[]', '{{}}')")
            
            db.execute(f"""
                INSERT INTO finvue_customer_profiles
                (customer_id, customer_name, latest_anchor_name, latest_analyzed_at,
                 latest_live_theme, latest_rank, best_rank, avg_watch_seconds, labels, tags, raw)
                VALUES {','.join(values_list)}
                ON DUPLICATE KEY UPDATE
                customer_name = VALUES(customer_name),
                latest_anchor_name = VALUES(latest_anchor_name),
                latest_analyzed_at = VALUES(latest_analyzed_at),
                latest_live_theme = VALUES(latest_live_theme),
                latest_rank = VALUES(latest_rank),
                best_rank = VALUES(best_rank),
                avg_watch_seconds = VALUES(avg_watch_seconds),
                updated_at = NOW()
            """)

        return {"ok": True, "message": f"成功导入 {count} 条客户档案", "count": count}

    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/api/customer-library/import-sessions")
async def import_customer_sessions(
    file: UploadFile = File(...),
    _: dict = Depends(security.require_permission("admin-api"))
) -> dict:
    """导入客户会话 CSV（批量插入优化）."""
    if not file.filename.endswith('.csv'):
        return {"ok": False, "error": "请上传 CSV 文件"}

    try:
        content = await file.read()
        text = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(text))

        count = 0
        batch = []
        batch_size = 500

        for row in reader:
            session_id = row.get('场次ID') or row.get('session_id')
            if not session_id:
                continue

            customer_id = row.get('客户ID') or row.get('customer_id') or ''
            anchor_name = row.get('主播名称') or row.get('anchor_name') or ''
            room_id = row.get('直播间ID') or row.get('room_id') or ''
            live_theme = row.get('直播主题') or row.get('live_theme') or ''
            report_type = row.get('报告类型') or row.get('report_type') or ''
            metric_type = row.get('指标类型') or row.get('metric_type') or ''
            metric_value = row.get('指标值') or row.get('metric_value') or ''
            watch_rank = int(row.get('观看排名') or row.get('watch_rank') or 0)
            watch_seconds = int(row.get('观看时长秒') or row.get('watch_duration_seconds') or 0)
            analyzed_at = row.get('分析时间') or row.get('analyzed_at')
            source_file = row.get('来源文件') or row.get('source_file') or ''

            # 解析时间
            analyzed_at_dt = None
            if analyzed_at:
                try:
                    analyzed_at_dt = datetime.strptime(analyzed_at, '%Y-%m-%d %H:%M:%S')
                except:
                    pass

            batch.append((session_id, customer_id, anchor_name, room_id, live_theme,
                         report_type, metric_type, metric_value, watch_rank,
                         watch_seconds, analyzed_at_dt, source_file))
            count += 1

            if len(batch) >= batch_size:
                # 批量插入
                values_list = []
                for b in batch:
                    sid = b[0].replace("'", "''")
                    cid = b[1].replace("'", "''")
                    aname = b[2].replace("'", "''")
                    rid = str(b[3]).replace("'", "''")
                    theme = b[4].replace("'", "''")
                    rtype = b[5].replace("'", "''")
                    mtype = b[6].replace("'", "''")
                    mval = b[7].replace("'", "''")
                    atime = f"'{b[10].strftime('%Y-%m-%d %H:%M:%S')}'" if b[10] else 'NULL'
                    src = b[11].replace("'", "''")
                    vals = f"('{sid}', '{cid}', '{aname}', '{rid}', '{theme}', '{rtype}', '{mtype}', '{mval}', {b[8]}, {b[9]}, {atime}, '{src}', '{{}}')"
                    values_list.append(vals)
                
                db.execute("""
                    INSERT INTO finvue_customer_sessions
                    (session_id, customer_id, anchor_name, room_id, live_theme,
                     report_type, metric_type, metric_value, watch_rank,
                     watch_duration_seconds, analyzed_at, source_file, raw)
                    VALUES %s
                    ON DUPLICATE KEY UPDATE
                    anchor_name = VALUES(anchor_name),
                    room_id = VALUES(room_id),
                    live_theme = VALUES(live_theme),
                    report_type = VALUES(report_type),
                    metric_type = VALUES(metric_type),
                    metric_value = VALUES(metric_value),
                    watch_rank = VALUES(watch_rank),
                    watch_duration_seconds = VALUES(watch_duration_seconds),
                    analyzed_at = VALUES(analyzed_at),
                    source_file = VALUES(source_file),
                    updated_at = NOW()
                """ % ','.join(values_list))
                batch = []

        # 处理剩余批次
        if batch:
            values_list = []
            for b in batch:
                sid = b[0].replace("'", "''")
                cid = b[1].replace("'", "''")
                aname = b[2].replace("'", "''")
                rid = str(b[3]).replace("'", "''")
                theme = b[4].replace("'", "''")
                rtype = b[5].replace("'", "''")
                mtype = b[6].replace("'", "''")
                mval = b[7].replace("'", "''")
                atime = f"'{b[10].strftime('%Y-%m-%d %H:%M:%S')}'" if b[10] else 'NULL'
                src = b[11].replace("'", "''")
                vals = f"('{sid}', '{cid}', '{aname}', '{rid}', '{theme}', '{rtype}', '{mtype}', '{mval}', {b[8]}, {b[9]}, {atime}, '{src}', '{{}}')"
                values_list.append(vals)
            
            db.execute("""
                INSERT INTO finvue_customer_sessions
                (session_id, customer_id, anchor_name, room_id, live_theme,
                 report_type, metric_type, metric_value, watch_rank,
                 watch_duration_seconds, analyzed_at, source_file, raw)
                VALUES %s
                ON DUPLICATE KEY UPDATE
                anchor_name = VALUES(anchor_name),
                room_id = VALUES(room_id),
                live_theme = VALUES(live_theme),
                report_type = VALUES(report_type),
                metric_type = VALUES(metric_type),
                metric_value = VALUES(metric_value),
                watch_rank = VALUES(watch_rank),
                watch_duration_seconds = VALUES(watch_duration_seconds),
                analyzed_at = VALUES(analyzed_at),
                source_file = VALUES(source_file),
                updated_at = NOW()
            """ % ','.join(values_list))

        return {"ok": True, "message": f"成功导入 {count} 条客户会话", "count": count}

    except Exception as e:
        return {"ok": False, "error": str(e)}
