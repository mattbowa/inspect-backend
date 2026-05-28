"""
Strategy Agent — synthesises all agent reports into a prioritised action list using Claude.
"""
import json
import structlog
import anthropic

from app.config import settings
from app.models.report import AgentReport, FullReport

log = structlog.get_logger()

_client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def run(scan_id: str, url: str, agent_reports: list[AgentReport], pages_crawled: int = 0, pages_discovered: int = 0) -> FullReport:
    all_issues = [issue for r in agent_reports for issue in r.issues]

    error_count = sum(1 for i in all_issues if i.severity == "error")
    warning_count = sum(1 for i in all_issues if i.severity == "warning")
    score = max(0, 100 - (error_count * 10) - (warning_count * 3))

    top_actions = _generate_top_actions(url, agent_reports)

    return FullReport(
        scan_id=scan_id,
        url=url,
        seo_score=score,
        agents=agent_reports,
        top_actions=top_actions,
        pages_crawled=pages_crawled,
        pages_discovered=pages_discovered,
    )


def _generate_top_actions(url: str, reports: list[AgentReport]) -> list[str]:
    issue_count = sum(len(r.issues) for r in reports)

    if issue_count == 0:
        return ["No issues found — your site passed all checks. Keep monitoring for regressions as you publish new content."]

    issue_lines: list[str] = []
    for r in reports:
        for i in r.issues:
            line = f"[{i.severity.upper()}] {r.agent} — {i.type} on {i.page_url}: {i.description}"
            if i.suggestion:
                line += f" Fix: {i.suggestion}"
            issue_lines.append(line)

    issues_text = "\n".join(issue_lines)

    prompt = f"""You are an SEO strategist reviewing an audit of {url}.

Below are every issue found across all agents. Identify the top 5 most impactful actions the site owner should fix first.

Prioritise by real-world ranking impact:
1. Errors blocking indexation or crawling (robots.txt, noindex, broken links)
2. Missing or duplicate title/H1 tags on crawled pages
3. Missing meta descriptions affecting CTR
4. Schema and structured data gaps
5. Content and internal linking improvements

ISSUES FOUND:
{issues_text}

Rules:
- Base every action ONLY on the issues listed above — do not invent advice not supported by the data
- Reference the specific page URL and element (e.g. "Add an H1 to https://example.com/about")
- If fewer than 5 distinct actions are warranted by the issues, return fewer
- 1–2 sentences max per action

Return ONLY a JSON object with key "actions" containing an array of strings."""

    try:
        response = _client.messages.create(
            model=settings.claude_model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text.strip()

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]

        data = json.loads(text)
        return data.get("actions", [])
    except Exception as e:
        log.warning("strategy_agent.error", error=str(e))
        return ["Review and fix all errors flagged in the technical audit."]
