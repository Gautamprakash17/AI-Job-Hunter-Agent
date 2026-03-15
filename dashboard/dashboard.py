"""
Streamlit dashboard for AI Job Hunter Agent.

Job discovery and ranking assistant: discover jobs, view ranked results,
and open job links to apply on the portal.
"""

import logging
import sys
from pathlib import Path

import streamlit as st

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from config.settings import settings
from database.db import init_db
from workflows.job_agent_graph import run_job_hunter_workflow

logger = logging.getLogger(__name__)


def main() -> None:
    """Run the Streamlit dashboard."""
    st.set_page_config(
        page_title="AI Job Hunter Agent",
        page_icon="🔍",
        layout="wide",
    )

    st.title("🔍 AI Job Hunter Agent")
    st.markdown(
        "Upload your resume, specify your target role, and discover ranked job matches. "
        "Click **Open Job** to apply on the portal."
    )

    init_db()

    if "workflow_result" not in st.session_state:
        st.session_state.workflow_result = None

    # Sidebar: Resume upload and filters
    with st.sidebar:
        st.header("Resume")
        uploaded_file = st.file_uploader(
            "Upload resume (PDF, TXT)",
            type=["pdf", "txt", "md"],
        )
        resume_path = None
        if uploaded_file:
            save_dir = Path("data/uploads")
            save_dir.mkdir(parents=True, exist_ok=True)
            save_path = save_dir / uploaded_file.name
            with open(save_path, "wb") as f:
                f.write(uploaded_file.getvalue())
            resume_path = str(save_path)
            st.session_state.resume_path = resume_path
            st.success(f"Uploaded: {uploaded_file.name}")

        st.header("Target Role")
        target_role = st.text_input(
            "Job title (e.g., AI Engineer)",
            value="AI Engineer",
        )
        experience_input = st.text_input(
            "Years of Experience (optional)",
            placeholder="Leave blank to show all jobs",
            value="",
        )
        experience_years = None
        if experience_input and str(experience_input).strip():
            try:
                experience_years = float(str(experience_input).strip())
                if experience_years < 0 or experience_years > 30:
                    experience_years = None
            except ValueError:
                experience_years = None
        location = st.text_input("Location (optional)", placeholder="Remote, India")

        st.header("Discovery options (optional)")
        with st.expander("Portals & limits", expanded=False):
            st.caption("Choose which job portals to use and how many jobs per portal.")
            col1, col2 = st.columns(2)
            with col1:
                use_linkedin = st.checkbox("LinkedIn", value=True, key="portal_linkedin")
                use_indeed = st.checkbox("Indeed", value=True, key="portal_indeed")
                use_naukri = st.checkbox("Naukri", value=True, key="portal_naukri")
            with col2:
                max_per_portal = st.number_input(
                    "Max jobs per portal",
                    min_value=5,
                    max_value=50,
                    value=15,
                    step=5,
                    key="max_per_portal",
                )
        portals = []
        if use_linkedin:
            portals.append("linkedin")
        if use_indeed:
            portals.append("indeed")
        if use_naukri:
            portals.append("naukri")
        if not portals:
            portals = ["linkedin", "indeed", "naukri"]  # fallback

    # Main area: Discover & Rank
    if st.button("🚀 Discover & Rank Jobs", type="primary"):
        if not resume_path:
            st.error("Please upload a resume first.")
        elif not target_role:
            st.error("Please enter a target role.")
        else:
            with st.spinner("Discovering and ranking jobs..."):
                try:
                    # Support both old and new workflow signature (portals, max_per_portal)
                    try:
                        result = run_job_hunter_workflow(
                            resume_path=resume_path,
                            target_role=target_role,
                            location=location or None,
                            experience_years=experience_years,
                            portals=portals if portals else None,
                            max_per_portal=max_per_portal,
                        )
                    except TypeError:
                        result = run_job_hunter_workflow(
                            resume_path=resume_path,
                            target_role=target_role,
                            location=location or None,
                            experience_years=experience_years,
                        )
                    st.session_state.workflow_result = result
                except Exception as e:
                    logger.exception("Dashboard workflow failed: %s", e)
                    st.error(f"Workflow failed: {e}")

    result = st.session_state.workflow_result

    # Single unified list of ranked jobs
    if result and not result.get("error"):
        ranked = result.get("ranked_jobs", [])
        jobs_found = result.get("jobs_found", [])

        ranked_count = len(ranked)
        st.success(f"Found and ranked {ranked_count} jobs by relevance. You decide which to apply to.")

        for i, ranked_item in enumerate(ranked, 1):
            job, score_info = ranked_item if isinstance(ranked_item, tuple) and len(ranked_item) == 2 else (ranked_item, {})
            if isinstance(score_info, dict):
                final_score = score_info.get("final_score", score_info.get("score", 0))
            else:
                final_score = score_info if isinstance(score_info, (int, float)) else 0

            title = job.get("title", "N/A")
            company = job.get("company", "N/A")
            portal = job.get("portal", "N/A")
            loc = job.get("location", "N/A")
            url = job.get("url") or ""

            with st.expander(f"#{i} {title} @ {company} — Score: {final_score:.2f}"):
                st.write(f"**Portal:** {portal}")
                st.write(f"**Location:** {loc}")

                # Score breakdown
                if isinstance(score_info, dict) and any(
                    k in score_info for k in ("embedding_score", "title_match")
                ):
                    st.markdown("**Score breakdown**")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        st.metric("Final Score", f"{score_info.get('final_score', final_score):.2f}")
                    with c2:
                        st.metric("Embedding Similarity", f"{score_info.get('embedding_score', 0):.2f}")
                    with c3:
                        st.metric("Title Match", score_info.get("title_match", 0))

                if job.get("description"):
                    st.text(job["description"][:500] + ("..." if len(job.get("description", "")) > 500 else ""))

                if url:
                    st.link_button("Open Job", url, type="primary")

    elif result and result.get("error"):
        st.error(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
