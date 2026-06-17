"""Regression tests for posted-date remediation (dashboard helpers)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

UTC = timezone.utc
NOW = datetime(2026, 6, 16, 12, 0, 0, tzinfo=UTC)


def _make_job(title: str, hours_ago: int):
    posted = NOW - timedelta(hours=hours_ago)
    return {
        "title": title,
        "company": "Co",
        "portal": "linkedin",
        "url": f"https://example.com/{title}",
        "posted_date_raw": f"{hours_ago}h ago",
        "posted_at_utc": posted.isoformat(),
    }


def _workflow_result(jobs, ranked_tuples, scrape_filter="last_24_hours"):
    return {
        "error": None,
        "jobs_found": jobs,
        "ranked_jobs": ranked_tuples,
        "workflow_reference_time_utc": NOW.isoformat(),
        "scrape_posted_date_filter": scrape_filter,
        "posted_date_metrics": {
            "total_jobs_scraped": len(jobs),
            "jobs_missing_posted_date": 0,
            "jobs_invalid_posted_date": 0,
            "jobs_filtered_by_date": 0,
            "jobs_remaining_after_filter": len(jobs),
        },
    }


@pytest.fixture
def dashboard_helpers():
    from dashboard import dashboard as dash

    return dash


class TestDashboardFilterHelpers:
    def test_build_ranked_rows_uses_posted_at_utc_not_raw(self, dashboard_helpers):
        job = _make_job("A", 2)
        rows = dashboard_helpers._build_ranked_rows([(job, {"final_score": 0.9})], NOW)
        assert rows[0]["posted_at"] == datetime.fromisoformat(job["posted_at_utc"])

    def test_apply_view_filters_stable_with_reference(self, dashboard_helpers):
        job = _make_job("A", 2)
        rows = dashboard_helpers._build_ranked_rows([(job, {"final_score": 0.9})], NOW)
        f1 = dashboard_helpers._apply_view_filters(
            rows,
            posted_date_filter="last_24_hours",
            reference_now=NOW,
            query="",
            portal_filter=[],
            min_score=0.0,
        )
        f2 = dashboard_helpers._apply_view_filters(
            rows,
            posted_date_filter="last_24_hours",
            reference_now=NOW,
            query="",
            portal_filter=[],
            min_score=0.0,
        )
        assert len(f1) == len(f2) == 1

    @patch("dashboard.dashboard.st")
    def test_compute_display_stats_uses_filtered_count(self, mock_st, dashboard_helpers):
        mock_st.session_state = MagicMock()
        mock_st.session_state.get = lambda k, d=None: {
            "posted_date_filter": "last_24_hours",
            "q": "",
            "portal_filter": [],
            "min_score": 0.0,
        }.get(k, d)

        fresh = _make_job("Fresh", 2)
        old = _make_job("Old", 200)
        result = _workflow_result([fresh, old], [(fresh, {"final_score": 0.9}), (old, {"final_score": 0.5})])
        stats = dashboard_helpers.compute_display_stats(result)
        assert stats["ranked_count"] == 1
        assert stats["discovered_count"] == 1

    def test_widening_scrape_vs_ui_filter(self, dashboard_helpers):
        from utils.job_posted_date import is_filter_widening

        assert is_filter_widening("last_24_hours", "last_3_days")
        assert is_filter_widening("last_3_days", "any_time")
