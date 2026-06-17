"""
Naukri.com job scraper for AI Job Hunter Agent.

Uses Playwright to handle dynamic content. Tries multiple selectors
for job cards (Naukri changes structure often). Waits for content
then extracts title, company, location, and job URL.
Total run is capped at ~65s so the UI does not hang.
"""

import logging
import re
import time
from datetime import datetime
from typing import List, Optional

from tools.browser_automation import get_browser, get_browser_context, STEALTH_LAUNCH_ARGS
from utils.job_posted_date import PostedDateFilter, freeze_posted_timestamp

logger = logging.getLogger(__name__)

# Live SRP structure (March 2026): job list in #listContainer, each job in .srp-jobtuple-wrapper
JOB_CARD_SELECTORS = [
    ".srp-jobtuple-wrapper",
    "div.srp-jobtuple-wrapper",
    "#listContainer .srp-jobtuple-wrapper",
    "div.cust-job-tuple.sjw__tuple",
    "div[data-job-id]",
    "[class*='jobtuple']",
    "div.jobTuple",
    ".jobTuple.bgWhite",
    "article.jobTuple",
]

# Wait for list or a job card to be present
PAGE_READY_SELECTORS = [
    ".srp-jobtuple-wrapper",
    "#listContainer",
    "div.styles_job-listing-container__OCfZC",
    "span.nI-gNb-sb__placeholder",
    "[class*='nI-gNb-sb']",
]

# Title: h2 > a.title with href like job-listings-...-090326500780
TITLE_SELECTORS = [
    "a.title",
    "h2 a.title",
    "a[href*='job-listings']",
    "a[href*='job-details']",
    "a[class*='title']",
    ".jobTitle",
]
COMPANY_SELECTORS = [
    "a.comp-name",
    ".comp-dtls-wrap a.comp-name",
    "a[class*='comp-name']",
    ".companyName",
]
LOCATION_SELECTORS = [
    "span.locWdth",
    "span.loc .locWdth",
    ".loc span.locWdth",
    ".job-details .loc",
    "span.loc-wrap",
    ".location",
]
DATE_SELECTORS = [
    "span.job-post-day",
    "span[type='latest']",
    ".job-post-day",
    "[class*='posted']",
    "[class*='daysAgo']",
]

# Balance: enough wait for Naukri JS to render, but cap total run
INITIAL_WAIT_MS = 5000   # Naukri is React/Next; list renders after ~3–4s
SELECTOR_TIMEOUT_MS = 10000
NAV_TIMEOUT_MS = 18000
PAGE_READY_TIMEOUT_MS = 8000   # single wait for list or link
SCRAPE_TOTAL_TIMEOUT_MS = 55000  # 55s cap
MAX_CARD_SELECTOR_TRIES = 5


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
    posted_date_filter: PostedDateFilter = "any_time",
    scrape_reference_time_utc: Optional[datetime] = None,
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

    def _elapsed_ms():
        return (time.time() - start_time) * 1000

    start_time = time.time()

    # Stealth args reduce "Access Denied"; prefer system Chrome when available
    with get_browser(
        headless=True,
        launch_timeout_ms=15000,
        args=STEALTH_LAUNCH_ARGS,
        channel="chrome",
    ) as browser:
        with get_browser_context(browser) as context:
            page = context.new_page()
            page.set_default_timeout(SELECTOR_TIMEOUT_MS)

            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "en-US,en;q=0.9",
            })

            urls_to_try = [search_url]
            if location:
                urls_to_try.append(f"https://www.naukri.com/{slug}-jobs")

            cards = []
            for try_url in urls_to_try:
                if _elapsed_ms() > SCRAPE_TOTAL_TIMEOUT_MS:
                    logger.warning("Naukri: total timeout reached, stopping.")
                    break
                try:
                    page.goto(
                        try_url,
                        wait_until="load",
                        timeout=NAV_TIMEOUT_MS,
                    )
                except Exception as e:
                    logger.warning("Naukri navigation failed for %s: %s", try_url, e)
                    continue

                page.wait_for_timeout(INITIAL_WAIT_MS)

                if _elapsed_ms() > SCRAPE_TOTAL_TIMEOUT_MS:
                    break

                # Wait for job list or at least one job link (Naukri renders via JS)
                page_ready = False
                for ready_sel in PAGE_READY_SELECTORS[:2]:
                    try:
                        page.wait_for_selector(ready_sel, timeout=PAGE_READY_TIMEOUT_MS)
                        page_ready = True
                        break
                    except Exception:
                        continue
                if not page_ready:
                    try:
                        page.wait_for_selector('a[href*="job-listings"]', timeout=4000)
                        page_ready = True
                    except Exception:
                        pass

                # Dismiss cookie/overlay so selectors are visible
                for btn in ["#block", ".qc-cmp2-summary-buttons button", ".bClose", "button:has-text('OK')", "button:has-text('Accept')"]:
                    try:
                        page.click(btn, timeout=1500)
                        page.wait_for_timeout(300)
                        break
                    except Exception:
                        pass

                if _elapsed_ms() > SCRAPE_TOTAL_TIMEOUT_MS:
                    break

                # Try card selectors (no skip if page_ready was False – still try)
                for i, card_sel in enumerate(JOB_CARD_SELECTORS):
                    if i >= MAX_CARD_SELECTOR_TRIES or _elapsed_ms() > SCRAPE_TOTAL_TIMEOUT_MS:
                        break
                    try:
                        page.wait_for_selector(card_sel, timeout=5000)
                        cards = page.query_selector_all(card_sel)
                        if len(cards) >= 1:
                            logger.info("Naukri: using '%s' (%d cards)", card_sel, len(cards))
                            break
                    except Exception:
                        continue
                if cards:
                    break

            # Fallback: find job links
            if not cards and _elapsed_ms() <= SCRAPE_TOTAL_TIMEOUT_MS:
                try:
                    job_links = page.query_selector_all('a[href*="job-listings"], a[href*="job-details"]')
                    cards = []
                    seen = set()
                    for link in job_links:
                        href = (link.get_attribute("href") or "").strip()
                        if not href or href in seen or ("job-listings" not in href and "job-details" not in href):
                            continue
                        seen.add(href)
                        cards.append(link)
                    if cards:
                        logger.info("Naukri: using job links as cards (%d)", len(cards))
                except Exception as e:
                    logger.debug("Naukri job-links fallback failed: %s", e)

            if not cards:
                try:
                    final_url = page.url
                    title = page.title()
                    logger.warning(
                        "Naukri: no job cards found. final_url=%s page_title=%s",
                        final_url[:80] if final_url else "",
                        title[:60] if title else "",
                    )
                except Exception:
                    pass
                page.close()
                return jobs

            seen_urls: set = set()
            collected = 0
            for card in cards:
                if collected >= max_results or _elapsed_ms() > SCRAPE_TOTAL_TIMEOUT_MS:
                    break
                try:
                    job = _extract_job_from_card(card, scrape_reference_time_utc)
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

    logger.info("Scraped %d jobs from Naukri in %.1fs", len(jobs), _elapsed_ms() / 1000)
    return jobs


def _extract_job_from_card(
    card,
    scrape_reference_time_utc: Optional[datetime] = None,
) -> Optional[dict]:
    """Extract title, company, location, url from one job card using multiple fallbacks."""
    try:
        root = card
        title = ""
        job_url = ""

        for sel in TITLE_SELECTORS:
            el = root.query_selector(sel)
            if el:
                title = _extract_text(el)
                job_url = el.get_attribute("href") or ""
                if title or job_url:
                    break
        job_url = _normalize_url(job_url)

        company = _first_text_from_selectors(root, COMPANY_SELECTORS)
        location = _first_text_from_selectors(root, LOCATION_SELECTORS)
        posted_date = _first_text_from_selectors(root, DATE_SELECTORS)

        if not title and job_url:
            title = "Job"
        if not title:
            return None

        job: dict = {
            "title": title,
            "company": company or "Unknown",
            "location": location,
            "url": job_url,
            "description": "",
        }
        if scrape_reference_time_utc is not None:
            frozen = freeze_posted_timestamp(posted_date, scrape_reference_time_utc)
            job["posted_date_raw"] = frozen["posted_date_raw"]
            job["posted_at_utc"] = frozen["posted_at_utc"]
            job["posted_date"] = frozen["posted_at_utc"]
        else:
            job["posted_date"] = posted_date or None
        return job
    except Exception:
        return None


def _extract_naukri_job_id(url: str) -> Optional[str]:
    """Extract job ID from Naukri URL (job-listings-...-ID or job-details/ID)."""
    if not url:
        return None
    # job-listings-...-090326500780
    match = re.search(r"-(\d{8,})$", url.split("?")[0])
    if match:
        return match.group(1)
    match = re.search(r"job-details/([^/?]+)", url) or re.search(r"nj[=_](\w+)", url)
    return match.group(1) if match else None
