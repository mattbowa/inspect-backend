import asyncio
import json
import uuid
import structlog
import redis
from datetime import datetime, timezone

from app.workers.celery_app import celery_app
from app.services.crawler import crawl_site
from app.services.embeddings import embed_batch
from app.services.email import send_scan_report
from app.agents import technical, content, linking, strategy
from app.database import save_scan, get_active_subscriptions, get_latest_scan, save_page_snapshots, get_scan_diff
from app.config import settings

log = structlog.get_logger()

_redis = redis.from_url(settings.redis_url, decode_responses=True)
_RESULT_TTL = 3600  # 1 hour


def _set_result(scan_id: str, data: dict) -> None:
    _redis.setex(f"scan:{scan_id}", _RESULT_TTL, json.dumps(data))


@celery_app.task(bind=True, name="tasks.manual_run_scan")
def manual_run_scan(self, scan_id: str, url: str, max_pages: int = 20, notify_email: str | None = None):
    log.info("scan.started", scan_id=scan_id, url=url)
    _set_result(scan_id, {"status": "crawling"})
    self.update_state(state="CRAWLING")

    try:
        # 1. Crawl
        pages, pages_discovered = asyncio.run(crawl_site(url, max_pages))
        log.info("scan.crawled", scan_id=scan_id, pages=len(pages), discovered=pages_discovered)

        _set_result(scan_id, {"status": "analysing"})
        self.update_state(state="ANALYSING")

        # 2. Embed pages for linking agent
        texts = [p.content_text for p in pages]
        embeddings_list = embed_batch(texts)
        embeddings_map: dict[str, list[float]] = {
            page.url: embedding
            for page, embedding in zip(pages, embeddings_list)
        }

        # 3. Agent pipeline — each agent builds on the previous
        tech_report = technical.run(pages)
        content_report = content.run(pages, tech_report.issues)
        linking_report = linking.run(pages, scan_id, embeddings_map)
        full_report = strategy.run(
            scan_id=scan_id,
            url=url,
            agent_reports=[tech_report, content_report, linking_report],
            pages_crawled=len(pages),
            pages_discovered=pages_discovered,
        )

        report_dict = full_report.model_dump()
        _set_result(scan_id, {"status": "done", "report": report_dict})
        save_scan(scan_id, url, "done", seo_score=full_report.seo_score, report=report_dict)
        log.info("scan.done", scan_id=scan_id, score=full_report.seo_score)

        if notify_email:
            previous = get_latest_scan(url, exclude_scan_id=scan_id)
            send_scan_report(
                to=notify_email,
                url=url,
                scan_id=scan_id,
                seo_score=full_report.seo_score,
                top_actions=full_report.top_actions,
                previous_score=previous.seo_score if previous else None,
                subject_prefix="Your SEO report",
            )

    except Exception as e:
        log.error("scan.failed", scan_id=scan_id, error=str(e))
        _set_result(scan_id, {"status": "failed", "error": str(e)})
        save_scan(scan_id, url, "failed")
        raise


def get_result(scan_id: str) -> dict | None:
    raw = _redis.get(f"scan:{scan_id}")
    return json.loads(raw) if raw else None


@celery_app.task(bind=True, name="tasks.run_monitoring_scan")
def run_monitoring_scan(self, scan_id: str, url: str, notify_email: str | None = None):
    """Lightweight scheduled scan — crawl + technical agent only, no LLM calls.
    Saves a page snapshot and emails the subscriber only if new issues are detected."""
    log.info("monitoring_scan.started", scan_id=scan_id, url=url)

    try:
        pages, _ = asyncio.run(crawl_site(url, max_pages=200))
        tech_report = technical.run(pages)

        errors = sum(1 for i in tech_report.issues if i.severity == "error")
        warnings = sum(1 for i in tech_report.issues if i.severity == "warning")
        score = max(0, 100 - (errors * 10) - (warnings * 3))

        save_scan(scan_id, url, "done", seo_score=score)
        save_page_snapshots(scan_id, tech_report.issues)
        log.info("monitoring_scan.done", scan_id=scan_id, score=score)

        if notify_email:
            previous = get_latest_scan(url, exclude_scan_id=scan_id)
            new_errors = get_scan_diff(scan_id, previous.scan_id) if previous else []
            if new_errors:
                send_scan_report(
                    to=notify_email,
                    url=url,
                    scan_id=scan_id,
                    seo_score=score,
                    top_actions=[],
                    previous_score=previous.seo_score if previous else None,
                    new_errors=new_errors,
                    subject_prefix="SEO issue detected",
                )

    except Exception as e:
        log.error("monitoring_scan.failed", scan_id=scan_id, error=str(e))
        save_scan(scan_id, url, "failed")
        raise


@celery_app.task(name="tasks.run_scheduled_scans")
def run_scheduled_scans():
    """Triggered daily by Celery Beat.
    Enterprise subscribers are scanned every day.
    Business subscribers are scanned once per week (if 7+ days since last scan)."""
    from datetime import timedelta
    subscriptions = get_active_subscriptions()
    queued = 0
    for sub in subscriptions:
        if not sub.website:
            continue

        if sub.plan == "business":
            previous = get_latest_scan(sub.website)
            if previous and (datetime.now(timezone.utc) - previous.created_at.replace(tzinfo=timezone.utc)) < timedelta(days=7):
                continue

        scan_id = str(uuid.uuid4())
        run_monitoring_scan.delay(scan_id, sub.website, notify_email=sub.email)
        queued += 1
        log.info("scheduled_scan.queued", scan_id=scan_id, website=sub.website, plan=sub.plan)
    log.info("scheduled_scan.complete", queued=queued)
