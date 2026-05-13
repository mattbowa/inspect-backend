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
    summaries = "\n".join(f"- {r.agent}: {r.summary}" for r in reports)
    issue_count = sum(len(r.issues) for r in reports)

    prompt = f"""You are an SEO strategist. Based on these audit findings for {url}, identify the top 5 most impactful actions the site owner should take first.

Prioritise actions in this order:
1. Critical technical errors (missing H1, broken structure) — these block rankings
2. High-traffic pages with missing or weak titles/meta descriptions — directly affects CTR
3. Schema markup gaps — quick wins for rich snippets
4. Content quality issues on key pages — E-E-A-T signals
5. Internal linking opportunities — distributes authority across the site

Agent summaries:
{summaries}

Total issues found: {issue_count}

Return ONLY a JSON object with key "actions" containing an array of 5 strings.
Each action must be specific to this site — no generic advice. Include the page URL or element affected where relevant. 1-2 sentences max per action."""

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
