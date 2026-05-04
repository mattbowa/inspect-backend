import stripe
import structlog
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, EmailStr

from app.config import settings
from app.database import upsert_subscription, check_signup, Session, Subscription

log = structlog.get_logger()
router = APIRouter()

stripe.api_key = settings.stripe_secret_key

PRICE_IDS = {
    "business": settings.stripe_price_business,
    "enterprise": settings.stripe_price_enterprise,
}


class CheckoutRequest(BaseModel):
    email: EmailStr
    plan: str
    website: str | None = None


class CheckRequest(BaseModel):
    email: EmailStr
    website: str


@router.post("/check")
def check_before_signup(body: CheckRequest):
    result = check_signup(body.email, body.website)
    return {
        **result,
        "offer_free_unlimited": result["website_scanned"] and not result["website_subscribed"],
    }


class DomainCheckRequest(BaseModel):
    website: str


@router.post("/check-domain")
def check_domain(body: DomainCheckRequest):
    """Check if a domain has an active subscription — no email required.
    Used to decide whether to show the subscriber email prompt on the scan form."""
    from urllib.parse import urlparse
    from app.database import Session, Subscription, ScanRecord

    domain = urlparse(body.website).netloc.removeprefix("www.") or body.website.removeprefix("www.")
    with Session() as session:
        website_subscribed = (
            session.query(Subscription)
            .filter(Subscription.status == "active", Subscription.website.contains(domain))
            .first() is not None
        )
        website_scanned = (
            session.query(ScanRecord).filter(ScanRecord.url.contains(domain)).first()
            is not None
        )
    return {
        "website_subscribed": website_subscribed,
        "website_scanned": website_scanned,
    }


class PortalRequest(BaseModel):
    email: EmailStr


@router.post("/portal")
def customer_portal(body: PortalRequest):
    """Return a Stripe customer portal URL so subscribers can manage or cancel their plan."""
    with Session() as session:
        sub = session.query(Subscription).filter_by(email=body.email).first()
    if not sub or not sub.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No subscription found for this email")

    try:
        portal = stripe.billing_portal.Session.create(
            customer=sub.stripe_customer_id,
            return_url=f"{settings.frontend_url}/",
        )
        return {"url": portal.url}
    except stripe.StripeError as e:
        log.error("stripe.portal_error", error=str(e))
        raise HTTPException(status_code=502, detail="Failed to create portal session")


@router.post("/checkout")
def create_checkout(body: CheckoutRequest):
    if body.plan not in PRICE_IDS:
        raise HTTPException(status_code=400, detail="Invalid plan")

    log.info("checkout.request", email=body.email, plan=body.plan, website=body.website)  
    try:
        session = stripe.checkout.Session.create(
            mode="subscription",
            customer_email=body.email,
            line_items=[{"price": PRICE_IDS[body.plan], "quantity": 1}],
            success_url=f"{settings.frontend_url}/success?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{settings.frontend_url}/pricing",
            metadata={"plan": body.plan, "website": body.website or ""},
            subscription_data={
                "metadata": {"plan": body.plan, "website": body.website or ""}
            },
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        log.error("stripe.checkout_error", error=str(e))
        raise HTTPException(status_code=502, detail="Failed to create checkout session")


@router.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.stripe_webhook_secret)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    if event["type"] in ("customer.subscription.created", "customer.subscription.updated"):
        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email", "")
        plan = sub["metadata"].get("plan") or sub["items"]["data"][0]["price"]["metadata"].get("plan", "business")
        website = sub["metadata"].get("website") or ""
        upsert_subscription(
            email=email,
            plan=plan,
            status=sub["status"],
            stripe_customer_id=sub["customer"],
            stripe_subscription_id=sub["id"],
            website=website,
        )
        log.info("subscription.updated", email=email, plan=plan, status=sub["status"])

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        customer = stripe.Customer.retrieve(sub["customer"])
        email = customer.get("email", "")
        upsert_subscription(
            email=email,
            plan="",
            status="cancelled",
            stripe_customer_id=sub["customer"],
            stripe_subscription_id=sub["id"],
        )
        log.info("subscription.cancelled", email=email)

    return {"ok": True}
