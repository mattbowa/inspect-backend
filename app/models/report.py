from pydantic import BaseModel
from typing import Optional


class Issue(BaseModel):
    page_url: str
    severity: str  # "error" | "warning" | "info"
    type: str
    description: str
    suggestion: Optional[str] = None


class AgentReport(BaseModel):
    agent: str
    issues: list[Issue]
    summary: str


class FullReport(BaseModel):
    scan_id: str
    url: str
    seo_score: int
    agents: list[AgentReport]
    top_actions: list[str]
