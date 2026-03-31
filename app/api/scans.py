import uuid
from fastapi import APIRouter, HTTPException

from app.models.scan import ScanRequest, ScanResponse, ScanStatus
from app.workers.tasks import run_scan, get_result

router = APIRouter()


@router.post("", response_model=ScanResponse, status_code=202)
def create_scan(body: ScanRequest):
    scan_id = str(uuid.uuid4())
    run_scan.delay(scan_id, str(body.url), body.max_pages)
    return ScanResponse(scan_id=scan_id, status=ScanStatus.pending, url=str(body.url))


@router.get("/{scan_id}/status")
def get_scan_status(scan_id: str):
    result = get_result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"scan_id": scan_id, "status": result["status"]}
