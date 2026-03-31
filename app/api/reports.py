from fastapi import APIRouter, HTTPException

from app.models.report import FullReport
from app.workers.tasks import get_result

router = APIRouter()


@router.get("/{scan_id}", response_model=FullReport)
def get_report(scan_id: str):
    result = get_result(scan_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Scan not found")
    if result["status"] != "done":
        raise HTTPException(status_code=202, detail=f"Scan status: {result['status']}")
    return result["report"]
