import resend
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.config import settings

log = structlog.get_logger()
router = APIRouter()


class ContactRequest(BaseModel):
    name: str
    email: EmailStr
    reason: str = "General enquiry"
    message: str


@router.post("")
def send_contact(body: ContactRequest):
    if not settings.resend_api_key:
        raise HTTPException(status_code=503, detail="Email service not configured")

    resend.api_key = settings.resend_api_key

    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": "audits@inspectflux.com",
            "reply_to": body.email,
            "subject": f"[{body.reason}] {body.name}",
            "html": f"""
            <p><strong>From:</strong> {body.name} &lt;{body.email}&gt;</p>
            <p><strong>Reason:</strong> {body.reason}</p>
            <p><strong>Message:</strong></p>
            <p style="white-space:pre-wrap">{body.message}</p>
            """,
        })
        log.info("contact.sent", email=body.email)
        return {"ok": True}
    except Exception as e:
        log.error("contact.failed", error=str(e))
        raise HTTPException(status_code=502, detail="Failed to send message")
