"""
Email reports via Resend. Two entry points:
  - send_scan_report()  — called after a manual scan when the user opts in
  - send_scheduled_report() — called after every weekly automated scan

Scheduled reports include a score delta vs the previous scan so subscribers
can see at a glance whether things improved or regressed since last week.
"""
import resend
import structlog

from app.config import settings

log = structlog.get_logger()


def _score_delta_text(current: int, previous: int | None) -> str:
    if previous is None:
        return ""
    delta = current - previous
    if delta > 0:
        return f" <span style='color:#22c55e'>▲{delta}</span>"
    if delta < 0:
        return f" <span style='color:#ef4444'>▼{abs(delta)}</span>"
    return " <span style='color:#94a3b8'>no change</span>"


def _build_html(
    url: str,
    scan_id: str,
    seo_score: int,
    top_actions: list[str],
    new_errors: list[dict],
    previous_score: int | None,
    frontend_url: str,
) -> str:
    delta_html = _score_delta_text(seo_score, previous_score)

    actions_html = "".join(
        f"<li style='margin-bottom:8px;color:#cbd5e1;font-size:14px;'>{a}</li>"
        for a in top_actions[:3]
    )

    new_errors_section = ""
    if new_errors:
        error_rows = "".join(
            f"<li style='margin-bottom:6px;color:#fca5a5;font-size:13px;'>"
            f"<strong>{e['type'].replace('_', ' ').title()}</strong> — {e['page_url']}</li>"
            for e in new_errors[:5]
        )
        new_errors_section = f"""
        <div style='margin-top:24px;'>
          <p style='font-size:13px;font-weight:600;color:#f87171;margin:0 0 8px;'>
            New issues since last scan
          </p>
          <ul style='padding-left:20px;margin:0;'>{error_rows}</ul>
        </div>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <body style='margin:0;padding:0;background:#0f172a;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;'>
      <div style='max-width:560px;margin:40px auto;padding:32px;background:#1e293b;border-radius:16px;border:1px solid #334155;'>

        <p style='font-size:12px;color:#64748b;margin:0 0 24px;'>AI-powered SEO auditing</p>

        <h1 style='font-size:20px;font-weight:700;color:#f1f5f9;margin:0 0 4px;'>
          Weekly SEO Report
        </h1>
        <p style='font-size:13px;color:#64748b;font-family:monospace;margin:0 0 28px;word-break:break-all;'>
          {url}
        </p>

        <div style='display:flex;align-items:baseline;gap:8px;margin-bottom:28px;'>
          <span style='font-size:48px;font-weight:700;color:#6366f1;line-height:1;'>{seo_score}</span>
          <span style='font-size:16px;color:#94a3b8;'>/100{delta_html}</span>
        </div>

        <div style='margin-bottom:24px;'>
          <p style='font-size:13px;font-weight:600;color:#94a3b8;margin:0 0 10px;text-transform:uppercase;letter-spacing:.05em;'>
            Top actions
          </p>
          <ol style='padding-left:20px;margin:0;'>{actions_html}</ol>
        </div>

        {new_errors_section}

        <div style='margin-top:32px;padding-top:24px;border-top:1px solid #334155;'>
          <a href='{frontend_url}/?scan_id={scan_id}'
             style='display:inline-block;background:#6366f1;color:#fff;font-weight:600;
                    font-size:14px;padding:12px 24px;border-radius:10px;text-decoration:none;'>
            View full report
          </a>
        </div>

        <p style='font-size:11px;color:#475569;margin:24px 0 0;'>
          You're receiving this because you have an active InspectFlux subscription.
        </p>
      </div>
    </body>
    </html>
    """


ADMIN_EMAIL = "audits@inspectflux.com"


def send_admin_notification(subject: str, body: str) -> None:
    if not settings.resend_api_key:
        return
    resend.api_key = settings.resend_api_key
    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": ADMIN_EMAIL,
            "subject": subject,
            "html": f"<pre style='font-family:monospace;font-size:14px;'>{body}</pre>",
        })
    except Exception as e:
        log.error("admin_email.failed", error=str(e))


def send_scan_report(
    to: str,
    url: str,
    scan_id: str,
    seo_score: int,
    top_actions: list[str],
    previous_score: int | None = None,
    new_errors: list[dict] | None = None,
    subject_prefix: str = "Your SEO report",
) -> None:
    if not settings.resend_api_key:
        log.warning("email.skipped", reason="RESEND_API_KEY not set")
        return

    resend.api_key = settings.resend_api_key

    html = _build_html(
        url=url,
        scan_id=scan_id,
        seo_score=seo_score,
        top_actions=top_actions,
        new_errors=new_errors or [],
        previous_score=previous_score,
        frontend_url=settings.frontend_url,
    )

    try:
        resend.Emails.send({
            "from": settings.email_from,
            "to": to,
            "subject": f"{subject_prefix}: {url} scored {seo_score}/100",
            "html": html,
        })
        log.info("email.sent", to=to, scan_id=scan_id, score=seo_score)
    except Exception as e:
        # Never let email failure break the scan result
        log.error("email.failed", to=to, scan_id=scan_id, error=str(e))
