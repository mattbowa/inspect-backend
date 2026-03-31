import asyncio
import json
import structlog
import redis

from app.workers.celery_app import celery_app
from app.services.crawler import crawl_site
from app.services.embeddings import embed_batch
from app.agents import technical, content, linking, strategy
from app.database import save_scan
from app.config import settings

log = structlog.get_logger()

_redis = redis.from_url(settings.redis_url, decode_responses=True)
_RESULT_TTL = 3600  # 1 hour


def _set_result(scan_id: str, data: dict) -> None:
    _redis.setex(f"scan:{scan_id}", _RESULT_TTL, json.dumps(data))


@celery_app.task(bind=True, name="tasks.run_scan")
def run_scan(self, scan_id: str, url: str, max_pages: int = 20):
    log.info("scan.started", scan_id=scan_id, url=url)
    _set_result(scan_id, {"status": "crawling"})
    self.update_state(state="CRAWLING")

    try:
        # 1. Crawl
        pages = asyncio.run(crawl_site(url, max_pages))
        log.info("scan.crawled", scan_id=scan_id, pages=len(pages))

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
        )

        report_dict = full_report.model_dump()
        _set_result(scan_id, {"status": "done", "report": report_dict})
        save_scan(scan_id, url, "done", seo_score=full_report.seo_score, report=report_dict)
        log.info("scan.done", scan_id=scan_id, score=full_report.seo_score)

    except Exception as e:
        log.error("scan.failed", scan_id=scan_id, error=str(e))
        _set_result(scan_id, {"status": "failed", "error": str(e)})
        save_scan(scan_id, url, "failed")
        raise


def get_result(scan_id: str) -> dict | None:
    raw = _redis.get(f"scan:{scan_id}")
    return json.loads(raw) if raw else None
