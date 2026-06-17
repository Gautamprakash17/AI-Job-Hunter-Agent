"""
Job Discovery Agent for AI Job Hunter Agent.

Searches jobs based on role and experience using Playwright to simulate
job search across multiple portals. Runs scrapers sequentially to avoid
Playwright event-loop conflicts (e.g. under Streamlit).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

from config.settings import settings
from tools.indeed_scraper import scrape_indeed_jobs
from tools.linkedin_scraper import scrape_linkedin_jobs
from tools.naukri_scraper import scrape_naukri_jobs
from utils.job_posted_date import (
    PostedDateFilter,
    PostedDateFilterMetrics,
    build_scrape_metrics,
    freeze_posted_timestamp,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryResult:
    """Output from job discovery including frozen timestamps and metrics."""

    jobs: List[dict]
    workflow_reference_time_utc: str
    scrape_posted_date_filter: PostedDateFilter
    scrape_metrics: PostedDateFilterMetrics


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
        "posted_date": "Just now",
    },
    {
        "title": "ML Engineer",
        "company": "StartupXYZ",
        "description": "FastAPI, ML pipelines, recommendation systems. Python, PyTorch.",
        "url": "https://example.com/demo2",
        "location": "Bangalore",
        "portal": "demo",
        "external_id": "demo-2",
        "posted_date": "2 hours ago",
    },
    {
        "title": "Senior AI Engineer",
        "company": "BigTech",
        "description": "LangChain, LLMs, embeddings. Production ML systems.",
        "url": "https://example.com/demo3",
        "location": "Remote",
        "portal": "demo",
        "external_id": "demo-3",
        "posted_date": "Today",
    },
]


def discover_jobs(
    target_role: str,
    location: Optional[str] = None,
    experience_years: Optional[float] = None,
    portals: Optional[List[str]] = None,
    max_per_portal: int = 15,
    fetch_descriptions: bool = True,
    posted_date_filter: PostedDateFilter = "any_time",
    workflow_reference_time_utc: Optional[datetime] = None,
) -> DiscoveryResult:
    """
    Discover jobs from configured portals based on target role and experience.

    Timestamps are frozen at ``workflow_reference_time_utc``. All scraped jobs
    are returned (date filtering is applied downstream with the same reference).
    """
    ref = workflow_reference_time_utc or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    else:
        ref = ref.astimezone(timezone.utc)

    portals = portals or ["linkedin", "indeed", "naukri"]
    all_jobs: List[dict] = []
    seen_urls: set = set()

    experience_str = (
        _format_experience(experience_years) if experience_years is not None else None
    )

    for portal in portals:
        p = portal.lower()
        try:
            if p == "linkedin":
                jobs = scrape_linkedin_jobs(
                    search_query=target_role,
                    location=location,
                    experience_years=experience_years,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                    posted_date_filter=posted_date_filter,
                    scrape_reference_time_utc=ref,
                )
            elif p == "naukri":
                jobs = scrape_naukri_jobs(
                    search_query=target_role,
                    location=location,
                    experience=experience_str,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                    posted_date_filter=posted_date_filter,
                    scrape_reference_time_utc=ref,
                )
            elif p == "indeed":
                jobs = scrape_indeed_jobs(
                    search_query=target_role,
                    location=location,
                    max_results=max_per_portal,
                    fetch_descriptions=fetch_descriptions,
                    posted_date_filter=posted_date_filter,
                    scrape_reference_time_utc=ref,
                )
            else:
                logger.warning("Unknown portal: %s", portal)
                continue
            for job in jobs:
                url = job.get("url", "") or ""
                dedup_key = url or f"{job.get('title','')}|{job.get('company','')}"
                if dedup_key and dedup_key not in seen_urls:
                    seen_urls.add(dedup_key)
                    all_jobs.append(_normalize_job_output(job, ref))
        except Exception as e:
            logger.exception("Discovery failed for portal %s: %s", portal, e)

    if not all_jobs and getattr(settings, "use_demo_jobs_on_empty", False):
        logger.info("Using demo jobs (use_demo_jobs_on_empty=True)")
        for job in DEMO_JOBS:
            all_jobs.append(_normalize_job_output(job, ref))

    metrics = build_scrape_metrics(all_jobs)
    logger.info(
        "Discovered %d unique jobs from %s (missing_date=%d invalid_date=%d) @ %s",
        len(all_jobs),
        portals,
        metrics.jobs_missing_posted_date,
        metrics.jobs_invalid_posted_date,
        ref.isoformat(),
    )
    return DiscoveryResult(
        jobs=all_jobs,
        workflow_reference_time_utc=ref.isoformat(),
        scrape_posted_date_filter=posted_date_filter,
        scrape_metrics=metrics,
    )


def _normalize_job_output(job: dict, reference_now: datetime) -> dict:
    """Ensure output has required keys and frozen posted-date fields."""
    if job.get("posted_at_utc"):
        frozen = {
            "posted_date_raw": job.get("posted_date_raw"),
            "posted_at_utc": job.get("posted_at_utc"),
        }
    else:
        raw = job.get("posted_date_raw") or job.get("posted_date")
        frozen = freeze_posted_timestamp(raw, reference_now)
    return {
        "title": str(job.get("title") or "").strip() or "Unknown",
        "company": str(job.get("company") or "").strip() or "Unknown",
        "description": str(job.get("description") or "").strip()
        or f"{job.get('title', '')} at {job.get('company', '')}",
        "url": str(job.get("url") or "").strip(),
        "location": str(job.get("location") or "").strip(),
        "portal": str(job.get("portal") or "").strip(),
        "external_id": job.get("external_id"),
        "posted_date_raw": frozen["posted_date_raw"],
        "posted_at_utc": frozen["posted_at_utc"],
        # Backward-compatible alias for consumers expecting posted_date
        "posted_date": frozen["posted_at_utc"],
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


if __name__ == "__main__":
    import json

    result = discover_jobs(
        target_role="AI Engineer",
        location="Remote",
        experience_years=1.0,
        portals=["linkedin"],
        max_per_portal=5,
        fetch_descriptions=True,
    )
    print(json.dumps(result.jobs, indent=2)[:1500])
