"""
LinkedIn job scraper for AI Job Hunter Agent.

Scrapes job listings from LinkedIn using Playwright browser automation.
Uses current LinkedIn jobs search page structure (base-card, base-search-card).
"""

import logging
import re
import time
from datetime import datetime
from typing import List, Optional

from playwright.sync_api import Page

from config.settings import settings
from tools.browser_automation import get_browser, get_browser_context, navigate_and_wait
from utils.job_posted_date import PostedDateFilter, freeze_posted_timestamp, portal_url_date_params

logger = logging.getLogger(__name__)

# LinkedIn selectors - current structure (base-card, base-search-card)
JOB_CARD_SELECTORS = [
    "div.base-card.base-card--link.job-search-card",
    "div.base-card",
    "li.job-card-container",
    "li[class*='job-card']",
    ".jobs-search-results__list-item",
]
TITLE_SELECTORS = [
    "h3.base-search-card__title",
    "a.base-card__full-link",
    "a.job-card-list__title",
    "[class*='job-card'] a",
]
COMPANY_SELECTORS = [
    "h4.base-search-card__subtitle",
    ".job-card-container__company-name",
    "[class*='company-name']",
]
LOCATION_SELECTORS = [
    "span.job-search-card__location",
    ".job-card-container__metadata-item",
    "[class*='metadata']",
]
DATE_SELECTORS = [
    "time.job-search-card__listdate",
    "span.job-search-card__listdate",
    "time",
    "[class*='listdate']",
    "[class*='posted']",
]
LINK_SELECTORS = [
    "a.base-card__full-link",
    "a.base-card",
    "a[href*='/jobs/view/']",
    "a.job-card-list__title",
]
DESCRIPTION_SELECTORS = [
    ".jobs-description__content",
    ".show-more-less-html__markup",
    "[class*='jobs-description']",
    ".jobs-search__job-details",
]


def _first_element(card, selectors: List[str]):
    """Return first matching element."""
    for sel in selectors:
        try:
            el = card.query_selector(sel)
            if el:
                return el
        except Exception:
            pass
    return None


def _first_text(card, selectors: List[str]) -> str:
    """Return first non-empty text from selectors."""
    el = _first_element(card, selectors)
    return (el.text_content() or "").strip() if el else ""


def scrape_linkedin_jobs(
    search_query: str,
    location: Optional[str] = None,
    experience_years: Optional[float] = None,
    max_results: int = 25,
    fetch_descriptions: bool = True,
    posted_date_filter: PostedDateFilter = "any_time",
    scrape_reference_time_utc: Optional[datetime] = None,
) -> List[dict]:
    """
    Scrape job listings from LinkedIn based on search criteria.

    Args:
        search_query: Job title or keywords (e.g., "AI Engineer").
        location: Location filter (e.g., "Remote", "India").
        experience_years: Years of experience for filter.
        max_results: Maximum number of jobs to return.
        fetch_descriptions: Whether to click into each job to fetch description.

    Returns:
        List of job dicts with title, company, description, url.
    """
    jobs: List[dict] = []
    query_encoded = search_query.replace(" ", "%20")
    base_url = f"https://www.linkedin.com/jobs/search/?keywords={query_encoded}"
    if location:
        base_url += f"&location={location.replace(' ', '%20')}"
    if experience_years is not None:
        exp_filter = _experience_to_linkedin(experience_years)
        if exp_filter:
            base_url += f"&f_E={exp_filter}"
    for key, value in portal_url_date_params("linkedin", posted_date_filter).items():
        base_url += f"&{key}={value}"

    with get_browser() as browser:
        with get_browser_context(browser) as context:
            page = context.new_page()

            # Set user agent to reduce bot detection
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            })

            if not navigate_and_wait(page, base_url):
                logger.error("Failed to load LinkedIn jobs page")
                return jobs

            time.sleep(4)  # Allow dynamic content to load

            try:
                cards = []
                for sel in JOB_CARD_SELECTORS:
                    cards = page.query_selector_all(sel)
                    if cards:
                        logger.debug("Using card selector: %s", sel)
                        break

                if not cards:
                    logger.warning("No job cards found with standard selectors")
                    cards = page.query_selector_all("li[class*='job']")

                collected = 0
                seen_urls = set()

                for i, card in enumerate(cards):
                    if collected >= max_results:
                        break
                    try:
                        job_data = _extract_job_from_card(
                            page, card, fetch_descriptions, scrape_reference_time_utc
                        )
                        if job_data and job_data.get("title"):
                            url = job_data.get("url", "")
                            if url and url in seen_urls:
                                continue
                            if url:
                                seen_urls.add(url)
                            job_data["portal"] = "linkedin"
                            jobs.append(job_data)
                            collected += 1
                            if fetch_descriptions:
                                time.sleep(0.5)  # Rate limit
                    except Exception as e:
                        logger.debug("Skipping card %d: %s", i, e)

            except Exception as e:
                logger.exception("LinkedIn scrape failed: %s", e)
            finally:
                page.close()

    logger.info("Scraped %d jobs from LinkedIn", len(jobs))
    return jobs


def _extract_job_from_card(
    page: Page,
    card,
    fetch_description: bool = True,
    scrape_reference_time_utc: Optional[datetime] = None,
) -> Optional[dict]:
    """Extract job data from a LinkedIn job card."""
    try:
        title = _first_text(card, TITLE_SELECTORS)
        company = _first_text(card, COMPANY_SELECTORS)
        location = _first_text(card, LOCATION_SELECTORS)
        posted_date = _first_text(card, DATE_SELECTORS)
        time_el = _first_element(card, ["time"])
        if time_el and not posted_date:
            posted_date = (time_el.get_attribute("datetime") or "").strip() or posted_date

        link_el = _first_element(card, LINK_SELECTORS)
        url = link_el.get_attribute("href") if link_el else ""

        if not title:
            return None

        if url and not url.startswith("http"):
            url = f"https://www.linkedin.com{url}"

        description = ""
        if fetch_description and link_el:
            try:
                link_el.click()
                time.sleep(1.5)
                for sel in DESCRIPTION_SELECTORS:
                    desc_el = page.query_selector(sel)
                    if desc_el:
                        description = (desc_el.text_content() or "").strip()[:5000]
                        break
            except Exception:
                pass

        job: dict = {
            "title": title,
            "company": company,
            "location": location,
            "url": url,
            "description": description or f"{title} at {company}.",
            "external_id": _extract_linkedin_job_id(url),
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


def _experience_to_linkedin(years: float) -> str:
    """Map experience years to LinkedIn filter param (f_E)."""
    if years < 1:
        return "1"
    if years < 3:
        return "2"
    if years < 5:
        return "3"
    if years < 10:
        return "4"
    return "5"


def _extract_linkedin_job_id(url: str) -> Optional[str]:
    """Extract job ID from LinkedIn URL."""
    if not url:
        return None
    match = re.search(r"job/view/(\d+)", url) or re.search(r"currentJobId=(\d+)", url)
    return match.group(1) if match else None
