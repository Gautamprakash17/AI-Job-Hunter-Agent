"""
Streamlit dashboard for AI Job Hunter Agent.

Job discovery and ranking assistant: discover jobs, view ranked results,
and open job links to apply on the portal.
"""

import logging
import sys
import csv
import io
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from database.db import init_db
from workflows.job_agent_graph import run_job_hunter_workflow
from agents.resume_parser_agent import ResumeParserAgent, parse_resume
from agents.job_discovery_agent import discover_jobs
from agents.job_ranking_agent import rank_jobs_with_details
from utils.job_posted_date import (
    POSTED_DATE_FILTER_LABELS,
    POSTED_DATE_FILTER_OPTIONS,
    PostedDateFilter,
    PostedDateFilterMetrics,
    WIDENING_FILTER_WARNING,
    filter_jobs_by_posted_date_with_metrics,
    get_posted_at_utc,
    is_filter_widening,
    job_within_posted_filter,
    parse_reference_iso,
)

logger = logging.getLogger(__name__)

LOGO_PATH = project_root / "data" / "logo" / "ScriptNeuronLogo.png"

PORTAL_STYLES = {
    "linkedin": ("LinkedIn", "#0A66C2"),
    "indeed": ("Indeed", "#2164F3"),
    "naukri": ("Naukri", "#4A90D9"),
    "demo": ("Demo", "#888888"),
}

DEFAULT_PAGE_SIZE = 10


def _reset_result_pages() -> None:
    """Reset pagination when filters change."""
    for key in list(st.session_state.keys()):
        if key.startswith("page_"):
            st.session_state[key] = 1


def _sync_posted_date_filter_state(current: PostedDateFilter) -> None:
    """Reset pagination when posted-date filter changes."""
    prev = st.session_state.get("_prev_posted_date_filter", "any_time")
    if current != prev:
        st.session_state["_prev_posted_date_filter"] = current
        _reset_result_pages()


def _workflow_reference(result: Optional[dict]):
    """Return frozen workflow reference time from a workflow result."""
    if not result:
        return None
    return parse_reference_iso(result.get("workflow_reference_time_utc"))


def _build_ranked_rows(ranked: List[Any], reference_now) -> List[Dict[str, Any]]:
    """Normalize ranked tuples into rows using frozen posted_at_utc only."""
    rows: List[Dict[str, Any]] = []
    for ranked_item in ranked:
        job, score_info = (
            ranked_item
            if isinstance(ranked_item, tuple) and len(ranked_item) == 2
            else (ranked_item, {})
        )
        if isinstance(score_info, dict):
            final_score = float(score_info.get("final_score", score_info.get("score", 0)) or 0.0)
        else:
            final_score = float(score_info) if isinstance(score_info, (int, float)) else 0.0
        rows.append(
            {
                "job": job,
                "score_info": score_info if isinstance(score_info, dict) else {},
                "final_score": final_score,
                "portal": (job.get("portal") or "").lower(),
                "title": (job.get("title") or ""),
                "company": (job.get("company") or ""),
                "location": (job.get("location") or ""),
                "url": (job.get("url") or ""),
                "job_id": _job_key(job),
                "posted_date_raw": job.get("posted_date_raw"),
                "posted_at": get_posted_at_utc(job),
            }
        )
    return rows


def _apply_view_filters(
    rows: List[Dict[str, Any]],
    *,
    posted_date_filter: PostedDateFilter,
    reference_now,
    query: str,
    portal_filter: List[str],
    min_score: float,
) -> List[Dict[str, Any]]:
    """Apply UI filters; posted-date uses frozen timestamps + workflow reference."""
    q = (query or "").strip().lower()
    filtered: List[Dict[str, Any]] = []
    for r in rows:
        if r["final_score"] < float(min_score):
            continue
        if portal_filter and r["portal"] not in set(portal_filter):
            continue
        if q and (q not in (r["title"] or "").lower()) and (q not in (r["company"] or "").lower()):
            continue
        if not job_within_posted_filter(
            r.get("posted_at"), posted_date_filter, reference_now=reference_now
        ):
            continue
        filtered.append(r)
    return filtered


def compute_display_stats(result: Dict[str, Any]) -> Dict[str, Any]:
    """Compute hero stats from workflow result + current sidebar/result filters."""
    ref = _workflow_reference(result)
    posted_date_filter: PostedDateFilter = st.session_state.get("posted_date_filter", "any_time")
    rows = _build_ranked_rows(result.get("ranked_jobs", []), ref)
    filtered = _apply_view_filters(
        rows,
        posted_date_filter=posted_date_filter,
        reference_now=ref,
        query=st.session_state.get("q", ""),
        portal_filter=st.session_state.get("portal_filter", []),
        min_score=float(st.session_state.get("min_score", 0.0)),
    )

    jobs_found = result.get("jobs_found", [])
    if posted_date_filter != "any_time" and ref is not None:
        discovered_count = sum(
            1
            for j in jobs_found
            if job_within_posted_filter(get_posted_at_utc(j), posted_date_filter, reference_now=ref)
        )
    else:
        discovered_count = len(jobs_found)

    top_score_str = "—"
    if filtered:
        top_score_str = f"{filtered[0]['final_score']:.0%}"

    portal_set: set = set()
    for r in filtered:
        p = (r.get("portal") or "").strip()
        if p:
            portal_set.add(p.capitalize())
    portals_str = ", ".join(sorted(portal_set)) if portal_set else "—"

    return {
        "ranked_count": len(filtered),
        "discovered_count": discovered_count,
        "top_score_str": top_score_str,
        "portals_str": portals_str,
    }


def _render_posted_date_debug_panel(result: Dict[str, Any], ui_metrics: PostedDateFilterMetrics) -> None:
    """Debug expander for posted-date pipeline metrics."""
    scrape_metrics = PostedDateFilterMetrics.from_dict(result.get("posted_date_metrics"))
    ref = result.get("workflow_reference_time_utc", "—")
    scrape_filter = result.get("scrape_posted_date_filter", "any_time")
    with st.expander("Posted date debug metrics", expanded=False):
        st.caption(f"Workflow reference (UTC): `{ref}`")
        st.caption(f"Scrape filter: `{scrape_filter}`")
        st.markdown("**At scrape**")
        st.json(scrape_metrics.to_dict())
        st.markdown("**Current UI filter**")
        st.json(ui_metrics.to_dict())


def inject_custom_css() -> None:
    """Apply ScriptNeuron-themed styling to the Streamlit app."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        :root {
            --sn-orange: #ff6b35;
            --sn-pink: #f72585;
            --sn-purple: #7209b7;
            --sn-bg: #0d0d12;
            --sn-surface: #16161f;
            --sn-surface-2: #1e1e2a;
            --sn-border: rgba(255, 255, 255, 0.08);
            --sn-text: #f0f0f5;
            --sn-muted: #9ca3af;
        }

        .stApp {
            background: linear-gradient(160deg, #0d0d12 0%, #12121a 40%, #0f0f16 100%);
            font-family: 'Inter', sans-serif;
        }

        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #12121a 0%, #0d0d12 100%);
            border-right: 1px solid var(--sn-border);
        }

        [data-testid="stSidebar"] .stMarkdown h1,
        [data-testid="stSidebar"] .stMarkdown h2,
        [data-testid="stSidebar"] .stMarkdown h3 {
            color: var(--sn-text) !important;
            font-weight: 600;
        }

        /* Keep Streamlit header visible so sidebar toggle works */
        #MainMenu, footer { visibility: hidden; }

        .hero-wrap {
            background: linear-gradient(135deg, rgba(255,107,53,0.12) 0%, rgba(114,9,183,0.12) 100%);
            border: 1px solid var(--sn-border);
            border-radius: 20px;
            padding: 2rem 2.5rem;
            margin-bottom: 1.5rem;
            position: relative;
            overflow: hidden;
        }
        .hero-wrap::before {
            content: '';
            position: absolute;
            top: -50%;
            right: -10%;
            width: 300px;
            height: 300px;
            background: radial-gradient(circle, rgba(255,107,53,0.15) 0%, transparent 70%);
            pointer-events: none;
        }
        .hero-title {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(90deg, #fff 0%, #ffb088 50%, #c77dff 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin: 0 0 0.5rem 0;
            line-height: 1.2;
        }
        .hero-sub {
            color: var(--sn-muted);
            font-size: 1.05rem;
            margin: 0;
            max-width: 640px;
            line-height: 1.6;
        }
        .hero-badge {
            display: inline-block;
            background: rgba(255,107,53,0.15);
            color: #ffb088;
            border: 1px solid rgba(255,107,53,0.3);
            border-radius: 999px;
            padding: 0.25rem 0.85rem;
            font-size: 0.75rem;
            font-weight: 600;
            letter-spacing: 0.04em;
            text-transform: uppercase;
            margin-bottom: 0.75rem;
        }

        .stat-card {
            background: var(--sn-surface);
            border: 1px solid var(--sn-border);
            border-radius: 14px;
            padding: 1.25rem 1.5rem;
            text-align: center;
        }
        .stat-value {
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(90deg, var(--sn-orange), var(--sn-pink));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .stat-label {
            color: var(--sn-muted);
            font-size: 0.8rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-top: 0.25rem;
        }

        .job-card {
            background: var(--sn-surface);
            border: 1px solid var(--sn-border);
            border-radius: 16px;
            padding: 1.25rem 1.5rem;
            margin-bottom: 0.85rem;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .job-card:hover {
            border-color: rgba(255,107,53,0.35);
            box-shadow: 0 4px 24px rgba(255,107,53,0.08);
        }
        .job-rank {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 8px;
            background: linear-gradient(135deg, var(--sn-orange), var(--sn-purple));
            color: white;
            font-size: 0.75rem;
            font-weight: 700;
            margin-right: 0.6rem;
            flex-shrink: 0;
        }
        .job-title {
            color: var(--sn-text);
            font-size: 1.05rem;
            font-weight: 600;
            margin: 0;
        }
        .job-company {
            color: var(--sn-muted);
            font-size: 0.9rem;
            margin: 0.15rem 0 0 0;
        }
        .portal-badge {
            display: inline-block;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.7rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            text-transform: uppercase;
            margin-right: 0.4rem;
        }
        .score-pill {
            display: inline-block;
            padding: 0.35rem 0.85rem;
            border-radius: 999px;
            font-size: 0.85rem;
            font-weight: 700;
            background: linear-gradient(135deg, rgba(255,107,53,0.2), rgba(114,9,183,0.2));
            border: 1px solid rgba(255,107,53,0.3);
            color: #ffb088;
        }
        .score-bar-wrap {
            background: rgba(255,255,255,0.06);
            border-radius: 999px;
            height: 6px;
            margin-top: 0.5rem;
            overflow: hidden;
        }
        .score-bar-fill {
            height: 100%;
            border-radius: 999px;
            background: linear-gradient(90deg, var(--sn-orange), var(--sn-pink), var(--sn-purple));
        }
        .meta-chip {
            display: inline-block;
            background: var(--sn-surface-2);
            border: 1px solid var(--sn-border);
            border-radius: 8px;
            padding: 0.2rem 0.6rem;
            font-size: 0.78rem;
            color: var(--sn-muted);
            margin-right: 0.35rem;
            margin-top: 0.35rem;
        }
        .section-title {
            color: var(--sn-text);
            font-size: 1.1rem;
            font-weight: 600;
            margin: 1.5rem 0 1rem 0;
            padding-bottom: 0.5rem;
            border-bottom: 1px solid var(--sn-border);
        }
        .empty-state {
            text-align: center;
            padding: 3rem 2rem;
            background: var(--sn-surface);
            border: 1px dashed var(--sn-border);
            border-radius: 16px;
            color: var(--sn-muted);
        }
        .empty-state-icon { font-size: 2.5rem; margin-bottom: 0.75rem; }
        .step-card {
            background: var(--sn-surface);
            border: 1px solid var(--sn-border);
            border-radius: 12px;
            padding: 1rem;
            text-align: center;
            height: 100%;
        }
        .step-num {
            display: inline-flex;
            width: 32px; height: 32px;
            align-items: center; justify-content: center;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--sn-orange), var(--sn-purple));
            color: white;
            font-weight: 700;
            font-size: 0.85rem;
            margin-bottom: 0.5rem;
        }
        .step-label { color: var(--sn-text); font-weight: 600; font-size: 0.9rem; }
        .step-desc { color: var(--sn-muted); font-size: 0.78rem; margin-top: 0.25rem; }

        div[data-testid="stMetric"] {
            background: var(--sn-surface-2);
            border: 1px solid var(--sn-border);
            border-radius: 12px;
            padding: 0.75rem 1rem;
        }
        div[data-testid="stMetric"] label { color: var(--sn-muted) !important; }
        div[data-testid="stMetric"] [data-testid="stMetricValue"] {
            color: var(--sn-text) !important;
        }

        .sidebar-section {
            color: var(--sn-muted);
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 1rem 0 0.4rem 0;
        }

        .controls-wrap {
            background: var(--sn-surface);
            border: 1px solid var(--sn-border);
            border-radius: 16px;
            padding: 1rem 1.25rem;
            margin-bottom: 1rem;
        }

        /* ── Hero card ── */
        .hero-card {
            position: relative;
            background: linear-gradient(135deg,
                rgba(255,107,53,0.08) 0%,
                rgba(13,13,18,0.97)  45%,
                rgba(114,9,183,0.08) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 20px;
            padding: 1.75rem 2.25rem 1.6rem 2.25rem;
            overflow: hidden;
            margin-bottom: 0;
        }
        .hero-card::before {
            content: '';
            position: absolute;
            top: -80px; left: -80px;
            width: 260px; height: 260px;
            background: radial-gradient(circle, rgba(255,107,53,0.14) 0%, transparent 70%);
            pointer-events: none;
        }
        .hero-card::after {
            content: '';
            position: absolute;
            bottom: -60px; right: -50px;
            width: 240px; height: 240px;
            background: radial-gradient(circle, rgba(114,9,183,0.14) 0%, transparent 70%);
            pointer-events: none;
        }
        /* brand eyebrow */
        .hero-eyebrow {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.65rem;
        }
        .hero-brand-dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: var(--sn-orange);
            flex-shrink: 0;
        }
        .hero-brand-text {
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: var(--sn-orange);
        }
        /* title */
        .hero-title-main {
            font-size: 1.65rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1.2;
            margin: 0 0 0.6rem 0;
            background: linear-gradient(100deg,
                #ffffff 0%,
                rgba(255,255,255,0.88) 60%,
                rgba(199,125,255,0.9) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        /* subtitle */
        .hero-subtitle {
            font-size: 0.875rem;
            color: rgba(156,163,175,0.9);
            line-height: 1.7;
            margin: 0 0 1.3rem 0;
            max-width: 700px;
        }
        /* workflow pills */
        .hero-workflow {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0;
            margin-bottom: 1.25rem;
        }
        .wf-pill {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 10px;
            padding: 0.38rem 0.85rem;
            font-size: 0.78rem;
            font-weight: 600;
            color: rgba(240,240,245,0.85);
            white-space: nowrap;
            transition: background 0.2s;
        }
        .wf-pill:hover {
            background: rgba(255,107,53,0.10);
            border-color: rgba(255,107,53,0.28);
            color: #ffb088;
        }
        .wf-arrow {
            padding: 0 0.45rem;
            color: rgba(255,255,255,0.18);
            font-size: 1rem;
            flex-shrink: 0;
        }
        /* trust line */
        .hero-trust {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255,255,255,0.05);
        }
        .trust-item {
            display: inline-flex;
            align-items: center;
            gap: 0.35rem;
            font-size: 0.75rem;
            font-weight: 500;
            color: rgba(156,163,175,0.75);
        }
        .trust-check {
            color: #4ade80;
            font-size: 0.7rem;
            font-weight: 700;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_hero(
    result: Optional[dict] = None,
    display_stats: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Premium SaaS hero: logo (st.image) + hero card + stats row.
    No base64 in HTML. No tech-stack badges (focus on business value).
    """
    # ── Live stats ──────────────────────────────────────────────────
    ranked_count = 0
    discovered_count = 0
    top_score_str = "—"
    portals_str = "—"
    if result and not result.get("error"):
        if display_stats:
            ranked_count = display_stats.get("ranked_count", 0)
            discovered_count = display_stats.get("discovered_count", 0)
            top_score_str = display_stats.get("top_score_str", "—")
            portals_str = display_stats.get("portals_str", "—")
        else:
            ranked = result.get("ranked_jobs", [])
            discovered_count = len(result.get("jobs_found", []))
            ranked_count = len(ranked)
            top_score_str = "—"
            portals_str = "—"
            if ranked:
                first = ranked[0]
                si = first[1] if isinstance(first, tuple) else {}
                s = si.get("final_score", 0) if isinstance(si, dict) else 0
                top_score_str = f"{s:.0%}"
            portal_set: set = set()
            for item in ranked:
                j = item[0] if isinstance(item, tuple) else item
                p = (j.get("portal") or "").strip()
                if p:
                    portal_set.add(p.capitalize())
            portals_str = ", ".join(sorted(portal_set)) if portal_set else "—"

    # Logo as base64 for inline use inside st.html (small, ~30px height)
    import base64
    logo_img_tag = ""
    if LOGO_PATH.exists():
        b64 = base64.b64encode(LOGO_PATH.read_bytes()).decode()
        logo_img_tag = (
            f'<img src="data:image/png;base64,{b64}" '
            f'style="height:30px;width:auto;object-fit:contain;vertical-align:middle;" '
            f'alt="ScriptNeuron"/>'
        )

    st.html(f"""
<style>
.sn-hero{{
  position:relative;
  background:linear-gradient(135deg,rgba(255,107,53,.09) 0%,rgba(13,13,18,.97) 45%,rgba(114,9,183,.09) 100%);
  border:1px solid rgba(255,255,255,.08);
  border-radius:20px;
  padding:1.75rem 2.25rem 1.6rem 2.25rem;
  overflow:hidden;
  font-family:'Inter',system-ui,sans-serif;
}}
.sn-hero::before{{
  content:'';position:absolute;top:-80px;left:-80px;
  width:260px;height:260px;
  background:radial-gradient(circle,rgba(255,107,53,.15) 0%,transparent 70%);
  pointer-events:none;
}}
.sn-hero::after{{
  content:'';position:absolute;bottom:-60px;right:-50px;
  width:240px;height:240px;
  background:radial-gradient(circle,rgba(114,9,183,.15) 0%,transparent 70%);
  pointer-events:none;
}}
.sn-eyebrow{{display:flex;align-items:center;gap:.6rem;margin-bottom:.75rem;}}
.sn-divider{{width:1px;height:22px;background:rgba(255,255,255,.15);flex-shrink:0;}}
.sn-brand{{font-size:.68rem;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:#ff6b35;}}
.sn-title{{
  font-size:1.65rem;font-weight:700;letter-spacing:-.03em;line-height:1.2;
  margin:0 0 .6rem 0;
  background:linear-gradient(100deg,#fff 0%,rgba(255,255,255,.88) 55%,rgba(199,125,255,.9) 100%);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
}}
.sn-sub{{font-size:.9rem;color:rgba(156,163,175,.9);line-height:1.7;margin:0;max-width:700px;}}
</style>
<div class="sn-hero">
  <div class="sn-eyebrow">
    {logo_img_tag}
    <div class="sn-divider"></div>
    <span class="sn-brand">ScriptNeuron &middot; AI Agent Platform</span>
  </div>
  <p class="sn-title">AI Job Discovery &amp; Ranking Platform</p>
  <p class="sn-sub">
    Discover, analyze, and rank relevant jobs from multiple job portals using AI-powered resume analysis.
  </p>
</div>
    """)

    # ── Stats row (always visible, updates after run) ───────────────
    st.markdown("<div style='height:0.9rem'></div>", unsafe_allow_html=True)
    s1, s2, s3, s4 = st.columns(4)

    def _stat(col: Any, value: str, label: str) -> None:
        col.markdown(
            f'<div class="stat-card">'
            f'<div class="stat-value">{value}</div>'
            f'<div class="stat-label">{label}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    _stat(s1, str(ranked_count),     "Jobs Ranked")
    _stat(s2, str(discovered_count), "Jobs Discovered")
    _stat(s3, top_score_str,         "Top Match Score")
    _stat(s4, portals_str,           "Portals Searched")
    st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)


def render_how_it_works() -> None:
    """Show quick steps when no results yet."""
    st.markdown('<p class="section-title">How it works</p>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    steps = [
        ("1", "Upload Resume", "PDF or TXT from sidebar"),
        ("2", "Set Filters", "Role, location & experience"),
        ("3", "Discover & Rank", "AI scrapes & scores jobs"),
        ("4", "Apply", "Open job on the portal"),
    ]
    for col, (num, label, desc) in zip([c1, c2, c3, c4], steps):
        with col:
            st.markdown(
                f"""
                <div class="step-card">
                    <div class="step-num">{num}</div>
                    <div class="step-label">{label}</div>
                    <div class="step-desc">{desc}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def portal_badge_html(portal: str) -> str:
    """Return HTML for a colored portal badge."""
    key = (portal or "unknown").lower()
    label, color = PORTAL_STYLES.get(key, (portal or "Unknown", "#666"))
    return (
        f'<span class="portal-badge" style="background:{color}22;color:{color};'
        f'border:1px solid {color}44;">{label}</span>'
    )


def score_color(score: float) -> str:
    """Return accent color based on match score."""
    if score >= 0.75:
        return "#4ade80"
    if score >= 0.5:
        return "#ffb088"
    return "#9ca3af"

def _job_key(job: Dict[str, Any]) -> str:
    """Stable key for shortlist/dedup: prefer URL, else title+company."""
    url = (job.get("url") or "").strip()
    if url:
        return url
    title = (job.get("title") or "").strip()
    company = (job.get("company") or "").strip()
    return f"{title}|{company}".strip("|") or "unknown"


def _to_csv_bytes(rows: List[Dict[str, Any]]) -> bytes:
    """Convert rows to CSV bytes for download."""
    buf = io.StringIO()
    fieldnames = ["title", "company", "portal", "location", "final_score", "url"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow({k: r.get(k, "") for k in fieldnames})
    return buf.getvalue().encode("utf-8")


def render_job_card(
    rank: int,
    job: Dict[str, Any],
    score_info: Dict[str, Any],
    final_score: float,
) -> None:
    """Render a single ranked job as a styled card with expander details."""
    title = job.get("title", "N/A")
    company = job.get("company", "N/A")
    portal = job.get("portal", "N/A")
    loc = job.get("location", "N/A") or "Not specified"
    url = job.get("url") or ""
    pct = min(int(final_score * 100), 100)
    accent = score_color(final_score)

    header_html = f"""
    <div class="job-card">
        <table style="width:100%;border:none;border-collapse:collapse;">
        <tr>
            <td style="width:70%;vertical-align:top;border:none;padding:0;">
                <span class="job-rank">{rank}</span>
                <span class="job-title">{title}</span>
                <p class="job-company">{company}</p>
                <div style="margin-top:0.5rem;">
                    {portal_badge_html(portal)}
                    <span class="meta-chip">📍 {loc}</span>
                </div>
            </td>
            <td style="width:30%;text-align:right;vertical-align:top;border:none;padding:0;">
                <span class="score-pill" style="color:{accent};border-color:{accent}44;">
                    {final_score:.0%}
                </span>
                <div class="score-bar-wrap"><div class="score-bar-fill" style="width:{pct}%;"></div></div>
            </td>
        </tr>
        </table>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    job_id = _job_key(job)
    shortlist: set = st.session_state.setdefault("shortlist", set())

    with st.expander("View details & apply", expanded=False):
        a1, a2, a3 = st.columns([1, 1, 2])
        with a1:
            if job_id in shortlist:
                if st.button("★ Shortlisted", key=f"unsave_{rank}_{job_id}", use_container_width=True):
                    shortlist.discard(job_id)
                    st.rerun()
            else:
                if st.button("☆ Shortlist", key=f"save_{rank}_{job_id}", use_container_width=True):
                    shortlist.add(job_id)
                    st.rerun()
        with a2:
            if url:
                st.link_button("Open Job", url, type="primary", use_container_width=True)
        with a3:
            st.caption("Tip: Shortlist jobs first, then export CSV from controls.")

        if isinstance(score_info, dict) and any(
            k in score_info for k in ("embedding_score", "title_match")
        ):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Final Score", f"{score_info.get('final_score', final_score):.2f}")
            with c2:
                st.metric("Embedding Similarity", f"{score_info.get('embedding_score', 0):.2f}")
            with c3:
                st.metric("Title Match", score_info.get("title_match", 0))

        if job.get("description"):
            st.markdown("**Description**")
            desc = job["description"]
            st.markdown(desc[:600] + ("..." if len(desc) > 600 else ""))


def render_results(result: Dict[str, Any]) -> None:
    """Render ranked job list (stats are shown in hero card)."""
    ranked = result.get("ranked_jobs", [])
    ref = _workflow_reference(result)

    st.markdown('<p class="section-title">Ranked Jobs</p>', unsafe_allow_html=True)

    posted_date_filter: PostedDateFilter = st.session_state.get("posted_date_filter", "any_time")
    _sync_posted_date_filter_state(posted_date_filter)

    scrape_filter: PostedDateFilter = result.get("scrape_posted_date_filter", "any_time")
    if is_filter_widening(scrape_filter, posted_date_filter):
        st.warning(WIDENING_FILTER_WARNING)

    st.markdown('<div class="controls-wrap">', unsafe_allow_html=True)
    if posted_date_filter != "any_time":
        active_label = POSTED_DATE_FILTER_LABELS[posted_date_filter]
        st.markdown(
            f'<span class="portal-badge" style="background:rgba(255,107,53,0.15);'
            f'color:#ffb088;border:1px solid rgba(255,107,53,0.35);">'
            f'Posted: {active_label}</span>',
            unsafe_allow_html=True,
        )
    cc1, cc2, cc3, cc4, cc5 = st.columns([2.2, 1.4, 1.3, 1.5, 1.2])
    with cc1:
        query = st.text_input(
            "Search (title/company)",
            value=st.session_state.get("q", ""),
            placeholder="e.g. LLM, Data Engineer, Wipro",
            label_visibility="collapsed",
            key="q",
        )
    with cc2:
        portal_filter = st.multiselect(
            "Portals",
            options=["linkedin", "indeed", "naukri", "demo"],
            default=st.session_state.get("portal_filter", []),
            format_func=lambda p: PORTAL_STYLES.get(p, (p, ""))[0],
            key="portal_filter",
        )
    with cc3:
        min_score = st.slider(
            "Min score",
            min_value=0.0,
            max_value=1.0,
            value=float(st.session_state.get("min_score", 0.0)),
            step=0.05,
            key="min_score",
        )
    with cc4:
        sort_mode = st.selectbox(
            "Sort",
            options=["Best match", "Lowest match", "Company A→Z", "Title A→Z"],
            index=int(st.session_state.get("sort_mode_idx", 0)),
            key="sort_mode",
        )
        st.session_state["sort_mode_idx"] = ["Best match", "Lowest match", "Company A→Z", "Title A→Z"].index(sort_mode)
    with cc5:
        page_size = st.selectbox(
            "Per page",
            options=[10, 15, 20, 30, 50],
            index=[10, 15, 20, 30, 50].index(int(st.session_state.get("page_size", DEFAULT_PAGE_SIZE))),
            key="page_size",
        )
    st.markdown("</div>", unsafe_allow_html=True)

    shortlist: set = st.session_state.setdefault("shortlist", set())

    normalized = _build_ranked_rows(ranked, ref)

    filtered = _apply_view_filters(
        normalized,
        posted_date_filter=posted_date_filter,
        reference_now=ref,
        query=query,
        portal_filter=portal_filter,
        min_score=float(min_score),
    )

    _, ui_date_metrics = filter_jobs_by_posted_date_with_metrics(
        [r["job"] for r in normalized],
        posted_date_filter,
        reference_now=ref,
    )
    _render_posted_date_debug_panel(result, ui_date_metrics)

    # Sort
    if sort_mode == "Lowest match":
        filtered.sort(key=lambda x: x["final_score"])
    elif sort_mode == "Company A→Z":
        filtered.sort(key=lambda x: (x["company"] or "").lower())
    elif sort_mode == "Title A→Z":
        filtered.sort(key=lambda x: (x["title"] or "").lower())
    else:  # Best match
        filtered.sort(key=lambda x: x["final_score"], reverse=True)

    # Tabs: All vs Shortlist
    tab_all, tab_short = st.tabs(["All results", f"Shortlisted ({len(shortlist)})"])

    def _render_list(items: List[Dict[str, Any]], key_prefix: str) -> None:
        if not items:
            st.markdown(
                """
                <div class="empty-state">
                    <div class="empty-state-icon">🔎</div>
                    <p><strong>No jobs match these filters</strong></p>
                    <p>Try lowering min score, clearing portal filter, changing search text, or selecting <strong>Any Time</strong> for posted date.</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            return

        # Pagination
        total = len(items)
        page_key = f"page_{key_prefix}"
        page = int(st.session_state.get(page_key, 1))
        per_page = int(page_size)
        total_pages = max(1, (total + per_page - 1) // per_page)
        if page > total_pages:
            page = total_pages
            st.session_state[page_key] = page

        p1, p2, p3, p4 = st.columns([1.2, 1, 1.2, 3])
        with p1:
            if st.button("← Prev", disabled=(page <= 1), key=f"prev_{key_prefix}"):
                st.session_state[page_key] = page - 1
                st.rerun()
        with p2:
            st.write(f"Page **{page}** / **{total_pages}**")
        with p3:
            if st.button("Next →", disabled=(page >= total_pages), key=f"next_{key_prefix}"):
                st.session_state[page_key] = page + 1
                st.rerun()
        with p4:
            st.caption(f"Showing {(page-1)*per_page+1}–{min(page*per_page, total)} of {total}")

        start = (page - 1) * per_page
        end = start + per_page
        page_items = items[start:end]

        for idx, r in enumerate(page_items, start + 1):
            render_job_card(
                rank=idx,
                job=r["job"],
                score_info=r["score_info"],
                final_score=r["final_score"],
            )

        # Export button
        export_rows = []
        for r in items:
            export_rows.append(
                {
                    "title": r["title"],
                    "company": r["company"],
                    "portal": r["portal"],
                    "location": r["location"],
                    "final_score": f"{r['final_score']:.2f}",
                    "url": r["url"],
                }
            )
        st.download_button(
            "Download CSV",
            data=_to_csv_bytes(export_rows),
            file_name="ranked_jobs.csv" if key_prefix == "all" else "shortlisted_jobs.csv",
            mime="text/csv",
            use_container_width=True,
            key=f"dl_{key_prefix}",
        )

    with tab_all:
        _render_list(filtered, "all")

    with tab_short:
        short_items = [r for r in filtered if r["job_id"] in shortlist]
        _render_list(short_items, "short")

def run_workflow_with_progress(
    *,
    resume_path: str,
    target_role: str,
    location: Optional[str],
    experience_years: Optional[float],
    portals: List[str],
    max_per_portal: int,
    posted_date_filter: PostedDateFilter = "any_time",
) -> Dict[str, Any]:
    """Run parse → discover → rank with progress feedback (no backend changes)."""
    progress = st.progress(0, text="Starting…")
    status = st.status("Preparing pipeline…", expanded=True)
    try:
        from datetime import datetime, timezone

        workflow_reference_time_utc = datetime.now(timezone.utc)

        status.update(label="1/3 Parsing resume…", state="running")
        progress.progress(8, text="Parsing resume…")
        resume_text = parse_resume(resume_path)
        if not resume_text:
            status.update(label="Parsing failed", state="error")
            progress.empty()
            return {"error": "Failed to parse resume", "resume_profile": {}, "jobs_found": [], "ranked_jobs": [], "applied_jobs": []}

        agent = ResumeParserAgent()
        profile = agent.parse(resume_text)
        preferred = list(profile.get("preferred_roles") or [])
        if target_role and target_role not in preferred:
            preferred.insert(0, target_role)
        profile["preferred_roles"] = preferred
        profile["raw_text"] = resume_text
        progress.progress(28, text="Resume parsed. Discovering jobs…")
        status.write("✓ Resume parsed")

        # 2) Discover jobs
        status.update(label="2/3 Discovering jobs…", state="running")
        status.write(f"Portals: {', '.join(portals)} · Max per portal: {max_per_portal}")
        progress.progress(38, text="Scraping portals… (this can take ~1–2 minutes)")
        discovery = discover_jobs(
            target_role=target_role or "Software Engineer",
            location=location,
            experience_years=experience_years,
            portals=portals,
            max_per_portal=max_per_portal,
            fetch_descriptions=False,
            posted_date_filter=posted_date_filter,
            workflow_reference_time_utc=workflow_reference_time_utc,
        )
        jobs = discovery.jobs
        status.write(f"✓ Discovered {len(jobs)} jobs")
        progress.progress(70, text="Ranking jobs with AI…")

        # 3) Rank jobs
        status.update(label="3/3 Ranking jobs…", state="running")
        ranked = rank_jobs_with_details(
            jobs=jobs,
            candidate_profile=profile,
            min_score=0.0,
            top_k=None,
        )
        status.write(f"✓ Ranked {len(ranked)} jobs")
        progress.progress(100, text="Done")
        status.update(label="Completed", state="complete")
        return {
            "error": None,
            "resume_profile": profile,
            "jobs_found": jobs,
            "ranked_jobs": ranked,
            "applied_jobs": [],
            "workflow_reference_time_utc": discovery.workflow_reference_time_utc,
            "scrape_posted_date_filter": discovery.scrape_posted_date_filter,
            "posted_date_metrics": discovery.scrape_metrics.to_dict(),
        }
    except Exception as e:
        logger.exception("Workflow failed: %s", e)
        status.update(label="Workflow failed", state="error")
        progress.empty()
        return {"error": str(e), "resume_profile": {}, "jobs_found": [], "ranked_jobs": [], "applied_jobs": []}


def main() -> None:
    """Run the Streamlit dashboard."""
    st.set_page_config(
        page_title="AI Job Hunter Agent | ScriptNeuron",
        page_icon=str(LOGO_PATH) if LOGO_PATH.exists() else "🔍",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    inject_custom_css()
    init_db()

    if "workflow_result" not in st.session_state:
        st.session_state.workflow_result = None

    resume_path: Optional[str] = None

    # Sidebar: Resume upload and filters
    with st.sidebar:
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), use_container_width=True)
            st.markdown("---")

        st.markdown('<p class="sidebar-section">Resume</p>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader(
            "Upload resume (PDF, TXT)",
            type=["pdf", "txt", "md"],
            label_visibility="collapsed",
        )
        if uploaded_file:
            save_dir = Path("data/uploads")
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / uploaded_file.name
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            resume_path = str(save_path)
            st.session_state.resume_path = resume_path
            st.success(f"✓ {uploaded_file.name}")
        elif st.session_state.get("resume_path"):
            resume_path = st.session_state.resume_path
            st.info(f"Using: {Path(resume_path).name}")

        st.markdown('<p class="sidebar-section">Target Role</p>', unsafe_allow_html=True)
        target_role = st.text_input(
            "Job title",
            value="AI Engineer",
            placeholder="e.g. AI Engineer, ML Engineer",
            label_visibility="collapsed",
        )
        experience_input = st.text_input(
            "Years of experience (optional)",
            placeholder="Leave blank for all jobs",
            value="",
            label_visibility="collapsed",
        )
        experience_years = None
        if experience_input and str(experience_input).strip():
            try:
                experience_years = float(str(experience_input).strip())
                if experience_years < 0 or experience_years > 30:
                    experience_years = None
            except ValueError:
                experience_years = None
        location = st.text_input(
            "Location (optional)",
            placeholder="Remote, India, Bangalore",
            label_visibility="collapsed",
        )

        st.markdown('<p class="sidebar-section">Posted Date</p>', unsafe_allow_html=True)
        posted_date_filter: PostedDateFilter = st.radio(
            "Posted date filter",
            options=POSTED_DATE_FILTER_OPTIONS,
            format_func=lambda k: POSTED_DATE_FILTER_LABELS[k],
            index=POSTED_DATE_FILTER_OPTIONS.index(
                st.session_state.get("posted_date_filter", "any_time")
            ),
            key="posted_date_filter",
            label_visibility="collapsed",
        )

        st.markdown('<p class="sidebar-section">Discovery</p>', unsafe_allow_html=True)
        with st.expander("Portals & limits", expanded=False):
            st.caption("Choose job portals and max jobs per portal.")
            col1, col2 = st.columns(2)
            with col1:
                use_linkedin = st.checkbox("LinkedIn", value=True, key="portal_linkedin")
                use_indeed = st.checkbox("Indeed", value=True, key="portal_indeed")
                use_naukri = st.checkbox("Naukri", value=True, key="portal_naukri")
            with col2:
                max_per_portal = st.number_input(
                    "Max per portal",
                    min_value=5,
                    max_value=50,
                    value=15,
                    step=5,
                    key="max_per_portal",
                )
        portals: List[str] = []
        if use_linkedin:
            portals.append("linkedin")
        if use_indeed:
            portals.append("indeed")
        if use_naukri:
            portals.append("naukri")
        if not portals:
            portals = ["linkedin", "indeed", "naukri"]

        st.markdown("---")
        run_clicked = st.button(
            "Discover & Rank Jobs",
            type="primary",
            use_container_width=True,
        )

    result = st.session_state.workflow_result

    display_stats = None
    if result and not result.get("error"):
        display_stats = compute_display_stats(result)

    # ── Hero is ALWAYS the first visible section ──────────────────
    render_hero(result=result, display_stats=display_stats)

    # ── Progress placeholder sits below hero ──────────────────────
    # While running: progress renders inside it.
    # After completion: placeholder is cleared → st.rerun() paints
    # the page fresh with no progress widget anywhere.
    progress_placeholder = st.empty()

    # ── Trigger workflow on button click ─────────────────────────
    if run_clicked:
        active_resume = resume_path or st.session_state.get("resume_path")
        if not active_resume:
            st.error("Please upload a resume in the sidebar first.")
        elif not target_role:
            st.error("Please enter a target role.")
        else:
            with progress_placeholder.container():
                run_result = run_workflow_with_progress(
                    resume_path=active_resume,
                    target_role=target_role,
                    location=location or None,
                    experience_years=experience_years,
                    portals=portals,
                    max_per_portal=int(max_per_portal),
                    posted_date_filter=posted_date_filter,
                )
            # Fallback on error
            if run_result.get("error"):
                try:
                    try:
                        run_result = run_job_hunter_workflow(
                            resume_path=active_resume,
                            target_role=target_role,
                            location=location or None,
                            experience_years=experience_years,
                            portals=portals if portals else None,
                            max_per_portal=max_per_portal,
                            posted_date_filter=posted_date_filter,
                        )
                    except TypeError:
                        run_result = run_job_hunter_workflow(
                            resume_path=active_resume,
                            target_role=target_role,
                            location=location or None,
                            experience_years=experience_years,
                            portals=portals if portals else None,
                            max_per_portal=max_per_portal,
                            posted_date_filter=posted_date_filter,
                        )
                except Exception as e:
                    logger.exception("Dashboard workflow fallback failed: %s", e)
                    st.error(f"Workflow failed: {e}")
            st.session_state.workflow_result = run_result
            # Clear placeholder and rerun: page repaints with hero first,
            # no progress tracker anywhere — clean SaaS result view.
            progress_placeholder.empty()
            st.rerun()

    # ── Results / empty state ─────────────────────────────────────
    if result and not result.get("error"):
        render_results(result)
    elif result and result.get("error"):
        st.error(f"Error: {result['error']}")
    else:
        render_how_it_works()
        st.markdown(
            """
            <div class="empty-state">
                <div class="empty-state-icon">🎯</div>
                <p><strong>Ready when you are</strong></p>
                <p>Upload your resume in the sidebar and click <strong>Discover &amp; Rank Jobs</strong>
                to see AI-ranked matches here.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )


if __name__ == "__main__":
    main()
