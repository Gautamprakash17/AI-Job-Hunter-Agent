"""
Naukri.com job scraper for AI Job Hunter Agent.

Uses Playwright to handle dynamic content. Tries multiple selectors
for job cards (Naukri changes structure often). Waits for content
then extracts title, company, location, and job URL.
"""

import logging
import re
from typing import List, Optional

from tools.browser_automation import get_browser, get_browser_context

logger = logging.getLogger(__name__)

# Naukri uses nI-gNb-* classes in newer UI (e.g. nI-gNb-sb__placeholder for search). Try new first, then legacy.
JOB_CARD_SELECTORS = [
    "[class*='nI-gNb'][class*='job']",
    "li[class*='nI-gNb']",
    "div[class*='nI-gNb-job']",
    "article[class*='nI-gNb']",
    ".srp-jobtuple-wrapper",
    "div.jobTuple",
    ".jobTuple.bgWhite",
    "article.jobTuple",
    "[class*='jobtuple']",
    "div[class*='jobTuple']",
    "article[class*='job']",
    ".list",
    "article",
]

# Wait for new UI to be present (search placeholder: nI-gNb-sb__placeholder)
PAGE_READY_SELECTORS = [
    "span.nI-gNb-sb__placeholder",
    "[class*='nI-gNb-sb']",
    "[class*='nI-gNb']",
    ".srp-jobtuple-wrapper",
]

TITLE_SELECTORS = [
    "a[href*='job-details']",
    "a.title",
    "a[class*='title']",
    "a[class*='nI-gNb']",
    ".jobTitle",
]
COMPANY_SELECTORS = [
    "a.comp-name",
    "a[class*='comp-name']",
    "[class*='nI-gNb'][class*='company']",
    ".companyName",
    "[class*='company']",
]
LOCATION_SELECTORS = [
    "span.locWdth",
    "span.loc-wrap",
    "[class*='nI-gNb'][class*='loc']",
    ".location",
    "span[class*='loc']",
    ".loc",
]

# Wait for dynamic content and reduce bot detection
INITIAL_WAIT_MS = 4000
SELECTOR_TIMEOUT_MS = 25000
NAV_TIMEOUT_MS = 45000


def _normalize_url(url: Optional[str]) -> str:
    """Ensure job URL is absolute."""
    if not url or not url.strip():
        return ""
    url = url.strip()
    if url.startswith("http"):
        return url
    if url.startswith("/"):
        return f"https://www.naukri.com{url}"
    return f"https://www.naukri.com/{url}"


def _extract_text(el) -> str:
    """Safe text extraction from element."""
    if el is None:
        return ""
    try:
        return (el.text_content() or "").strip() or ""
    except Exception:
        return ""


def _first(card, selectors: List[str], attr: Optional[str] = None):
    """Return first matching element; if attr, return attribute value."""
    for sel in selectors:
        try:
            el = card.query_selector(sel)
            if el:
                if attr:
                    return el.get_attribute(attr) or ""
                return el
        except Exception:
            pass
    return None


def _first_text_from_selectors(card, selectors: List[str]) -> str:
    """Get text from first element matching any selector."""
    el = _first(card, selectors)
    return _extract_text(el) if el else ""


def scrape_naukri_jobs(
    search_query: str,
    location: Optional[str] = None,
    experience: Optional[str] = None,
    max_results: int = 25,
    fetch_descriptions: bool = True,
) -> List[dict]:
    """
    Scrape job listings from Naukri.com using Playwright.

    Tries multiple job-card selectors (Naukri DOM changes). Waits for
    content to load, optionally dismisses overlay, then extracts from each card.
    """
    jobs: List[dict] = []
    slug = search_query.replace(" ", "-").lower()
    search_url = f"https://www.naukri.com/{slug}-jobs"
    if location:
        loc_slug = location.replace(" ", "-").lower()
        search_url += f"-in-{loc_slug}"

    # Non-headless helps with Naukri (fewer bot blocks) and debugging
    with get_browser(headless=False) as browser:
        with get_browser_context(browser) as context:
            page = context.new_page()
            page.set_default_timeout(SELECTOR_TIMEOUT_MS)

            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            })

            urls_to_try = [search_url]
            if location:
                # Fallback: try without location in case location breaks the page
                urls_to_try.append(f"https://www.naukri.com/{slug}-jobs")

            cards = []
            for try_url in urls_to_try:
                try:
                    page.goto(
                        try_url,
                        wait_until="domcontentloaded",
                        timeout=NAV_TIMEOUT_MS,
                    )
                except Exception as e:
                    logger.warning("Naukri navigation failed for %s: %s", try_url, e)
                    continue

                page.wait_for_timeout(INITIAL_WAIT_MS)

                # Wait for page to be ready (new UI: nI-gNb-sb__placeholder or legacy)
                for ready_sel in PAGE_READY_SELECTORS:
                    try:
                        page.wait_for_selector(ready_sel, timeout=6000)
                        logger.debug("Naukri page ready: %s", ready_sel)
                        break
                    except Exception:
                        pass

                # Dismiss cookie/overlay if present
                for btn in ["#block", ".qc-cmp2-summary-buttons button", "[data-cy='cookie-consent-accept']", ".bClose", "button:has-text('OK')", "button:has-text('Accept')"]:
                    try:
                        page.click(btn, timeout=2000)
                        page.wait_for_timeout(500)
                        break
                    except Exception:
                        pass

                for card_sel in JOB_CARD_SELECTORS:
                    try:
                        page.wait_for_selector(card_sel, timeout=8000)
                        cards = page.query_selector_all(card_sel)
                        if len(cards) >= 1:
                            logger.info("Naukri: using '%s' (%d cards) from %s", card_sel, len(cards), try_url)
                            break
                    except Exception:
                        continue
                if cards:
                    break

            # Fallback: find job links; use each link as card (title + url from link, company/location may be empty)
            if not cards:
                try:
                    job_links = page.query_selector_all('a[href*="job-details"]')
                    cards = []
                    seen = set()
                    for link in job_links:
                        href = (link.get_attribute("href") or "").strip()
                        if not href or "job-details" not in href or href in seen:
                            continue
                        seen.add(href)
                        cards.append(link)
                    if cards:
                        logger.info("Naukri: using job-details links as cards (%d)", len(cards))
                except Exception as e:
                    logger.debug("Naukri job-details fallback failed: %s", e)

            if not cards:
                logger.warning("Naukri: no job cards found with any selector. Page may have changed or be blocking.")
                page.close()
                return jobs

            seen_urls: set = set()
            collected = 0

            for card in cards:
                if collected >= max_results:
                    break
                try:
                    job = _extract_job_from_card(card)
                    if not job or not job.get("title"):
                        continue
                    url = job.get("url") or ""
                    if url and url in seen_urls:
                        continue
                    if url:
                        seen_urls.add(url)
                    job["portal"] = "naukri"
                    job["description"] = job.get("description") or f"{job.get('title', '')} at {job.get('company', '')}"
                    job["external_id"] = _extract_naukri_job_id(url)
                    jobs.append(job)
                    collected += 1
                except Exception as e:
                    logger.debug("Skipping Naukri card: %s", e)

            page.close()

    logger.info("Scraped %d jobs from Naukri", len(jobs))
    return jobs


def _extract_job_from_card(card) -> Optional[dict]:
    """Extract title, company, location, url from one job card using multiple fallbacks."""
    try:
        title = ""
        job_url = ""

        for sel in TITLE_SELECTORS:
            el = card.query_selector(sel)
            if el:
                title = _extract_text(el)
                job_url = el.get_attribute("href") or ""
                if title or job_url:
                    break
        job_url = _normalize_url(job_url)

        company = _first_text_from_selectors(card, COMPANY_SELECTORS)
        location = _first_text_from_selectors(card, LOCATION_SELECTORS)

        if not title and job_url:
            title = "Job"
        if not title:
            return None

        return {
            "title": title,
            "company": company or "Unknown",
            "location": location,
            "url": job_url,
            "description": "",
        }
    except Exception:
        return None


def _extract_naukri_job_id(url: str) -> Optional[str]:
    """Extract job ID from Naukri URL."""
    if not url:
        return None
    match = re.search(r"job-details/([^/?]+)", url) or re.search(r"nj[=_](\w+)", url)
    return match.group(1) if match else None
