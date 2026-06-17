"""Unit tests for posted-date parsing and filtering."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from utils.job_posted_date import (
    FILTER_NARROWNESS_RANK,
    WIDENING_FILTER_WARNING,
    PostedDateFilterMetrics,
    build_scrape_metrics,
    filter_jobs_by_posted_date,
    filter_jobs_by_posted_date_with_metrics,
    freeze_posted_timestamp,
    get_filter_cutoff,
    get_posted_at_utc,
    is_filter_widening,
    job_within_posted_filter,
    parse_posted_date,
    portal_url_date_params,
)

UTC = timezone.utc


def _now() -> datetime:
    return datetime(2026, 6, 16, 12, 0, 0, tzinfo=UTC)


def _job(posted_date_raw=None, posted_at_utc=None):
    return {
        "title": "Engineer",
        "company": "Co",
        "posted_date_raw": posted_date_raw,
        "posted_at_utc": posted_at_utc,
    }


def _frozen_job(hours_ago: int, ref: datetime, raw: str = "2 hours ago"):
    posted = ref - timedelta(hours=hours_ago)
    return _job(posted_date_raw=raw, posted_at_utc=posted.isoformat())


class TestParsePostedDate:
    def test_relative_hours_with_reference(self):
        ref = _now()
        parsed = parse_posted_date("2 hours ago", reference_now=ref)
        assert parsed == ref - timedelta(hours=2)

    def test_iso_string(self):
        parsed = parse_posted_date("2026-06-10T08:00:00+00:00")
        assert parsed == datetime(2026, 6, 10, 8, 0, 0, tzinfo=UTC)

    def test_today(self):
        ref = _now()
        parsed = parse_posted_date("Today", reference_now=ref)
        assert parsed == ref.replace(hour=0, minute=0, second=0, microsecond=0)

    def test_yesterday(self):
        ref = _now()
        parsed = parse_posted_date("Yesterday", reference_now=ref)
        expected = (ref - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        assert parsed == expected

    def test_few_hours_ago(self):
        ref = _now()
        parsed = parse_posted_date("Few hours ago", reference_now=ref)
        assert parsed == ref - timedelta(hours=3)

    def test_human_date(self):
        parsed = parse_posted_date("Jun 10, 2026", reference_now=_now())
        assert parsed == datetime(2026, 6, 10, 0, 0, 0, tzinfo=UTC)

    def test_30_plus_days_ago(self):
        ref = _now()
        parsed = parse_posted_date("30+ days ago", reference_now=ref)
        assert parsed == ref - timedelta(days=30)

    def test_invalid_returns_none(self):
        assert parse_posted_date("not-a-date") is None

    def test_null_returns_none(self):
        assert parse_posted_date(None) is None


class TestFreezePostedTimestamp:
    def test_freezes_relative_at_reference(self):
        ref = _now()
        frozen = freeze_posted_timestamp("2 days ago", ref)
        assert frozen["posted_date_raw"] == "2 days ago"
        assert frozen["posted_at_utc"] == (ref - timedelta(days=2)).isoformat()

    def test_stability_does_not_change_when_clock_advances(self):
        ref = _now()
        frozen = freeze_posted_timestamp("2 days ago", ref)
        job = {"posted_date_raw": frozen["posted_date_raw"], "posted_at_utc": frozen["posted_at_utc"]}
        later = ref + timedelta(hours=5)
        assert get_posted_at_utc(job) == parse_posted_date("2 days ago", reference_now=ref)
        assert job_within_posted_filter(
            get_posted_at_utc(job), "last_3_days", reference_now=ref
        )
        assert job_within_posted_filter(
            get_posted_at_utc(job), "last_3_days", reference_now=later
        )


class TestBoundaryConditions:
    @pytest.fixture
    def now(self):
        return _now()

    def test_exactly_24_hours_in_24h(self, now):
        posted = now - timedelta(hours=24)
        assert job_within_posted_filter(posted, "last_24_hours", now) is True

    def test_25_hours_excluded_from_24h(self, now):
        posted = now - timedelta(hours=25)
        assert job_within_posted_filter(posted, "last_24_hours", now) is False

    def test_exactly_3_days_in_3_days(self, now):
        posted = now - timedelta(hours=72)
        assert job_within_posted_filter(posted, "last_3_days", now) is True

    def test_exactly_7_days_in_1_week(self, now):
        posted = now - timedelta(days=7)
        assert job_within_posted_filter(posted, "last_1_week", now) is True

    def test_null_excluded_when_filter_active(self, now):
        assert job_within_posted_filter(None, "last_24_hours", now) is False

    def test_future_date_excluded(self, now):
        posted = now + timedelta(hours=1)
        assert job_within_posted_filter(posted, "last_24_hours", now) is False

    def test_unknown_filter_fail_closed(self, now):
        posted = now - timedelta(hours=1)
        assert job_within_posted_filter(posted, "last_2_weeks", now) is False  # type: ignore[arg-type]


class TestFilterJobsByPostedDate:
    def test_uses_frozen_posted_at_utc_only(self):
        ref = _now()
        jobs = [
            _frozen_job(12, ref),
            _frozen_job(200, ref, raw="8 days ago"),
        ]
        kept = filter_jobs_by_posted_date(jobs, "last_24_hours", ref)
        assert len(kept) == 1

    def test_any_time_keeps_all_including_null(self):
        jobs = [_job(None, None), _job("x", _now().isoformat())]
        assert len(filter_jobs_by_posted_date(jobs, "any_time", _now())) == 2

    def test_metrics_counters(self):
        ref = _now()
        jobs = [
            _frozen_job(2, ref),
            _job(None, None),
            _job("bad", None),
            _frozen_job(200, ref, raw="old"),
        ]
        _, metrics = filter_jobs_by_posted_date_with_metrics(jobs, "last_24_hours", ref)
        assert metrics.total_jobs_scraped == 4
        assert metrics.jobs_missing_posted_date == 1
        assert metrics.jobs_invalid_posted_date == 1
        assert metrics.jobs_filtered_by_date == 1
        assert metrics.jobs_remaining_after_filter == 1


class TestWideningFilter:
    def test_widening_pairs(self):
      assert is_filter_widening("last_24_hours", "last_3_days")
      assert is_filter_widening("last_24_hours", "last_1_week")
      assert is_filter_widening("last_24_hours", "any_time")
      assert is_filter_widening("last_3_days", "last_1_week")
      assert is_filter_widening("last_3_days", "any_time")
      assert is_filter_widening("last_1_week", "any_time")

    def test_not_widening_when_narrowing(self):
      assert not is_filter_widening("any_time", "last_24_hours")
      assert not is_filter_widening("last_3_days", "last_24_hours")

    def test_warning_message_defined(self):
      assert "narrower date window" in WIDENING_FILTER_WARNING.lower()


class TestScrapeMetrics:
    def test_build_scrape_metrics(self):
        ref = _now()
        jobs = [_frozen_job(1, ref), _job("bad", None), _job(None, None)]
        metrics = build_scrape_metrics(jobs)
        assert metrics.total_jobs_scraped == 3
        assert metrics.jobs_invalid_posted_date == 1
        assert metrics.jobs_missing_posted_date == 1


class TestPortalUrlParams:
    def test_indeed_3_days(self):
        assert portal_url_date_params("indeed", "last_3_days") == {"fromage": "3"}

    def test_any_time_empty(self):
        assert portal_url_date_params("indeed", "any_time") == {}


class TestCutoff:
    def test_cutoff_24h(self):
        now = _now()
        cutoff = get_filter_cutoff("last_24_hours", now)
        assert cutoff == now - timedelta(hours=24)

    def test_filter_ranks_ordered(self):
        assert FILTER_NARROWNESS_RANK["last_24_hours"] < FILTER_NARROWNESS_RANK["any_time"]
