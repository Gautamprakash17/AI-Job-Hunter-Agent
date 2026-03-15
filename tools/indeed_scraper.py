"""
Indeed.com job scraper for AI Job Hunter Agent.

Scrapes job listings from Indeed using Playwright.
"""

import logging
import re
import time
from typing import List, Optional

from playwright.sync_api import Page

from tools.browser_automation import get_browser, get_browser_context, navigate_and_wait

logger = logging.getLogger(__name__)

# Indeed selectors - multiple fallbacks (Indeed uses dynamic classes)
JOB_CARD_SELECTORS = [
    "div[data-jk]",
    "div.job_seen_beacon",
    "div.slider_container div[data-jk]",
    "td.resultContent",
    ".jobsearch-ResultsList li",
]
TITLE_SELECTORS = [
    "h2.jobTitle",
    "h2[class*='jobTitle']",
    "a[data-jk]",
    "h2 a",
]
COMPANY_SELECTORS = [
    "span[data-testid='company-name']",
    ".companyName",
    "[class*='companyName']",
]
LOCATION_SELECTORS = [
    "div[data-testid='text-location']",
    ".companyLocation",
    "[class*='companyLocation']",
]


def _first_text(card, selectors: List[str]) -> str:
    for sel in selectors:
        try:
            el = card.query_selector(sel)
            if el:
                t = (el.text_content() or "").strip()
                if t:
                    return t
        except Exception:
            pass
    return ""


def scrape_indeed_jobs(
    search_query: str,
    location: Optional[str] = None,
    max_results: int = 25,
    fetch_descriptions: bool = False,
) -> List[dict]:
    """
    Scrape job listings from Indeed.com.

    Args:
        search_query: Job title or keywords.
        location: Location filter.
        max_results: Max jobs to return.
        fetch_descriptions: Whether to fetch full description (slower).

    Returns:
        List of job dicts.
    """
    jobs: List[dict] = []
    query = search_query.replace(" ", "+")
    base_url = f"https://www.indeed.com/jobs?q={query}"
    if location:
        base_url += f"&l={location.replace(' ', '+')}"

    with get_browser() as browser:
        with get_browser_context(browser) as context:
            page = context.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })

            if not navigate_and_wait(page, base_url):
                logger.error("Failed to load Indeed jobs page")
                return jobs

            time.sleep(4)

            try:
                cards = []
                for sel in JOB_CARD_SELECTORS:
                    cards = page.query_selector_all(sel)
                    if len(cards) > 2:  # Avoid matching too many elements
                        logger.debug("Using Indeed selector: %s", sel)
                        break
                if not cards:
                    cards = page.query_selector_all("div.job_seen_beacon, td.resultContent")

                collected = 0
                seen = set()

                for i, card in enumerate(cards):
                    if collected >= max_results:
                        break
                    try:
                        job_data = _extract_job_from_card(card)
                        if job_data and job_data.get("title"):
                            jk = job_data.get("external_id") or job_data.get("url", "")
                            if jk in seen:
                                continue
                            seen.add(jk)
                            job_data["portal"] = "indeed"
                            jobs.append(job_data)
                            collected += 1
                    except Exception as e:
                        logger.debug("Skipping Indeed card %d: %s", i, e)

            except Exception as e:
                logger.exception("Indeed scrape failed: %s", e)
            finally:
                page.close()

    logger.info("Scraped %d jobs from Indeed", len(jobs))
    return jobs


def _extract_job_from_card(card) -> Optional[dict]:
    try:
        title_el = card.query_selector("h2.jobTitle a, h2 a, a[data-jk]")
        title = _first_text(card, TITLE_SELECTORS)
        company = _first_text(card, COMPANY_SELECTORS)
        location = _first_text(card, LOCATION_SELECTORS)
        url = ""
        jk = ""
        if title_el:
            href = title_el.get_attribute("href")
            if href:
                url = f"https://www.indeed.com{href}" if not href.startswith("http") else href
            jk = title_el.get_attribute("data-jk") or ""

        if not title:
            return None

        return {
            "title": title,
            "company": company or "Unknown",
            "location": location,
            "url": url,
            "description": f"{title} at {company}. {location}",
            "external_id": jk or _extract_indeed_jk(url),
        }
    except Exception:
        return None


def _extract_indeed_jk(url: str) -> Optional[str]:
    if not url:
        return None
    m = re.search(r"jk=([a-f0-9]+)", url)
    return m.group(1) if m else None
