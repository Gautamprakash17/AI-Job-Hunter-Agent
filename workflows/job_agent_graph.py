"""
LangGraph workflow for AI Job Hunter Agent.

Job discovery and ranking only (no auto-apply).
Flow: Parse Resume -> Discover Jobs -> Rank Jobs -> END.
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

from langgraph.graph import END, StateGraph

from agents.resume_parser_agent import ResumeParserAgent, parse_resume
from agents.job_discovery_agent import discover_jobs
from agents.job_ranking_agent import rank_jobs_with_details

logger = logging.getLogger(__name__)


class JobAgentState(TypedDict):
    """State for the LangGraph job agent workflow."""

    # Inputs
    resume_path: str
    target_role: str
    location: Optional[str]
    experience_years: Optional[float]

    # Agent outputs
    resume_profile: Dict[str, Any]
    jobs_found: List[Dict[str, Any]]
    ranked_jobs: List[Any]  # List[tuple[job_dict, score_info]]
    applied_jobs: List[Dict[str, Any]]  # Unused; kept for API compatibility (always [])

    # Internal / error
    error: Optional[str]


def _parse_resume_node(state: JobAgentState) -> JobAgentState:
    """Parse resume file and extract structured profile."""
    try:
        text = parse_resume(state["resume_path"])
        if not text:
            return {**state, "error": "Failed to parse resume", "resume_profile": {}}

        agent = ResumeParserAgent()
        profile = agent.parse(text)

        # Ensure target role is reflected in preferred_roles
        preferred = list(profile.get("preferred_roles") or [])
        if state.get("target_role") and state["target_role"] not in preferred:
            preferred.insert(0, state["target_role"])
        profile["preferred_roles"] = preferred
        profile["raw_text"] = text

        return {**state, "resume_profile": profile, "error": None}
    except Exception as exc:  # defensive
        logger.exception("Parse resume failed: %s", exc)
        return {**state, "error": str(exc), "resume_profile": {}}


def _discover_jobs_node(state: JobAgentState) -> JobAgentState:
    """Discover jobs from configured portals."""
    if state.get("error"):
        return state

    profile = state.get("resume_profile") or {}
    target = state.get("target_role") or (profile.get("preferred_roles") or [""])[0]
    if isinstance(target, list):
        target = target[0] if target else ""

    # Use only explicit experience from UI/API; do not fall back to resume profile.
    # When experience_years is None, discovery returns all jobs (no experience filter).
    exp_years: Optional[float] = state.get("experience_years")

    try:
        jobs = discover_jobs(
            target_role=target or "Software Engineer",
            location=state.get("location"),
            experience_years=exp_years,
            max_per_portal=15,
            fetch_descriptions=False,  # Faster; ranking uses title+company+short desc
        )
        return {**state, "jobs_found": jobs}
    except Exception as exc:
        logger.exception("Job discovery failed: %s", exc)
        return {**state, "error": str(exc), "jobs_found": []}


def _rank_jobs_node(state: JobAgentState) -> JobAgentState:
    """Rank jobs using semantic similarity with candidate profile."""
    if state.get("error"):
        return state

    jobs = state.get("jobs_found") or []
    if not jobs:
        return {**state, "ranked_jobs": []}

    profile = state.get("resume_profile") or {}

    # No score limit: rank all jobs by relevance; user decides which to apply to
    try:
        ranked = rank_jobs_with_details(
            jobs=jobs,
            candidate_profile=profile,
            min_score=0.0,
            top_k=None,
        )
        return {**state, "ranked_jobs": ranked}
    except Exception as exc:
        logger.exception("Job ranking failed: %s", exc)
        # Fallback: no ranking
        _empty_breakdown = {"final_score": 0.0, "embedding_score": 0.0, "title_match": 0}
        return {**state, "ranked_jobs": [(job, _empty_breakdown) for job in jobs]}


def build_job_agent_graph() -> StateGraph:
    """
    Build the LangGraph workflow for the job agent (discovery + ranking only).

    Flow:
    START -> parse_resume -> discover_jobs -> rank_jobs -> END
    """
    workflow = StateGraph(JobAgentState)

    workflow.add_node("parse_resume", _parse_resume_node)
    workflow.add_node("discover_jobs", _discover_jobs_node)
    workflow.add_node("rank_jobs", _rank_jobs_node)

    workflow.set_entry_point("parse_resume")
    workflow.add_edge("parse_resume", "discover_jobs")
    workflow.add_edge("discover_jobs", "rank_jobs")
    workflow.add_edge("rank_jobs", END)

    return workflow.compile()


_job_agent_graph = None


def get_job_agent_graph() -> StateGraph:
    """Get or create the compiled LangGraph job agent graph."""
    global _job_agent_graph
    if _job_agent_graph is None:
        _job_agent_graph = build_job_agent_graph()
    return _job_agent_graph


def run_job_agent(resume_path: str, target_role: str) -> Dict[str, Any]:
    """
    Run the full multi-agent job workflow.

    Args:
        resume_path: Path to resume PDF/TXT.
        target_role: Target job role string.

    Returns:
        Final JobAgentState dict with keys:
        - resume_profile
        - jobs_found
        - ranked_jobs
        - applied_jobs
        - error
    """
    graph = get_job_agent_graph()
    initial_state: JobAgentState = {
        "resume_path": resume_path,
        "target_role": target_role,
        "location": None,
        "experience_years": None,
        "resume_profile": {},
        "jobs_found": [],
        "ranked_jobs": [],
        "applied_jobs": [],
        "error": None,
    }
    return graph.invoke(initial_state)


def run_job_hunter_workflow(
    resume_path: str,
    target_role: str,
    location: Optional[str] = None,
    experience_years: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Backwards-compatible wrapper around run_job_agent.
    Location and experience_years are currently hints; core flow uses resume profile.
    """
    graph = get_job_agent_graph()
    initial_state: JobAgentState = {
        "resume_path": resume_path,
        "target_role": target_role,
        "location": location,
        "experience_years": experience_years,
        "resume_profile": {},
        "jobs_found": [],
        "ranked_jobs": [],
        "applied_jobs": [],
        "error": None,
    }
    return graph.invoke(initial_state)
