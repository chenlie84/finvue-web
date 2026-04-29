from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request

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
