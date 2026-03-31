"""
Technical SEO Agent — detects missing tags, duplicate titles, thin content, etc.
No LLM calls here: pure rule-based so it's fast and deterministic.
"""
from app.models.report import AgentReport, Issue
from app.models.scan import PageData


def run(pages: list[PageData]) -> AgentReport:
    issues: list[Issue] = []

    title_seen: dict[str, str] = {}

    for page in pages:
        # Missing title
        if not page.title:
            issues.append(Issue(
                page_url=page.url,
                severity="error",
                type="missing_title",
                description="Page has no <title> tag.",
                suggestion="Add a descriptive title tag (50–60 characters).",
            ))
        else:
            # Duplicate title
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

            # Title too long
            if len(page.title) > 60:
                issues.append(Issue(
                    page_url=page.url,
                    severity="warning",
                    type="title_too_long",
                    description=f"Title is {len(page.title)} characters (max 60).",
                    suggestion="Shorten the title to 50–60 characters.",
                ))

        # Missing meta description
        if not page.meta_description:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="missing_meta_description",
                description="Page is missing a meta description.",
                suggestion="Add a meta description of 150–160 characters.",
            ))

        # Multiple H1s
        if len(page.h1) > 1:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="multiple_h1",
                description=f"Page has {len(page.h1)} H1 tags.",
                suggestion="Use exactly one H1 per page.",
            ))

        # Missing H1
        if len(page.h1) == 0:
            issues.append(Issue(
                page_url=page.url,
                severity="error",
                type="missing_h1",
                description="Page has no H1 tag.",
                suggestion="Add a single H1 that reflects the page's primary topic.",
            ))

        # Images missing alt text
        if page.images_missing_alt > 0:
            issues.append(Issue(
                page_url=page.url,
                severity="warning",
                type="images_missing_alt",
                description=f"{page.images_missing_alt} image(s) missing alt text.",
                suggestion="Add descriptive alt attributes to all images.",
            ))

        # Thin content
        if page.word_count < 300:
            issues.append(Issue(
                page_url=page.url,
                severity="info",
                type="thin_content",
                description=f"Page has only {page.word_count} words.",
                suggestion="Consider expanding content to at least 300 words.",
            ))

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")
    summary = (
        f"Found {error_count} errors and {warning_count} warnings "
        f"across {len(pages)} pages."
    )

    return AgentReport(agent="technical", issues=issues, summary=summary)
