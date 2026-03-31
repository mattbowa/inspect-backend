from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime
from typing import Optional

from app.database import get_scans

router = APIRouter()


class ScanSummary(BaseModel):
    scan_id: str
    url: str
    seo_score: Optional[int]
    status: str
    created_at: datetime


@router.get("", response_model=list[ScanSummary])
def list_history(domain: Optional[str] = Query(None, description="Filter by domain")):
    records = get_scans(domain=domain)
    return [
        ScanSummary(
            scan_id=r.scan_id,
            url=r.url,
            seo_score=r.seo_score,
            status=r.status,
            created_at=r.created_at,
        )
        for r in records
    ]
