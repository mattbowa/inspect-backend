from sqlalchemy import create_engine, Column, String, Integer, DateTime, JSON, Text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from datetime import datetime, timezone
from zoneinfo import ZoneInfo  # SYDNEY: uncomment to use Sydney time
_tz = ZoneInfo("Australia/Sydney")  # SYDNEY: replace timezone.utc with _tz in all default= lambdas below
import uuid

from app.config import settings

_db_url = settings.database_url.replace("postgres://", "postgresql://", 1)
engine = create_engine(_db_url)
Session = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class ScanRecord(Base):
    __tablename__ = "scans"

    scan_id = Column(String, primary_key=True)
    url = Column(String, nullable=False)
    email = Column(String, nullable=True, index=True)
    seo_score = Column(Integer)
    status = Column(String, nullable=False)
    report = Column(JSON)
    # created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime, default=lambda: datetime.now(_tz))


class PageSnapshot(Base):
    __tablename__ = "page_snapshots"

    id = Column(String, primary_key=True)
    scan_id = Column(String, nullable=False, index=True)
    page_url = Column(String, nullable=False)
    issue_types = Column(JSON, nullable=False)  # list[str]
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(String, primary_key=True)
    email = Column(String, nullable=False, index=True)
    plan = Column(String, nullable=False)          # "business" | "enterprise"
    status = Column(String, nullable=False)        # "active" | "cancelled" | "past_due"
    stripe_customer_id = Column(String)
    stripe_subscription_id = Column(Text)
    website = Column(String)
    cancellation_reason = Column(JSON)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


def upsert_subscription(email: str, plan: str, status: str, stripe_customer_id: str, stripe_subscription_id: str, website: str = None, cancellation_reason: dict = None):
    import uuid
    with Session() as session:
        record = session.query(Subscription).filter_by(email=email).first()
        if record:
            record.plan = plan
            record.status = status
            record.stripe_customer_id = stripe_customer_id
            record.stripe_subscription_id = stripe_subscription_id
            if website:
                record.website = website
            if cancellation_reason is not None:
                record.cancellation_reason = cancellation_reason
            record.updated_at = datetime.now(timezone.utc)
        else:
            record = Subscription(
                id=str(uuid.uuid4()),
                email=email,
                plan=plan,
                status=status,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                website=website,
                cancellation_reason=cancellation_reason,
            )
            session.add(record)
        session.commit()


def init_db():
    Base.metadata.create_all(engine)


def _summarise_report(report: dict) -> dict:
    """Strip per-page issue lists, keep top_actions and per-agent counts + summaries."""
    agents = []
    for agent in report.get("agents", []):
        issues = agent.get("issues", [])
        counts = {"error": 0, "warning": 0, "info": 0}
        for issue in issues:
            severity = issue.get("severity", "info")
            counts[severity] = counts.get(severity, 0) + 1
        agents.append({
            "agent": agent["agent"],
            "summary": agent["summary"],
            "issue_counts": counts,
        })
    return {
        "top_actions": report.get("top_actions", []),
        "agents": agents,
        "pages_crawled": report.get("pages_crawled", 0),
        "pages_discovered": report.get("pages_discovered", 0),
    }


def save_scan(scan_id: str, url: str, status: str, seo_score: int = None, report: dict = None, email: str = None):
    summary = _summarise_report(report) if report else None
    with Session() as session:
        record = session.get(ScanRecord, scan_id)
        if record:
            record.status = status
            record.seo_score = seo_score
            record.report = summary
            if email:
                record.email = email
        else:
            record = ScanRecord(
                scan_id=scan_id,
                url=url,
                email=email,
                status=status,
                seo_score=seo_score,
                report=summary,
            )
            session.add(record)
        session.commit()


def get_latest_scan(url: str, exclude_scan_id: str | None = None) -> ScanRecord | None:
    """Return the most recent completed scan for a URL, optionally excluding the current one."""
    from urllib.parse import urlparse
    domain = urlparse(url).netloc or url
    with Session() as session:
        q = (
            session.query(ScanRecord)
            .filter(ScanRecord.url.contains(domain), ScanRecord.status == "done")
            .order_by(ScanRecord.created_at.desc())
        )
        if exclude_scan_id:
            q = q.filter(ScanRecord.scan_id != exclude_scan_id)
        return q.first()


def get_scans(email: str = None, domain: str = None, limit: int = 50) -> list[ScanRecord]:
    with Session() as session:
        q = session.query(ScanRecord).order_by(ScanRecord.created_at.desc())
        if email:
            q = q.filter(ScanRecord.email == email)
        if domain:
            q = q.filter(ScanRecord.url.contains(domain))
        return q.limit(limit).all()


_TRACKED_ISSUE_TYPES = {"missing_title", "missing_meta_description", "missing_h1", "broken_internal_links"}


def save_page_snapshots(scan_id: str, issues: list) -> None:
    from collections import defaultdict
    page_issues: dict[str, list[str]] = defaultdict(list)
    for issue in issues:
        if issue.type in _TRACKED_ISSUE_TYPES:
            page_issues[issue.page_url].append(issue.type)
    with Session() as session:
        for page_url, issue_types in page_issues.items():
            session.add(PageSnapshot(
                id=str(uuid.uuid4()),
                scan_id=scan_id,
                page_url=page_url,
                issue_types=issue_types,
            ))
        session.commit()


def get_scan_diff(current_scan_id: str, previous_scan_id: str) -> list[dict]:
    """Return issues present in current scan that weren't in the previous scan."""
    with Session() as session:
        current = {
            s.page_url: set(s.issue_types)
            for s in session.query(PageSnapshot).filter_by(scan_id=current_scan_id).all()
        }
        previous = {
            s.page_url: set(s.issue_types)
            for s in session.query(PageSnapshot).filter_by(scan_id=previous_scan_id).all()
        }

    new_issues = []
    for page_url, issue_types in current.items():
        prev_issues = previous.get(page_url, set())
        for issue_type in issue_types - prev_issues:
            new_issues.append({"page_url": page_url, "type": issue_type})
    return new_issues


ACTIVE_STATUSES = {"active", "trialing", "past_due"}


def get_active_subscriptions() -> list[Subscription]:
    with Session() as session:
        return session.query(Subscription).filter(Subscription.status.in_(ACTIVE_STATUSES)).all()


def get_active_subscription(email: str, url: str) -> Subscription | None:
    """Return subscription only if email matches, domain matches, and status grants access."""
    from urllib.parse import urlparse

    scan_domain = urlparse(url).netloc.removeprefix("www.")
    with Session() as session:
        sub = (
            session.query(Subscription)
            .filter(Subscription.email == email, Subscription.status.in_(ACTIVE_STATUSES))
            .first()
        )
        if not sub or not sub.website:
            return None
        registered_domain = urlparse(sub.website).netloc.removeprefix("www.") or sub.website.removeprefix("www.")
        if scan_domain != registered_domain:
            return None
        return sub


def check_signup(email: str, website: str) -> dict:
    """Check if email or website already exist before sending to Stripe."""
    from urllib.parse import urlparse
    domain = urlparse(website).netloc or website

    with Session() as session:
        email_exists = session.query(Subscription).filter_by(email=email).first() is not None
        website_subscribed = (
            session.query(Subscription).filter(Subscription.website.contains(domain)).first()
            is not None
        )
        website_scanned = (
            session.query(ScanRecord).filter(ScanRecord.url.contains(domain)).first()
            is not None
        )
    return {
        "email_exists": email_exists,
        "website_subscribed": website_subscribed,
        "website_scanned": website_scanned,
    }
