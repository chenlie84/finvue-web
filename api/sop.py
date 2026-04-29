from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

import db
import security


router = APIRouter()


class AnchorUpsertRequest(BaseModel):
    operatorName: str = Field(..., min_length=1)
    note: Optional[str] = None
    currentBlocker: Optional[str] = None


class ProgressUpsertRequest(BaseModel):
    week: int = Field(..., ge=1, le=4)
    actionIndex: int = Field(..., ge=0)
    subIndex: int = Field(-1, ge=-1)
    childIndex: int = Field(-1, ge=-1)
    checked: Optional[bool] = None
    note: Optional[str] = None


class CustomOptionCreateRequest(BaseModel):
    week: int = Field(..., ge=1, le=4)
    actionIndex: int = Field(..., ge=0)
    subIndex: int = Field(..., ge=0)
    label: str = Field(..., min_length=1, max_length=64)


def _iso(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _anchor_to_response(row: dict) -> dict:
    start_date = row.get("start_date")
    days = (date.today() - start_date).days + 1 if start_date else 0
    return {
        "anchorName": row.get("anchor_name"),
        "operatorName": row.get("operator_name"),
        "startDate": _iso(row.get("start_date")),
        "lastSavedDate": _iso(row.get("last_saved_date")),
        "currentWeek": row.get("current_week"),
        "status": row.get("status"),
        "note": row.get("note"),
        "currentBlocker": row.get("current_blocker"),
        "warning": days > 28,
    }


def _progress_to_response(row: dict) -> dict:
    return {
        "week": row.get("week"),
        "actionIndex": row.get("action_index"),
        "subIndex": row.get("sub_index"),
        "childIndex": row.get("child_index"),
        "checked": bool(row.get("checked")),
        "note": row.get("note") or "",
    }


def _custom_option_to_response(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "week": row.get("week"),
        "actionIndex": row.get("action_index"),
        "subIndex": row.get("sub_index"),
        "label": row.get("label"),
        "sortOrder": row.get("sort_order"),
    }


def _get_anchor_row(anchor_name: str) -> dict | None:
    return db.fetch_one("SELECT * FROM sop_anchors WHERE anchor_name = %s", (anchor_name,))


def _list_progress(anchor_name: str) -> list[dict]:
    return db.fetch_all(
        """
        SELECT week, action_index, sub_index, child_index, checked, note, updated_at
        FROM sop_action_progress
        WHERE anchor_name = %s
        ORDER BY week, action_index, sub_index, child_index
        """,
        (anchor_name,),
    )


def _list_week_completions(anchor_name: str) -> dict[str, str]:
    rows = db.fetch_all(
        "SELECT week, completed_at FROM sop_week_completion WHERE anchor_name = %s",
        (anchor_name,),
    )
    return {str(row["week"]): _iso(row["completed_at"]) for row in rows}


def _build_full_anchor(row: dict) -> dict:
    anchor_name = row["anchor_name"]
    payload = _anchor_to_response(row)
    payload["progress"] = [_progress_to_response(item) for item in _list_progress(anchor_name)]
    payload["weekCompletions"] = _list_week_completions(anchor_name)
    return payload


@router.get("/api/sop/anchors")
def list_anchors(_: dict = Depends(security.require_permission("sop"))) -> dict:
    rows = db.fetch_all("SELECT * FROM sop_anchors ORDER BY created_at DESC")
    return {"anchors": [_build_full_anchor(row) for row in rows]}


@router.get("/api/sop/options")
def list_options(_: dict = Depends(security.require_permission("sop"))) -> dict:
    rows = db.fetch_all(
        """
        SELECT id, week, action_index, sub_index, label, sort_order, created_at
        FROM sop_custom_options
        ORDER BY week, action_index, sub_index, sort_order, id
        """
    )
    return {"options": [_custom_option_to_response(row) for row in rows]}


@router.post("/api/sop/options", status_code=201)
def add_option(payload: CustomOptionCreateRequest, _: dict = Depends(security.require_permission("sop"))) -> dict:
    label = payload.label.strip()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT id, week, action_index, sub_index, label, sort_order, created_at
            FROM sop_custom_options
            WHERE week = %s AND action_index = %s AND sub_index = %s AND label = %s
            """,
            (payload.week, payload.actionIndex, payload.subIndex, label),
        )
        existing = cur.fetchone()
        if existing:
            return _custom_option_to_response(existing)
        cur.execute(
            """
            SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort
            FROM sop_custom_options
            WHERE week = %s AND action_index = %s AND sub_index = %s
            """,
            (payload.week, payload.actionIndex, payload.subIndex),
        )
        next_sort = cur.fetchone()["next_sort"]
        cur.execute(
            """
            INSERT INTO sop_custom_options (week, action_index, sub_index, label, sort_order)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (payload.week, payload.actionIndex, payload.subIndex, label, next_sort),
        )
        cur.execute(
            """
            SELECT id, week, action_index, sub_index, label, sort_order, created_at
            FROM sop_custom_options
            WHERE id = LAST_INSERT_ID()
            """
        )
        return _custom_option_to_response(cur.fetchone())


@router.get("/api/sop/anchors/{anchor_name}")
def get_anchor(anchor_name: str, _: dict = Depends(security.require_permission("sop"))) -> dict:
    row = _get_anchor_row(anchor_name)
    if not row:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    return _build_full_anchor(row)


@router.put("/api/sop/anchors/{anchor_name}")
def upsert_anchor(anchor_name: str, payload: AnchorUpsertRequest, _: dict = Depends(security.require_permission("sop"))) -> dict:
    db.execute(
        """
        INSERT INTO sop_anchors (anchor_name, operator_name, start_date, last_saved_date, note, current_blocker)
        VALUES (%s, %s, CURDATE(), CURDATE(), %s, %s)
        ON DUPLICATE KEY UPDATE
          operator_name = VALUES(operator_name),
          last_saved_date = CURDATE(),
          note = COALESCE(VALUES(note), note),
          current_blocker = COALESCE(VALUES(current_blocker), current_blocker)
        """,
        (anchor_name, payload.operatorName, payload.note, payload.currentBlocker),
    )
    return _build_full_anchor(_get_anchor_row(anchor_name))


@router.delete("/api/sop/anchors/{anchor_name}", status_code=204)
def delete_anchor(anchor_name: str, _: dict = Depends(security.require_permission("sop"))) -> Response:
    if not _get_anchor_row(anchor_name):
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    db.execute("DELETE FROM sop_anchors WHERE anchor_name = %s", (anchor_name,))
    return Response(status_code=204)


@router.put("/api/sop/anchors/{anchor_name}/progress", status_code=204)
def upsert_progress(anchor_name: str, payload: ProgressUpsertRequest, _: dict = Depends(security.require_permission("sop"))) -> Response:
    if not _get_anchor_row(anchor_name):
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    checked_int = None if payload.checked is None else (1 if payload.checked else 0)
    checked_insert = 0 if checked_int is None else checked_int
    db.execute(
        """
        INSERT INTO sop_action_progress
          (anchor_name, week, action_index, sub_index, child_index, checked, note)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
          checked = IF(%s IS NULL, checked, VALUES(checked)),
          note = COALESCE(VALUES(note), note)
        """,
        (
            anchor_name,
            payload.week,
            payload.actionIndex,
            payload.subIndex,
            payload.childIndex,
            checked_insert,
            payload.note,
            checked_int,
        ),
    )
    return Response(status_code=204)


@router.post("/api/sop/anchors/{anchor_name}/advance")
def advance_week(anchor_name: str, _: dict = Depends(security.require_permission("sop"))) -> dict:
    row = _get_anchor_row(anchor_name)
    if not row:
        raise HTTPException(status_code=404, detail=f"anchor not found: {anchor_name}")
    current_week = int(row.get("current_week") or 1)
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sop_week_completion (anchor_name, week, completed_at)
            VALUES (%s, %s, CURDATE())
            ON DUPLICATE KEY UPDATE completed_at = VALUES(completed_at)
            """,
            (anchor_name, current_week),
        )
        if current_week >= 4:
            cur.execute(
                "UPDATE sop_anchors SET current_week = LEAST(current_week + 1, 4), status = '已完成' WHERE anchor_name = %s",
                (anchor_name,),
            )
        else:
            cur.execute(
                "UPDATE sop_anchors SET current_week = LEAST(current_week + 1, 4) WHERE anchor_name = %s",
                (anchor_name,),
            )
    return _build_full_anchor(_get_anchor_row(anchor_name))
