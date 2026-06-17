"""
Posted-date parsing and filtering for job listings.

All comparisons use UTC. Boundary is inclusive: a job posted exactly at
(now - window) is included in that window.

Jobs store frozen ``posted_at_utc`` at scrape time; filtering must use that
field only (never re-parse relative ``posted_date_raw`` strings).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

logger = logging.getLogger(__name__)

PostedDateFilter = Literal["any_time", "last_24_hours", "last_3_days", "last_1_week"]

POSTED_DATE_FILTER_LABELS: Dict[PostedDateFilter, str] = {
    "any_time": "Any Time",
    "last_24_hours": "Last 24 Hours",
    "last_3_days": "Last 3 Days",
    "last_1_week": "Last 1 Week",
}

POSTED_DATE_FILTER_OPTIONS: List[PostedDateFilter] = list(POSTED_DATE_FILTER_LABELS.keys())

# Lower rank = narrower window. Used for widening-filter detection.
FILTER_NARROWNESS_RANK: Dict[PostedDateFilter, int] = {
    "last_24_hours": 0,
    "last_3_days": 1,
    "last_1_week": 2,
    "any_time": 3,
}

# Window lengths — boundary-inclusive via posted_at >= cutoff
_FILTER_WINDOWS: Dict[PostedDateFilter, Optional[timedelta]] = {
    "any_time": None,
    "last_24_hours": timedelta(hours=24),
    "last_3_days": timedelta(hours=72),
    "last_1_week": timedelta(days=7),
}

# Portal URL query hints (best-effort; client-side filter still applied)
PORTAL_URL_DATE_PARAMS: Dict[str, Dict[PostedDateFilter, Dict[str, str]]] = {
    "indeed": {
        "last_24_hours": {"fromage": "1"},
        "last_3_days": {"fromage": "3"},
        "last_1_week": {"fromage": "7"},
    },
    "linkedin": {
        "last_24_hours": {"f_TPR": "r86400"},
        "last_1_week": {"f_TPR": "r604800"},
        # LinkedIn has no exact 3-day URL filter; client-side handles it
    },
}

_RELATIVE_RE = re.compile(
    r"(?P<num>\d+)\s*(?P<unit>second|minute|hour|day|week|month|year)s?\s+ago",
    re.IGNORECASE,
)
_JUST_NOW_RE = re.compile(r"just\s+now|moments?\s+ago", re.IGNORECASE)
_TODAY_RE = re.compile(r"^today$", re.IGNORECASE)
_YESTERDAY_RE = re.compile(r"^yesterday$", re.IGNORECASE)
_FEW_HOURS_RE = re.compile(
    r"(?P<qual>few|several|couple(?:\s+of)?)\s+hours?\s+ago",
    re.IGNORECASE,
)
_OLD_30_PLUS_RE = re.compile(r"30\+?\s*days?\s+ago", re.IGNORECASE)
_HUMAN_DATE_FORMATS = (
    "%b %d, %Y",
    "%B %d, %Y",
    "%d %b %Y",
    "%d %B %Y",
)

WIDENING_FILTER_WARNING = (
    "Results were originally fetched with a narrower date window. "
    "Re-run search to retrieve older jobs."
)


@dataclass
class PostedDateFilterMetrics:
    """Visibility counters for posted-date pipeline stages."""

    total_jobs_scraped: int = 0
    jobs_missing_posted_date: int = 0
    jobs_invalid_posted_date: int = 0
    jobs_filtered_by_date: int = 0
    jobs_remaining_after_filter: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "total_jobs_scraped": self.total_jobs_scraped,
            "jobs_missing_posted_date": self.jobs_missing_posted_date,
            "jobs_invalid_posted_date": self.jobs_invalid_posted_date,
            "jobs_filtered_by_date": self.jobs_filtered_by_date,
            "jobs_remaining_after_filter": self.jobs_remaining_after_filter,
        }

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> PostedDateFilterMetrics:
        if not data:
            return cls()
        return cls(
            total_jobs_scraped=int(data.get("total_jobs_scraped", 0)),
            jobs_missing_posted_date=int(data.get("jobs_missing_posted_date", 0)),
            jobs_invalid_posted_date=int(data.get("jobs_invalid_posted_date", 0)),
            jobs_filtered_by_date=int(data.get("jobs_filtered_by_date", 0)),
            jobs_remaining_after_filter=int(data.get("jobs_remaining_after_filter", 0)),
        )


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_reference_iso(iso_value: Optional[str]) -> Optional[datetime]:
    """Parse workflow_reference_time_utc ISO string to aware UTC datetime."""
    if not iso_value:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(str(iso_value).replace("Z", "+00:00")))
    except ValueError:
        logger.warning("Invalid workflow_reference_time_utc: %r", iso_value)
        return None


def is_filter_widening(
    from_filter: PostedDateFilter,
    to_filter: PostedDateFilter,
) -> bool:
    """Return True when ``to_filter`` includes a broader date window than ``from_filter``."""
    return FILTER_NARROWNESS_RANK[to_filter] > FILTER_NARROWNESS_RANK[from_filter]


def is_valid_posted_date_filter(value: str) -> bool:
    return value in POSTED_DATE_FILTER_LABELS


def parse_posted_date(
    value: Union[str, datetime, None],
    reference_now: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    Parse a job posted_date into UTC datetime.

    Supports ISO strings, datetime objects, relative strings, Today/Yesterday,
    human-readable dates, and portal phrases like "Few hours ago".
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return _ensure_utc(value)

    raw = str(value).strip()
    if not raw:
        return None

    now = _ensure_utc(reference_now or datetime.now(timezone.utc))

    if _JUST_NOW_RE.search(raw):
        return now

    if _TODAY_RE.match(raw):
        return now.replace(hour=0, minute=0, second=0, microsecond=0)

    if _YESTERDAY_RE.match(raw):
        return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

    few_hours = _FEW_HOURS_RE.search(raw)
    if few_hours:
        qual = few_hours.group("qual").lower()
        hours = 2 if "couple" in qual else 3
        return now - timedelta(hours=hours)

    if _OLD_30_PLUS_RE.search(raw):
        return now - timedelta(days=30)

    rel = _RELATIVE_RE.search(raw)
    if rel:
        num = int(rel.group("num"))
        unit = rel.group("unit").lower()
        delta_kwargs = {
            "second": {"seconds": num},
            "minute": {"minutes": num},
            "hour": {"hours": num},
            "day": {"days": num},
            "week": {"weeks": num},
            "month": {"days": num * 30},
            "year": {"days": num * 365},
        }.get(unit)
        if delta_kwargs:
            return now - timedelta(**delta_kwargs)

    # ISO / common date formats
    normalized = raw.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        *_HUMAN_DATE_FORMATS,
    ):
        try:
            parsed = datetime.strptime(normalized[:40], fmt)
            return _ensure_utc(parsed)
        except ValueError:
            continue

    try:
        return _ensure_utc(datetime.fromisoformat(normalized))
    except ValueError:
        logger.debug("Could not parse posted_date: %r", raw)
        return None


def freeze_posted_timestamp(
    raw: Union[str, datetime, None],
    reference_now: datetime,
) -> Dict[str, Optional[str]]:
    """
    Freeze a raw portal date string to absolute UTC at scrape time.

    Returns:
        posted_date_raw: original text (or ISO if input was datetime)
        posted_at_utc: ISO-8601 UTC string, or None if unparseable
    """
    ref = _ensure_utc(reference_now)
    if raw is None:
        return {"posted_date_raw": None, "posted_at_utc": None}
    if isinstance(raw, datetime):
        raw_str: Optional[str] = _ensure_utc(raw).isoformat()
    else:
        raw_str = str(raw).strip() or None

    parsed = parse_posted_date(raw, reference_now=ref)
    return {
        "posted_date_raw": raw_str,
        "posted_at_utc": parsed.isoformat() if parsed else None,
    }


def get_posted_at_utc(job: Dict[str, Any]) -> Optional[datetime]:
    """Read frozen posted_at_utc from a job dict. Never re-parses relative raw text."""
    iso = job.get("posted_at_utc")
    if not iso:
        return None
    try:
        return _ensure_utc(datetime.fromisoformat(str(iso).replace("Z", "+00:00")))
    except ValueError:
        logger.debug("Invalid posted_at_utc on job: %r", iso)
        return None


def build_scrape_metrics(jobs: List[Dict[str, Any]]) -> PostedDateFilterMetrics:
    """Metrics after scrape + freeze, before date filtering."""
    missing = 0
    invalid = 0
    for job in jobs:
        raw = job.get("posted_date_raw")
        utc = job.get("posted_at_utc")
        if not utc:
            if raw:
                invalid += 1
            else:
                missing += 1
    return PostedDateFilterMetrics(
        total_jobs_scraped=len(jobs),
        jobs_missing_posted_date=missing,
        jobs_invalid_posted_date=invalid,
        jobs_filtered_by_date=0,
        jobs_remaining_after_filter=len(jobs),
    )


def get_filter_cutoff(
    posted_date_filter: PostedDateFilter,
    reference_now: Optional[datetime] = None,
) -> Optional[datetime]:
    """Return UTC cutoff datetime for filter, or None for any_time / unknown."""
    if posted_date_filter not in _FILTER_WINDOWS:
        return None
    window = _FILTER_WINDOWS.get(posted_date_filter)
    if window is None:
        return None
    now = _ensure_utc(reference_now or datetime.now(timezone.utc))
    return now - window


def job_within_posted_filter(
    posted_at: Optional[datetime],
    posted_date_filter: PostedDateFilter,
    reference_now: Optional[datetime] = None,
) -> bool:
    """
    Return True if job should be included for the given filter.

    Boundary-inclusive: posted_at == cutoff is included.
    Null/invalid/future dates are excluded when filter is active.
    """
    if posted_date_filter == "any_time":
        return True
    if posted_at is None:
        return False

    posted_at = _ensure_utc(posted_at)
    now = _ensure_utc(reference_now or datetime.now(timezone.utc))

    if posted_at > now:
        logger.warning("Excluding future-dated job: posted_at=%s", posted_at.isoformat())
        return False

    cutoff = get_filter_cutoff(posted_date_filter, reference_now=now)
    if cutoff is None:
        # Unknown filter value — fail closed when a restrictive filter was requested
        if posted_date_filter != "any_time":
            logger.warning("Unknown posted_date_filter %r; excluding job", posted_date_filter)
            return False
        return True
    return posted_at >= cutoff


def filter_jobs_by_posted_date(
    jobs: List[Dict[str, Any]],
    posted_date_filter: PostedDateFilter,
    reference_now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Filter job dicts using frozen ``posted_at_utc`` only."""
    filtered, _metrics = filter_jobs_by_posted_date_with_metrics(
        jobs, posted_date_filter, reference_now=reference_now
    )
    return filtered


def filter_jobs_by_posted_date_with_metrics(
    jobs: List[Dict[str, Any]],
    posted_date_filter: PostedDateFilter,
    reference_now: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], PostedDateFilterMetrics]:
    """Filter jobs by frozen UTC timestamps and return visibility metrics."""
    scrape_metrics = build_scrape_metrics(jobs)
    if posted_date_filter == "any_time":
        return list(jobs), scrape_metrics

    now = _ensure_utc(reference_now or datetime.now(timezone.utc))
    kept: List[Dict[str, Any]] = []
    skipped_null = scrape_metrics.jobs_missing_posted_date
    skipped_invalid = scrape_metrics.jobs_invalid_posted_date
    skipped_old = 0

    for job in jobs:
        posted_at = get_posted_at_utc(job)
        if posted_at is None:
            continue
        if job_within_posted_filter(posted_at, posted_date_filter, reference_now=now):
            kept.append(job)
        else:
            skipped_old += 1

    metrics = PostedDateFilterMetrics(
        total_jobs_scraped=len(jobs),
        jobs_missing_posted_date=skipped_null,
        jobs_invalid_posted_date=skipped_invalid,
        jobs_filtered_by_date=skipped_old,
        jobs_remaining_after_filter=len(kept),
    )
    logger.info(
        "Posted-date filter %s @ %s: kept %d, filtered=%d, missing=%d, invalid=%d (of %d)",
        posted_date_filter,
        now.isoformat(),
        metrics.jobs_remaining_after_filter,
        metrics.jobs_filtered_by_date,
        metrics.jobs_missing_posted_date,
        metrics.jobs_invalid_posted_date,
        metrics.total_jobs_scraped,
    )
    return kept, metrics


def portal_url_date_params(
    portal: str,
    posted_date_filter: PostedDateFilter,
) -> Dict[str, str]:
    """Return URL query params for portal-native date filtering when supported."""
    if posted_date_filter == "any_time":
        return {}
    portal_key = (portal or "").lower()
    return dict(PORTAL_URL_DATE_PARAMS.get(portal_key, {}).get(posted_date_filter, {}))
