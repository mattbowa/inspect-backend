from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Any

from app.database import get_scans, get_latest_scan, get_scan_diff, Session, Subscription, ScanRecord, ACTIVE_STATUSES

router = APIRouter()


class ScanSummary(BaseModel):
    scan_id: str
    url: str
    seo_score: Optional[int]
    status: str
    created_at: datetime
    report: Optional[Any] = None


@router.get("", response_model=list[ScanSummary])
def list_history(
    email: str = Query(..., description="Subscriber email"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
):
    with Session() as session:
        sub = session.query(Subscription).filter(
            Subscription.email == email,
            Subscription.status.in_(ACTIVE_STATUSES),
        ).first()

    if not sub:
        raise HTTPException(status_code=403, detail="Active subscription required")

    records = get_scans(email=email, domain=domain)
    return [
        ScanSummary(
            scan_id=r.scan_id,
            url=r.url,
            seo_score=r.seo_score,
            status=r.status,
            created_at=r.created_at,
            report=r.report,
        )
        for r in records
    ]


@router.get("/{scan_id}/diff")
def get_diff(scan_id: str, email: str = Query(...)):
    with Session() as session:
        sub = session.query(Subscription).filter(
            Subscription.email == email,
            Subscription.status.in_(ACTIVE_STATUSES),
        ).first()

    if not sub:
        raise HTTPException(status_code=403, detail="Active subscription required")

    with Session() as session:
        current = session.get(ScanRecord, scan_id)
    if not current:
        raise HTTPException(status_code=404, detail="Scan not found")

    previous = get_latest_scan(current.url, exclude_scan_id=scan_id)
    if not previous:
        return {"new_issues": [], "previous_scan_id": None}

    new_issues = get_scan_diff(scan_id, previous.scan_id)
    return {"new_issues": new_issues, "previous_scan_id": previous.scan_id}
