"""
Internal Linking Agent — uses cosine similarity to find:
  1. Internal link opportunities (similar pages that don't link to each other)
  2. Keyword cannibalization (near-duplicate pages competing for the same queries)
"""
import math
import structlog

from app.models.report import AgentReport, Issue
from app.models.scan import PageData

log = structlog.get_logger()

LINK_OPPORTUNITY_THRESHOLD = 0.82
CANNIBALIZATION_THRESHOLD = 0.95


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
    checked_pairs: set[frozenset] = set()

    for page in pages:
        embedding = embeddings.get(page.url)
        if not embedding:
            continue

        for candidate_url in urls:
            if candidate_url == page.url:
                continue

            pair = frozenset([page.url, candidate_url])

            score = _cosine_similarity(embedding, embeddings[candidate_url])

            # Keyword cannibalization — near-duplicate content competing for same queries
            if score >= CANNIBALIZATION_THRESHOLD and pair not in checked_pairs:
                checked_pairs.add(pair)
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="keyword_cannibalization",
                    description=(
                        f"This page has near-identical content to {candidate_url} "
                        f"(similarity: {score:.2f}). Both pages may be competing for the same search queries."
                    ),
                    suggestion=f"Consolidate these pages, set a canonical, or differentiate their content and target keywords.",
                ))
                continue

            # Internal link opportunity — similar but not yet linked
            if score >= LINK_OPPORTUNITY_THRESHOLD and candidate_url not in page.internal_links:
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

    link_opps = sum(1 for i in issues if i.type == "internal_link_opportunity")
    cannib = sum(1 for i in issues if i.type == "keyword_cannibalization")

    parts = []
    if link_opps:
        parts.append(f"{link_opps} internal linking {'opportunity' if link_opps == 1 else 'opportunities'}")
    if cannib:
        parts.append(f"{cannib} keyword cannibalization {'issue' if cannib == 1 else 'issues'}")

    summary = f"Found {' and '.join(parts)}." if parts else "No linking issues found."
    return AgentReport(agent="linking", issues=issues, summary=summary)
