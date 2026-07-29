"""
Demo script for Custom Job Search Agent with WhatsApp Notifications.

This demonstrates:
1. Uploading a resume
2. Running a one-time custom search
3. Scheduling periodic searches
4. Viewing search history

Usage:
    python examples/custom_search_demo.py --phone +919876543210 --resume path/to/resume.pdf
"""

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from database.db import get_db, init_db
from database.models import Resume, SearchHistory
from agents.resume_parser_agent import parse_resume, ResumeParserAgent
from agents.custom_search_agent import run_custom_search_for_user
from notifications.scheduler import get_scheduler

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def upload_resume(resume_path: str, phone: str, target_role: str = "AI Engineer") -> int:
    """
    Upload and parse resume, save to database.
    
    Returns:
        Resume ID
    """
    logger.info("Uploading resume: %s", resume_path)
    
    # Parse resume
    resume_text = parse_resume(resume_path)
    if not resume_text:
        raise ValueError("Failed to parse resume")
    
    parser = ResumeParserAgent()
    profile = parser.parse(resume_text)
    
    # Infer experience years from profile
    exp_str = profile.get("experience_years", "0")
    try:
        experience_years = float(exp_str.split()[0]) if exp_str else 0.0
    except:
        experience_years = 0.0
    
    # Save to database
    db = next(get_db())
    resume = Resume(
        filename=Path(resume_path).name,
        file_path=resume_path,
        parsed_content=str(profile),
        target_role=target_role,
        experience_years=experience_years,
        user_phone=phone,
        preferred_location=None,
        min_match_score=0.7,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)
    
    logger.info("Resume uploaded successfully! ID: %d", resume.id)
    logger.info("Parsed profile: %s", profile)
    
    return resume.id


def run_one_time_search(resume_id: int, phone: str, location: str = None):
    """Run a one-time custom job search."""
    logger.info("Running one-time custom search for resume_id=%d", resume_id)
    
    result = run_custom_search_for_user(
        resume_id=resume_id,
        user_phone=phone,
        location=location,
        min_score=0.7,
        max_jobs_per_search=5,
        portals=["linkedin", "indeed"],
    )
    
    logger.info("Search completed!")
    logger.info("Jobs found: %d", result.get("jobs_found", 0))
    logger.info("Jobs notified: %d", result.get("jobs_notified", 0))
    logger.info("Notification sent: %s", result.get("notification_sent", False))
    
    if result.get("jobs"):
        print("\n=== Top Job Matches ===")
        for i, job in enumerate(result["jobs"], 1):
            print(f"{i}. {job['title']} @ {job['company']}")
            print(f"   Score: {job['score']:.2f} | URL: {job['url']}")
    
    return result


def schedule_periodic_search(
    resume_id: int,
    phone: str,
    frequency: str = "daily",
    location: str = None,
):
    """Schedule periodic job searches."""
    logger.info("Scheduling %s search for resume_id=%d", frequency, resume_id)
    
    scheduler = get_scheduler()
    
    # Start scheduler if not running
    if not scheduler.is_running():
        scheduler.start()
        logger.info("Scheduler started")
    
    job_id = scheduler.add_scheduled_search(
        resume_id=resume_id,
        user_phone=phone,
        frequency=frequency,
        location=location,
        min_score=0.7,
        max_jobs_per_search=5,
        portals=["linkedin", "indeed"],
        hour=9,
        minute=0,
    )
    
    logger.info("Scheduled search activated! Job ID: %s", job_id)
    print(f"\n✅ Scheduled {frequency} searches at 09:00")
    print(f"📱 Notifications will be sent to {phone}")
    print(f"🔍 Searching: {location or 'All locations'}")
    
    return job_id


def view_search_history(resume_id: int):
    """View search history for a resume."""
    db = next(get_db())
    history = (
        db.query(SearchHistory)
        .filter(SearchHistory.resume_id == resume_id)
        .order_by(SearchHistory.executed_at.desc())
        .limit(10)
        .all()
    )
    
    if not history:
        print("\nNo search history found.")
        return
    
    print(f"\n=== Search History (Last {len(history)} searches) ===")
    for h in history:
        print(f"\n{h.executed_at.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Type: {h.search_type}")
        print(f"  Found: {h.jobs_found} jobs")
        print(f"  Notified: {h.jobs_notified} jobs")
        print(f"  Location: {h.location or 'Any'}")
        print(f"  Notification: {'✅ Sent' if h.notification_sent else '❌ Failed'}")
        if h.error_message:
            print(f"  Error: {h.error_message}")


def main():
    parser = argparse.ArgumentParser(
        description="Demo: Custom Job Search Agent with WhatsApp Notifications"
    )
    parser.add_argument(
        "--phone",
        required=True,
        help="WhatsApp phone number (format: +919876543210)",
    )
    parser.add_argument(
        "--resume",
        help="Path to resume file (PDF/TXT)",
    )
    parser.add_argument(
        "--resume-id",
        type=int,
        help="Existing resume ID (skip upload)",
    )
    parser.add_argument(
        "--target-role",
        default="AI Engineer",
        help="Target job role",
    )
    parser.add_argument(
        "--location",
        help="Location filter (e.g., Bangalore, Remote)",
    )
    parser.add_argument(
        "--schedule",
        choices=["hourly", "daily", "weekly"],
        help="Schedule periodic searches",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="View search history",
    )
    
    args = parser.parse_args()
    
    # Initialize database
    init_db()
    
    # Get or upload resume
    if args.resume_id:
        resume_id = args.resume_id
        logger.info("Using existing resume_id=%d", resume_id)
    elif args.resume:
        resume_id = upload_resume(args.resume, args.phone, args.target_role)
    else:
        parser.error("Either --resume or --resume-id is required")
        return
    
    # View history if requested
    if args.history:
        view_search_history(resume_id)
        return
    
    # Schedule periodic search if requested
    if args.schedule:
        schedule_periodic_search(
            resume_id=resume_id,
            phone=args.phone,
            frequency=args.schedule,
            location=args.location,
        )
        print("\n💡 Tip: Keep the scheduler running with:")
        print("   python notifications/scheduler.py start")
    else:
        # Default: Run one-time search
        run_one_time_search(
            resume_id=resume_id,
            phone=args.phone,
            location=args.location,
        )
        print(f"\n✅ Check your WhatsApp ({args.phone}) for job notifications!")
    
    print("\n📊 View search history with: --history --resume-id", resume_id)


if __name__ == "__main__":
    main()
