from pydantic import BaseModel, HttpUrl
from enum import Enum
from typing import Optional


class ScanStatus(str, Enum):
    pending = "pending"
    crawling = "crawling"
    analysing = "analysing"
    done = "done"
    failed = "failed"


class ScanRequest(BaseModel):
    url: HttpUrl
    max_pages: int = 20


class ScanResponse(BaseModel):
    scan_id: str
    status: ScanStatus
    url: str


class PageData(BaseModel):
    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    h1: list[str] = []
    h2: list[str] = []
    images_missing_alt: int = 0
    internal_links: list[str] = []
    word_count: int = 0
    content_text: str = ""
