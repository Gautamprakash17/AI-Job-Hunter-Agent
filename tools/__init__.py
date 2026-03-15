"""Tools module for scraping and browser automation."""

from tools.browser_automation import (
    click_element,
    extract_text,
    fill_form_field,
    get_browser,
    get_browser_context,
    navigate_and_wait,
)
from tools.indeed_scraper import scrape_indeed_jobs
from tools.linkedin_scraper import scrape_linkedin_jobs
from tools.naukri_scraper import scrape_naukri_jobs

__all__ = [
    "scrape_indeed_jobs",
    "get_browser",
    "get_browser_context",
    "navigate_and_wait",
    "fill_form_field",
    "click_element",
    "extract_text",
    "scrape_linkedin_jobs",
    "scrape_naukri_jobs",
]
