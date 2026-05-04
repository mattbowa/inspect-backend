import asyncio
import httpx
from urllib.parse import urljoin, urlparse
import structlog
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

from app.models.scan import PageData

log = structlog.get_logger()

_SKIP_EXTERNAL_DOMAINS = {"twitter.com", "x.com", "facebook.com", "instagram.com", "linkedin.com", "t.co", "youtube.com"}
_MAX_EXTERNAL_LINKS_CHECKED = 3  # per page, to limit crawl time


async def _count_sitemap_pages(base_url: str, base_domain: str) -> int | None:
    """Return total page count from sitemap, or None if unavailable."""
    parsed = urlparse(base_url)
    root = f"{parsed.scheme}://{parsed.netloc}"

    sitemap_url = f"{root}/sitemap.xml"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            robots = await client.get(f"{root}/robots.txt")
            if robots.status_code == 200:
                for line in robots.text.splitlines():
                    if line.lower().startswith("sitemap:"):
                        sitemap_url = line.split(":", 1)[1].strip()
                        break

            resp = await client.get(sitemap_url)
            if resp.status_code != 200:
                return None

            soup = BeautifulSoup(resp.text, "html.parser")

            if soup.find("sitemapindex"):
                total = 0
                for loc in soup.find_all("sitemap"):
                    child_url = loc.find("loc")
                    if not child_url:
                        continue
                    child_resp = await client.get(child_url.text.strip())
                    if child_resp.status_code == 200:
                        child_soup = BeautifulSoup(child_resp.text, "html.parser")
                        total += len(child_soup.find_all("url"))
                return total or None

            count = sum(
                1 for u in soup.find_all("url")
                if (loc := u.find("loc")) and urlparse(loc.text).netloc == base_domain
            )
            return count or None

    except Exception as e:
        log.warning("sitemap.error", error=str(e))
        return None


_REPETITIVE_PREFIXES = {
    "/products", "/collections", "/blog", "/articles", "/news",
    "/events", "/category", "/tag", "/tags", "/shop", "/brands",
    "/vendor", "/vendors", "/types", "/search", "/departments",
}
_PREFIX_CAP = 3


def _url_prefix(url: str) -> str | None:
    path = urlparse(url).path
    first_segment = "/" + path.strip("/").split("/")[0] if path.strip("/") else "/"
    return first_segment if first_segment in _REPETITIVE_PREFIXES else None


async def _check_broken_internal_links(links: list[str]) -> list[str]:
    broken = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
        async def check(url: str) -> None:
            try:
                resp = await client.head(url)
                if resp.status_code in (405, 501):
                    resp = await client.get(url)
                if resp.status_code >= 400:
                    broken.append(url)
            except Exception:
                broken.append(url)

        await asyncio.gather(*[check(url) for url in links])
    return broken


async def _check_broken_external_links(links: list[str]) -> list[str]:
    broken = []
    async with httpx.AsyncClient(follow_redirects=True, timeout=5) as client:
        async def check(url: str) -> None:
            domain = urlparse(url).netloc.removeprefix("www.")
            if any(skip in domain for skip in _SKIP_EXTERNAL_DOMAINS):
                return
            try:
                resp = await client.head(url)
                if resp.status_code in (405, 501):
                    resp = await client.get(url)
                if resp.status_code >= 400:
                    broken.append(url)
            except Exception:
                pass  # external network errors are too noisy to flag as broken

        await asyncio.gather(*[check(url) for url in links])
    return broken


async def crawl_site(base_url: str, max_pages: int = 20) -> tuple[list[PageData], int]:
    visited: set[str] = set()
    queue: list[str] = [base_url]
    pages: list[PageData] = []
    prefix_counts: dict[str, int] = {}
    base_domain = urlparse(base_url).netloc

    sitemap_count = await _count_sitemap_pages(base_url, base_domain)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        while queue and len(pages) < max_pages:
            url = queue.pop(0)
            if url in visited:
                continue

            prefix = _url_prefix(url)
            if prefix and prefix_counts.get(prefix, 0) >= _PREFIX_CAP:
                log.debug("crawl.prefix_cap_reached", prefix=prefix, url=url)
                continue

            visited.add(url)

            try:
                log.info("crawling", url=url)
                await page.goto(url, timeout=30000, wait_until="networkidle")
                final_url = page.url
                html = await page.content()

                page_data = _parse_page(final_url, html, base_domain)

                # Detect redirect: requested URL differs from final URL
                if final_url.rstrip("/") != url.rstrip("/"):
                    page_data.redirect_from = url

                page_data.broken_internal_links = await _check_broken_internal_links(page_data.internal_links)
                page_data.broken_external_links = await _check_broken_external_links(
                    page_data.external_links[:_MAX_EXTERNAL_LINKS_CHECKED]
                )
                pages.append(page_data)

                if prefix:
                    prefix_counts[prefix] = prefix_counts.get(prefix, 0) + 1

                for link in page_data.internal_links:
                    if link not in visited:
                        queue.append(link)

            except Exception as e:
                log.error("crawl_error", url=url, error=str(e), exc_info=True)

        await browser.close()

    pages_discovered = sitemap_count or (len(visited) + len(set(queue) - visited))
    return pages, pages_discovered


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

    # Canonical tag
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    canonical_url = canonical_tag.get("href", "").strip() if canonical_tag else None

    # Noindex (meta robots)
    robots_meta = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "robots"})
    is_noindex = False
    if robots_meta and robots_meta.get("content"):
        is_noindex = "noindex" in robots_meta["content"].lower()

    # Open Graph tags
    has_og_tags = bool(
        soup.find("meta", attrs={"property": "og:title"}) or
        soup.find("meta", attrs={"property": "og:description"})
    )

    # Structured data (JSON-LD)
    has_structured_data = bool(soup.find("script", attrs={"type": "application/ld+json"}))

    # Internal links
    internal_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(url, href)
        parsed = urlparse(full)
        if parsed.netloc == base_domain and full not in internal_links:
            internal_links.append(full)

    # External links (http/https only, different domain)
    external_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(url, href)
        parsed = urlparse(full)
        if (
            parsed.scheme in ("http", "https")
            and parsed.netloc
            and parsed.netloc != base_domain
            and full not in external_links
        ):
            external_links.append(full)

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
        external_links=external_links[:10],
        word_count=word_count,
        content_text=body_text[:3000],
        canonical_url=canonical_url or None,
        is_noindex=is_noindex,
        has_og_tags=has_og_tags,
        has_structured_data=has_structured_data,
    )
