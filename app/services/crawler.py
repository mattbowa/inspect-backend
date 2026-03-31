import asyncio
from urllib.parse import urljoin, urlparse
import structlog
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.models.scan import PageData

log = structlog.get_logger()


async def crawl_site(base_url: str, max_pages: int = 20) -> list[PageData]:
    visited: set[str] = set()
    queue: list[str] = [base_url]
    pages: list[PageData] = []
    base_domain = urlparse(base_url).netloc

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                log.info("crawling", url=url)
                await page.goto(url, timeout=30000, wait_until="networkidle")
                html = await page.content()
                page_data = _parse_page(url, html, base_domain)
                pages.append(page_data)

                for link in page_data.internal_links:
                    if link not in visited:
                        queue.append(link)

            except Exception as e:
                log.warning("crawl_error", url=url, error=str(e))

        await browser.close()

    return pages


def _parse_page(url: str, html: str, base_domain: str) -> PageData:
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title else None
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    meta_description = meta_desc_tag["content"].strip() if meta_desc_tag else None

    h1 = [t.get_text(strip=True) for t in soup.find_all("h1")]
    h2 = [t.get_text(strip=True) for t in soup.find_all("h2")]

    images_missing_alt = sum(
        1 for img in soup.find_all("img") if not img.get("alt", "").strip()
    )

    internal_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(url, href)
        if urlparse(full).netloc == base_domain and full not in internal_links:
            internal_links.append(full)

    body_text = soup.get_text(separator=" ", strip=True)
    word_count = len(body_text.split())

    return PageData(
        url=url,
        title=title,
        meta_description=meta_description,
        h1=h1,
        h2=h2,
        images_missing_alt=images_missing_alt,
        internal_links=internal_links[:50],
        word_count=word_count,
        content_text=body_text[:3000],
    )
