"""Integration tests for posted-date filtering in discovery pipeline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from agents.job_discovery_agent import discover_jobs, _normalize_job_output
from utils.job_posted_date import (
    filter_jobs_by_posted_date_with_metrics,
    freeze_posted_timestamp,
    get_posted_at_utc,
    is_filter_widening,
)

UTC = timezone.utc
NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=UTC)


def _mock_job(title: str, hours_ago: int):
    posted = NOW - timedelta(hours=hours_ago)
    frozen = freeze_posted_timestamp(f"{hours_ago} hours ago", NOW)
    return _normalize_job_output(
        {
            "title": title,
            "company": "Co",
            "description": "desc",
            "url": f"https://example.com/{title}",
            "portal": "linkedin",
            "posted_date_raw": frozen["posted_date_raw"],
            "posted_at_utc": posted.isoformat(),
        },
        NOW,
    )


@patch("agents.job_discovery_agent.scrape_linkedin_jobs")
@patch("agents.job_discovery_agent.scrape_indeed_jobs")
@patch("agents.job_discovery_agent.scrape_naukri_jobs")
def test_discover_jobs_returns_frozen_metadata(mock_naukri, mock_indeed, mock_linkedin):
    mock_linkedin.return_value = [
        {
            "title": "J",
            "company": "C",
            "url": "u",
            "portal": "linkedin",
            "posted_date_raw": "2 hours ago",
            "posted_at_utc": (NOW - timedelta(hours=2)).isoformat(),
        }
    ]
    mock_indeed.return_value = []
    mock_naukri.return_value = []

    result = discover_jobs(
        target_role="AI Engineer",
        portals=["linkedin"],
        posted_date_filter="last_3_days",
        workflow_reference_time_utc=NOW,
    )
    assert result.workflow_reference_time_utc == NOW.isoformat()
    assert result.scrape_posted_date_filter == "last_3_days"
    assert len(result.jobs) == 1
    assert result.jobs[0]["posted_at_utc"] is not None
    assert result.scrape_metrics.total_jobs_scraped == 1


def test_normalize_and_filter_pipeline():
    jobs = [_mock_job("fresh", 2), _mock_job("old", 200)]
    filtered, metrics = filter_jobs_by_posted_date_with_metrics(jobs, "last_24_hours", NOW)
    assert len(filtered) == 1
    assert filtered[0]["title"] == "fresh"
    assert metrics.jobs_remaining_after_filter == 1
    assert metrics.jobs_filtered_by_date == 1


def test_filter_results_stable_as_time_passes():
    jobs = [_mock_job("fresh", 2)]
    filtered_t0, _ = filter_jobs_by_posted_date_with_metrics(jobs, "last_24_hours", NOW)
    later = NOW + timedelta(hours=10)
    filtered_later, _ = filter_jobs_by_posted_date_with_metrics(jobs, "last_24_hours", NOW)
    assert len(filtered_t0) == len(filtered_later) == 1
    assert get_posted_at_utc(filtered_later[0]) == get_posted_at_utc(filtered_t0[0])
    # Frozen reference — using later clock without updating reference still stable when ref is fixed
    filtered_wrong_ref, _ = filter_jobs_by_posted_date_with_metrics(jobs, "last_24_hours", later)
    assert len(filtered_wrong_ref) == 1  # still frozen posted_at, same ref would be needed


def test_filter_then_pagination_count():
    jobs = [_mock_job("a", 2), _mock_job("b", 80), _mock_job("c", 200)]
    filtered, _ = filter_jobs_by_posted_date_with_metrics(jobs, "last_3_days", NOW)
    per_page = 10
    total_pages = max(1, (len(filtered) + per_page - 1) // per_page)
    assert len(filtered) == 1
    assert total_pages == 1


def test_widening_filter_detection_for_cached_scrape():
    assert is_filter_widening("last_24_hours", "any_time")
    assert not is_filter_widening("any_time", "last_24_hours")
