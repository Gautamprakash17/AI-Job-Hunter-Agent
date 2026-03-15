"""
Main entry point for AI Job Hunter Agent.

Supports running the FastAPI server, Streamlit dashboard,
or CLI workflow execution.
"""

import argparse
import logging
import sys
from pathlib import Path

# Ensure project root is in path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import settings

logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def run_api() -> None:
    """Run the FastAPI server."""
    import uvicorn
    from api.main_api import app

    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
    )


def run_dashboard() -> None:
    """Run the Streamlit dashboard."""
    import subprocess

    dashboard_path = PROJECT_ROOT / "dashboard" / "dashboard.py"
    subprocess.run(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(dashboard_path),
            "--server.port",
            str(settings.dashboard_port),
        ],
        cwd=str(PROJECT_ROOT),
    )


def run_workflow_cli(resume_path: str, target_role: str, location: str = None) -> None:
    """Run the job hunter workflow from CLI."""
    from workflows.job_agent_graph import run_job_hunter_workflow

    logger.info("Running workflow: resume=%s, role=%s", resume_path, target_role)
    result = run_job_hunter_workflow(
        resume_path=resume_path,
        target_role=target_role,
        location=location,
    )
    ranked = result.get("ranked_jobs", [])
    logger.info("Found %d ranked jobs", len(ranked))
    for i, (job, score_info) in enumerate(ranked[:10], 1):
        score = score_info.get("final_score", 0) if isinstance(score_info, dict) else score_info
        print(f"{i}. {job.get('title')} @ {job.get('company')} — {score:.2f}")


def main() -> None:
    """Parse arguments and dispatch to appropriate runner."""
    parser = argparse.ArgumentParser(
        description="AI Job Hunter Agent - Discover, rank, and apply to jobs."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # API server
    api_parser = subparsers.add_parser("api", help="Run FastAPI server")
    api_parser.set_defaults(func=run_api)

    # Dashboard
    dash_parser = subparsers.add_parser("dashboard", help="Run Streamlit dashboard")
    dash_parser.set_defaults(func=run_dashboard)

    # CLI workflow
    workflow_parser = subparsers.add_parser("workflow", help="Run job hunter workflow")
    workflow_parser.add_argument("--resume", "-r", required=True, help="Path to resume")
    workflow_parser.add_argument("--role", required=True, help="Target job role")
    workflow_parser.add_argument("--location", "-l", help="Location filter")

    args = parser.parse_args()

    if args.command == "workflow":
        run_workflow_cli(args.resume, args.role, getattr(args, "location", None))
    elif args.command and hasattr(args, "func"):
        args.func()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
