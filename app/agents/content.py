"""
Content Agent — uses Claude to suggest better titles, descriptions, and content improvements.
Only runs on pages that have issues flagged by the technical agent to keep costs down.
"""
import json
import structlog
import anthropic

from app.config import settings
from app.models.report import AgentReport, Issue
from app.models.scan import PageData

log = structlog.get_logger()

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


BATCH_SIZE = 5   # pages per Claude call
EXCERPT_LEN = 300  # chars of content per page


def run(pages: list[PageData], technical_issues: list[Issue]) -> AgentReport:
    flagged_urls = {i.page_url for i in technical_issues}
    flagged_pages = [p for p in pages if p.url in flagged_urls]

    issues: list[Issue] = []
    for i in range(0, len(flagged_pages), BATCH_SIZE):
        batch = flagged_pages[i:i + BATCH_SIZE]
        issues.extend(_analyse_batch(batch))

    summary = f"Generated content suggestions for {len(flagged_pages)} pages."
    return AgentReport(agent="content", issues=issues, summary=summary)


def _analyse_batch(pages: list[PageData]) -> list[Issue]:
    pages_text = "\n\n".join(
        f"PAGE {i+1}\nURL: {p.url}\nTitle: {p.title or '(none)'}\n"
        f"Meta: {p.meta_description or '(none)'}\nH1: {', '.join(p.h1) or '(none)'}\n"
        f"Words: {p.word_count}\nExcerpt: {p.content_text[:EXCERPT_LEN]}"
        for i, p in enumerate(pages)
    )

    prompt = f"""You are an SEO content expert. Audit each page against this checklist and return 1-2 of the most impactful issues found.

SEO CHECKLIST:
- Title: 50-60 characters, includes primary keyword, unique per page
- Meta description: 150-160 characters, includes a CTA, accurately reflects page content
- H1: exactly one per page, matches search intent, different from title
- Content: minimum 300 words, demonstrates E-E-A-T (Experience, Expertise, Authority, Trust)
- URL: short, keyword-rich, no unnecessary parameters or session IDs
- Schema markup: appropriate type used (Product, Article, LocalBusiness, FAQ, etc.)
- Keyword intent: page content matches what a user searching for this topic expects to find
- Internal linking: page links to related content where relevant

For each issue found, be specific — include the actual values (e.g. "title is 78 chars, reduce to 55") and a concrete rewrite suggestion where applicable. If the page passes all checklist items, flag any additional issues you notice.

PAGES:
{pages_text}

Return ONLY a JSON array of objects with keys: url, type, description, suggestion.
Example: [{{"url": "https://...", "type": "weak_title", "description": "...", "suggestion": "..."}}]"""

    try:
        response = _client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        items = json.loads(text)
        if isinstance(items, dict):
            items = items.get("suggestions", [])

        return [
            Issue(
                page_url=item.get("url", ""),
                severity="info",
                type=item.get("type", "content_suggestion"),
                description=item.get("description", ""),
                suggestion=item.get("suggestion", ""),
            )
            for item in items
            if item.get("url")
        ]
    except Exception as e:
        log.warning("content_agent.error", error=str(e))
        return []
