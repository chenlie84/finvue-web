"""FinVue MySQL-backed worker process."""
from __future__ import annotations

import os
import time
import traceback

import ai_router
import config
import migrate
import store
from services import fusion_report, live_room_sync, pdf_export


POLL_SECONDS = float(os.environ.get("WORKER_POLL_SECONDS", "2"))


def handle_job(job: dict) -> dict:
    job_type = job.get("type")
    payload = job.get("payload") or {}
    job_id = job.get("id")

    def progress(percent: int, phase: str, message: str, meta: dict | None = None) -> None:
        if not job_id:
            return
        store.update_job(job_id, progress=percent, result={"phase": phase, "message": message, "meta": meta or {}})

    if job_type in {"ai_generate", "batch_ai_analysis", "prompt_optimize"}:
        return ai_router.generate(payload)
    if job_type == "export_report_pdf":
        return {"ok": True, "phase": "done", "message": "PDF 导出完成", "meta": pdf_export.render_pdf_file(str(payload.get("html") or ""), str(payload.get("fileName") or payload.get("filename") or ""))}
    if job_type == "douyin_sync":
        return live_room_sync.run_sync(payload, progress=progress)
    if job_type == "parse_fusion_report":
        return fusion_report.parse_fusion_report(payload, progress=progress)
    if job_type in {"customer_backfill", "trend_summary"}:
        return {"ok": True, "phase": "done", "message": f"{job_type} 任务已完成：当前版本使用 MySQL 聚合接口实时生成结果。"}
    raise RuntimeError(f"未知任务类型：{job_type}")


def run_once() -> bool:
    job = store.claim_next_job()
    if not job:
        return False
    job_id = job["id"]
    try:
        store.update_job(job_id, progress=20)
        result = handle_job(job)
        store.update_job(job_id, status="completed", progress=100, result=result, error=None, finished_at=store._dt(time.strftime("%Y-%m-%d %H:%M:%S")))
        print(f"[worker] success {job_id} {job.get('type')}")
    except Exception as exc:
        store.update_job(job_id, status="failed", progress=100, error=f"{exc}\n{traceback.format_exc()}", finished_at=store._dt(time.strftime("%Y-%m-%d %H:%M:%S")))
        print(f"[worker] failed {job_id}: {exc}")
    return True


def main() -> None:
    if not config.has_mysql_config():
        raise RuntimeError("MySQL 未配置，worker 无法启动")
    migrate.run_migrations()
    print("[worker] FinVue worker started")
    while True:
        did_work = run_once()
        if not did_work:
            time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
