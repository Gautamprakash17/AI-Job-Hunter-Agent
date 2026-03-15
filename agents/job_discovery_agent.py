"""
Job Discovery Agent for AI Job Hunter Agent.

Searches jobs based on role and experience using Playwright to simulate
job search across multiple portals. Scrapes title, company, description, and URL.
"""

import logging
from typing import List, Optional

from config.settings import settings
from tools.indeed_scraper import scrape_indeed_jobs
from tools.linkedin_scraper import scrape_linkedin_jobs
from tools.naukri_scraper import scrape_naukri_jobs

logger = logging.getLogger(__name__)

# Demo jobs for testing when scrapers return 0
DEMO_JOBS = [
    {
        "title": "AI Engineer",
        "company": "TechCorp",
        "description": "Build ML models with Python, TensorFlow. 2+ years experience. FastAPI, AWS.",
        "url": "https://example.com/demo1",
        "location": "Remote",
        "portal": "demo",
        "external_id": "demo-1",
    },
    {
        "title": "ML Engineer",
        "company": "StartupXYZ",
        "description": "FastAPI, ML pipelines, recommendation systems. Python, PyTorch.",
        "url": "https://example.com/demo2",
        "location": "Bangalore",
        "portal": "demo",
        "external_id": "demo-2",
    },
    {
        "title": "Senior AI Engineer",
        "company": "BigTech",
        "description": "LangChain, LLMs, embeddings. Production ML systems.",
        "url": "https://example.com/demo3",
        "location": "Remote",
        "portal": "demo",
        "external_id": "demo-3",
    },
]


def discover_jobs(
    target_role: str,
    location: Optional[str] = None,
    experience_years: Optional[float] = None,
    portals: Optional[List[str]] = None,
    max_per_portal: int = 15,
    fetch_descriptions: bool = True,
) -> List[dict]:
    """
    Discover jobs from configured portals based on target role and experience.

    Uses Playwright via portal-specific scrapers to simulate job search and
    extract full job details including descriptions.

    Args:
        target_role: Desired job title (e.g., "AI Engineer").
        location: Location filter for jobs (e.g., "Remote", "India").
        experience_years: Optional. Years of experience for portal-specific filters.
            Pass None or omit to show all jobs (no experience filter).
        portals: List of portals to scrape. Default: ["linkedin", "indeed", "naukri"].
        max_per_portal: Max jobs per portal.
        fetch_descriptions: Whether to fetch full job descriptions.

    Returns:
        List of job dicts with keys: title, company, description, url.
        Example:
        [
            {
                "title": "AI Engineer",
                "company": "Company X",
                "description": "...",
                "url": "job_link"
            }
        ]
    """
    portals = portals or ["linkedin", "indeed", "naukri"]
    all_jobs: List[dict] = []
    seen_urls: set = set()

    experience_str = (
        _format_experience(experience_years) if experience_years is not None else None
    )

    for portal in portals:
        try:
            if portal.lower() == "linkedin":
                jobs = scrape_linkedin_jobs(
                    search_query=target_role,
                    location=location,
                    experience_years=experience_years,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                )
            elif portal.lower() == "naukri":
                jobs = scrape_naukri_jobs(
                    search_query=target_role,
                    location=location,
                    experience=experience_str,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                )
            elif portal.lower() == "indeed":
                jobs = scrape_indeed_jobs(
                    search_query=target_role,
                    location=location,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                )
            else:
                logger.warning("Unknown portal: %s", portal)
                continue

            for job in jobs:
                url = job.get("url", "") or ""
                dedup_key = url or f"{job.get('title','')}|{job.get('company','')}"
                if dedup_key and dedup_key not in seen_urls:
                    seen_urls.add(dedup_key)
                    all_jobs.append(_normalize_job_output(job))

        except Exception as e:
            logger.exception("Discovery failed for portal %s: %s", portal, e)

    # Use demo jobs when scrapers return 0 (for testing)
    if not all_jobs and getattr(settings, "use_demo_jobs_on_empty", True):
        logger.info("Using demo jobs for testing (scrapers returned 0)")
        for job in DEMO_JOBS:
            all_jobs.append(_normalize_job_output(job))

    logger.info("Discovered %d unique jobs from %s", len(all_jobs), portals)
    return all_jobs


def _normalize_job_output(job: dict) -> dict:
    """Ensure output has required keys: title, company, description, url."""
    return {
        "title": str(job.get("title") or "").strip() or "Unknown",
        "company": str(job.get("company") or "").strip() or "Unknown",
        "description": str(job.get("description") or "").strip()
        or f"{job.get('title', '')} at {job.get('company', '')}",
        "url": str(job.get("url") or "").strip(),
        "location": str(job.get("location") or "").strip(),
        "portal": str(job.get("portal") or "").strip(),
        "external_id": job.get("external_id"),
    }


def _format_experience(years: float) -> str:
    """Format experience for portal filters (e.g., 1.0 -> '1-3')."""
    if years < 1:
        return "0-1"
    if years < 3:
        return "1-3"
    if years < 5:
        return "3-5"
    if years < 10:
        return "5-10"
    return "10+"


# -----------------------------------------------------------------------------
# Example usage
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    import json

    # Discover jobs for AI Engineer with 1 year experience
    jobs = discover_jobs(
        target_role="AI Engineer",
        location="Remote",
        experience_years=1.0,
        portals=["linkedin"],
        max_per_portal=5,
        fetch_descriptions=True,
    )
    print(json.dumps(jobs, indent=2)[:1500])
