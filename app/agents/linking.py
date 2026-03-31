"""
Internal Linking Agent — uses in-memory cosine similarity to suggest internal link opportunities.
Pages with similar content that don't already link to each other are good candidates.
"""
import math
import structlog

from app.models.report import AgentReport, Issue
from app.models.scan import PageData

log = structlog.get_logger()

SIMILARITY_THRESHOLD = 0.82


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def run(pages: list[PageData], scan_id: str, embeddings: dict[str, list[float]]) -> AgentReport:
    issues: list[Issue] = []
    urls = list(embeddings.keys())

    for page in pages:
        embedding = embeddings.get(page.url)
        if not embedding:
            continue

        for candidate_url in urls:
            if candidate_url == page.url:
                continue
            if candidate_url in page.internal_links:
                continue

            score = _cosine_similarity(embedding, embeddings[candidate_url])
            if score < SIMILARITY_THRESHOLD:
                continue

            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="internal_link_opportunity",
                description=(
                    f"This page is topically similar to {candidate_url} "
                    f"(similarity: {score:.2f}) but doesn't link to it."
                ),
                suggestion=f"Consider adding an internal link to {candidate_url}.",
            ))

    summary = f"Found {len(issues)} internal linking opportunities."
    return AgentReport(agent="linking", issues=issues, summary=summary)
