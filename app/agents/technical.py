"""
Technical SEO Agent — rule-based checks across all crawled pages.
No LLM calls: fast and deterministic.
"""
from urllib.parse import urlparse

from app.models.report import AgentReport, Issue
from app.models.scan import PageData


def run(pages: list[PageData]) -> AgentReport:
    issues: list[Issue] = []

    title_seen: dict[str, str] = {}
    meta_seen: dict[str, str] = {}

    # Build inbound link map for orphan page detection
    all_urls = {page.url for page in pages}
    inbound: dict[str, set[str]] = {page.url: set() for page in pages}
    for page in pages:
        for link in page.internal_links:
            if link in inbound:
                inbound[link].add(page.url)

    start_url = pages[0].url if pages else None

    for page in pages:

        # ── Title ──────────────────────────────────────────────────────────────

        if not page.title:
            issues.append(Issue(
                page_url=page.url,
                severity="error",
                type="missing_title",
                description="Page has no <title> tag.",
                suggestion="Add a descriptive title tag (50–60 characters).",
            ))
        else:
            if page.title in title_seen:
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="duplicate_title",
                    description=f"Title '{page.title}' also used on {title_seen[page.title]}.",
                    suggestion="Each page should have a unique title.",
                ))
            else:
                title_seen[page.title] = page.url

            if len(page.title) > 60:
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="title_too_long",
                    description=f"Title is {len(page.title)} characters (max 60).",
                    suggestion="Shorten the title to 50–60 characters.",
                ))

        # ── Meta description ───────────────────────────────────────────────────

        if not page.meta_description:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="missing_meta_description",
                description="Page is missing a meta description.",
                suggestion="Add a meta description of 150–160 characters.",
            ))
        else:
            if page.meta_description in meta_seen:
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="duplicate_meta_description",
                    description=f"Meta description also used on {meta_seen[page.meta_description]}.",
                    suggestion="Write a unique meta description for each page.",
                ))
            else:
                meta_seen[page.meta_description] = page.url

        # ── H1 ────────────────────────────────────────────────────────────────

        if len(page.h1) > 1:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="multiple_h1",
                description=f"Page has {len(page.h1)} H1 tags.",
                suggestion="Use exactly one H1 per page.",
            ))

        if len(page.h1) == 0:
            issues.append(Issue(
                page_url=page.url,
                severity="error",
                type="missing_h1",
                description="Page has no H1 tag.",
                suggestion="Add a single H1 that reflects the page's primary topic.",
            ))

        # ── Images ────────────────────────────────────────────────────────────

        if page.images_missing_alt > 0:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="images_missing_alt",
                description=f"{page.images_missing_alt} image(s) missing alt text.",
                suggestion="Add descriptive alt attributes to all images.",
            ))

        # ── Broken internal links ─────────────────────────────────────────────

        if page.broken_internal_links:
            issues.append(Issue(
                page_url=page.url,
                severity="error",
                type="broken_internal_links",
                description=f"{len(page.broken_internal_links)} broken internal link(s): {', '.join(page.broken_internal_links[:3])}{'…' if len(page.broken_internal_links) > 3 else ''}",
                suggestion="Fix or remove links returning 4xx/5xx responses.",
            ))

        # ── Broken external links ─────────────────────────────────────────────

        if page.broken_external_links:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="broken_external_links",
                description=f"{len(page.broken_external_links)} broken external link(s): {', '.join(page.broken_external_links[:3])}{'…' if len(page.broken_external_links) > 3 else ''}",
                suggestion="Fix or remove outbound links returning 4xx/5xx responses.",
            ))

        # ── Thin content ──────────────────────────────────────────────────────

        if page.word_count < 300:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="thin_content",
                description=f"Page has only {page.word_count} words.",
                suggestion="Consider expanding content to at least 300 words.",
            ))

        # ── Canonical tag ─────────────────────────────────────────────────────

        if not page.canonical_url:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="missing_canonical",
                description="Page has no canonical tag.",
                suggestion="Add <link rel=\"canonical\" href=\"...\"> to avoid duplicate content issues.",
            ))
        else:
            canonical_domain = urlparse(page.canonical_url).netloc
            page_domain = urlparse(page.url).netloc
            if canonical_domain and canonical_domain != page_domain:
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="canonical_external_domain",
                    description=f"Canonical tag points to a different domain: {page.canonical_url}",
                    suggestion="Verify this is intentional — canonicalising to an external domain passes authority away from your site.",
                ))

        # ── Noindex ───────────────────────────────────────────────────────────

        if page.is_noindex:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="noindex_detected",
                description="Page has a noindex directive — search engines will not index this page.",
                suggestion="Remove noindex if this page should appear in search results.",
            ))

        # ── Open Graph tags ───────────────────────────────────────────────────

        if not page.has_og_tags:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="missing_og_tags",
                description="Page is missing Open Graph tags (og:title, og:description).",
                suggestion="Add Open Graph meta tags to control how this page appears when shared on social media.",
            ))

        # ── Structured data ───────────────────────────────────────────────────

        if not page.has_structured_data:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="missing_structured_data",
                description="Page has no JSON-LD structured data.",
                suggestion="Add Schema.org markup (e.g. Organization, Product, Article) to enable rich snippets in search results.",
            ))

        # ── Redirect chain ────────────────────────────────────────────────────

        if page.redirect_from:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="redirect_detected",
                description=f"Page is accessed via a redirect from {page.redirect_from}.",
                suggestion=f"Update internal links to point directly to {page.url} to avoid unnecessary redirect hops.",
            ))

        # ── Orphan pages ──────────────────────────────────────────────────────

        if page.url != start_url and not inbound.get(page.url):
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="orphan_page",
                description="No internal links point to this page — search engines may struggle to discover it.",
                suggestion="Add internal links from related pages to help crawlers find this page.",
            ))

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    summary = (
        f"Found {error_count} errors and {warning_count} warnings "
        f"across {len(pages)} pages."
    )

    return AgentReport(agent="technical", issues=issues, summary=summary)
