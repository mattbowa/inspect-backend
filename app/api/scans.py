import uuid
from fastapi import APIRouter, HTTPException

from app.models.scan import ScanRequest, ScanResponse, ScanStatus
from app.workers.tasks import manual_run_scan, get_result
from app.database import get_active_subscription
from app.config import settings

router = APIRouter()


@router.post("", response_model=ScanResponse, status_code=202)
def create_scan(body: ScanRequest):
    scan_id = str(uuid.uuid4())

    if body.email and get_active_subscription(body.email, str(body.url)):
        max_pages = body.max_pages  # no cap for active subscribers
    else:
        max_pages = min(body.max_pages, settings.free_page_limit)

    notify_email = str(body.email) if body.email and body.notify else None
    manual_run_scan.delay(scan_id, str(body.url), max_pages, notify_email=notify_email)
    return ScanResponse(scan_id=scan_id, status=ScanStatus.pending, url=str(body.url))


@router.get("/{scan_id}/status")
def get_scan_status(scan_id: str):
    result = get_result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"scan_id": scan_id, "status": result["status"]}
