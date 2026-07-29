"""
Job Search Scheduler for AI Job Hunter Agent.

Schedules and manages periodic job searches with notifications.
Supports:
- Scheduled searches (cron-like)
- One-time searches
- Multiple user profiles
- Configurable frequency
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path
import json

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from agents.custom_search_agent import run_custom_search_for_user
from database.db import get_db
from database.models import Resume

logger = logging.getLogger(__name__)


class JobSearchScheduler:
    """
    Manages scheduled job searches for multiple users.
    
    Features:
    - Background job execution
    - Configurable search frequency
    - User preference management
    - Search history tracking
    """

    def __init__(self):
        """Initialize the scheduler."""
        self.scheduler = BackgroundScheduler()
        self.search_configs: Dict[int, Dict] = {}  # resume_id -> config
        self.config_file = Path("data/scheduler_config.json")
        self._load_configs()

    def _load_configs(self):
        """Load saved scheduler configurations."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    self.search_configs = json.load(f)
                logger.info("Loaded %d scheduler configs", len(self.search_configs))
            except Exception as e:
                logger.exception("Failed to load scheduler configs: %s", e)
                self.search_configs = {}
        else:
            self.search_configs = {}

    def _save_configs(self):
        """Save scheduler configurations."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w") as f:
                json.dump(self.search_configs, f, indent=2)
            logger.info("Saved scheduler configs")
        except Exception as e:
            logger.exception("Failed to save scheduler configs: %s", e)

    def add_scheduled_search(
        self,
        resume_id: int,
        user_phone: str,
        frequency: str = "daily",
        location: Optional[str] = None,
        min_score: float = 0.7,
        max_jobs_per_search: int = 5,
        portals: Optional[List[str]] = None,
        hour: int = 9,  # Default: 9 AM
        minute: int = 0,
    ) -> str:
        """
        Schedule periodic job search for a user.

        Args:
            resume_id: Database ID of resume
            user_phone: WhatsApp number
            frequency: 'hourly', 'daily', 'weekly', or cron expression
            location: Optional location filter
            min_score: Minimum job match score
            max_jobs_per_search: Max jobs to notify per search
            portals: Job portals to search
            hour: Hour of day for daily/weekly searches (0-23)
            minute: Minute for scheduled searches (0-59)

        Returns:
            Job ID string
        """
        job_id = f"search_{resume_id}"

        # Remove existing job if any
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)

        # Create trigger based on frequency
        if frequency == "hourly":
            trigger = IntervalTrigger(hours=1)
        elif frequency == "daily":
            trigger = CronTrigger(hour=hour, minute=minute)
        elif frequency == "weekly":
            trigger = CronTrigger(day_of_week=0, hour=hour, minute=minute)  # Monday
        elif frequency.startswith("every_"):
            # Parse "every_4h", "every_30m", etc.
            value = int(frequency.split("_")[1][:-1])
            unit = frequency.split("_")[1][-1]
            if unit == "h":
                trigger = IntervalTrigger(hours=value)
            elif unit == "m":
                trigger = IntervalTrigger(minutes=value)
            else:
                trigger = IntervalTrigger(hours=24)  # Default: daily
        else:
            # Default: daily
            trigger = CronTrigger(hour=hour, minute=minute)

        # Add job to scheduler
        self.scheduler.add_job(
            func=self._run_scheduled_search,
            trigger=trigger,
            args=[resume_id, user_phone, location, min_score, max_jobs_per_search, portals],
            id=job_id,
            name=f"Job search for resume {resume_id}",
            replace_existing=True,
        )

        # Save config
        self.search_configs[str(resume_id)] = {
            "resume_id": resume_id,
            "user_phone": user_phone,
            "frequency": frequency,
            "location": location,
            "min_score": min_score,
            "max_jobs_per_search": max_jobs_per_search,
            "portals": portals,
            "hour": hour,
            "minute": minute,
            "added_at": datetime.utcnow().isoformat(),
        }
        self._save_configs()

        logger.info(
            "Scheduled %s search for resume_id=%d at %02d:%02d",
            frequency,
            resume_id,
            hour,
            minute,
        )
        return job_id

    def _run_scheduled_search(
        self,
        resume_id: int,
        user_phone: str,
        location: Optional[str],
        min_score: float,
        max_jobs_per_search: int,
        portals: Optional[List[str]],
    ):
        """Execute a scheduled job search."""
        try:
            logger.info("Running scheduled search for resume_id=%d", resume_id)
            result = run_custom_search_for_user(
                resume_id=resume_id,
                user_phone=user_phone,
                location=location,
                min_score=min_score,
                max_jobs_per_search=max_jobs_per_search,
                portals=portals,
            )
            logger.info(
                "Scheduled search completed: found=%d, notified=%d",
                result.get("jobs_found", 0),
                result.get("jobs_notified", 0),
            )
        except Exception as e:
            logger.exception("Scheduled search failed for resume_id=%d: %s", resume_id, e)

    def remove_scheduled_search(self, resume_id: int) -> bool:
        """
        Remove scheduled search for a user.

        Args:
            resume_id: Resume ID

        Returns:
            True if removed, False if not found
        """
        job_id = f"search_{resume_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            if str(resume_id) in self.search_configs:
                del self.search_configs[str(resume_id)]
                self._save_configs()
            logger.info("Removed scheduled search for resume_id=%d", resume_id)
            return True
        return False

    def get_scheduled_searches(self) -> List[Dict]:
        """
        Get all scheduled searches.

        Returns:
            List of search config dicts
        """
        return list(self.search_configs.values())

    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Job search scheduler started")

    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Job search scheduler stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running


# Global scheduler instance
_scheduler: Optional[JobSearchScheduler] = None


def get_scheduler() -> JobSearchScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = JobSearchScheduler()
    return _scheduler


def start_scheduler():
    """Start the global scheduler."""
    scheduler = get_scheduler()
    if not scheduler.is_running():
        scheduler.start()


def stop_scheduler():
    """Stop the global scheduler."""
    scheduler = get_scheduler()
    if scheduler.is_running():
        scheduler.stop()


# CLI interface
if __name__ == "__main__":
    import sys
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Job Search Scheduler")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # Add scheduled search
    add_parser = subparsers.add_parser("add", help="Add scheduled search")
    add_parser.add_argument("resume_id", type=int, help="Resume ID")
    add_parser.add_argument("phone", help="WhatsApp phone number")
    add_parser.add_argument("--frequency", default="daily", help="hourly, daily, weekly")
    add_parser.add_argument("--location", help="Location filter")
    add_parser.add_argument("--min-score", type=float, default=0.7, help="Min score")
    add_parser.add_argument("--max-jobs", type=int, default=5, help="Max jobs per search")
    add_parser.add_argument("--hour", type=int, default=9, help="Hour (0-23)")
    add_parser.add_argument("--minute", type=int, default=0, help="Minute (0-59)")

    # Remove scheduled search
    remove_parser = subparsers.add_parser("remove", help="Remove scheduled search")
    remove_parser.add_argument("resume_id", type=int, help="Resume ID")

    # List scheduled searches
    list_parser = subparsers.add_parser("list", help="List scheduled searches")

    # Start scheduler daemon
    start_parser = subparsers.add_parser("start", help="Start scheduler daemon")

    args = parser.parse_args()

    scheduler = get_scheduler()

    if args.command == "add":
        job_id = scheduler.add_scheduled_search(
            resume_id=args.resume_id,
            user_phone=args.phone,
            frequency=args.frequency,
            location=args.location,
            min_score=args.min_score,
            max_jobs_per_search=args.max_jobs,
            hour=args.hour,
            minute=args.minute,
        )
        print(f"✅ Scheduled search added: {job_id}")

    elif args.command == "remove":
        if scheduler.remove_scheduled_search(args.resume_id):
            print(f"✅ Scheduled search removed for resume_id={args.resume_id}")
        else:
            print(f"❌ No scheduled search found for resume_id={args.resume_id}")

    elif args.command == "list":
        searches = scheduler.get_scheduled_searches()
        if not searches:
            print("No scheduled searches")
        else:
            print(f"\n📋 Scheduled Searches ({len(searches)}):\n")
            for config in searches:
                print(f"Resume ID: {config['resume_id']}")
                print(f"Phone: {config['user_phone']}")
                print(f"Frequency: {config['frequency']}")
                print(f"Time: {config.get('hour', 9):02d}:{config.get('minute', 0):02d}")
                print(f"Location: {config.get('location', 'Any')}")
                print(f"Min Score: {config.get('min_score', 0.7)}")
                print("-" * 40)

    elif args.command == "start":
        print("🚀 Starting job search scheduler...")
        scheduler.start()
        print("✅ Scheduler is running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n🛑 Stopping scheduler...")
            scheduler.stop()
            print("✅ Scheduler stopped")

    else:
        parser.print_help()
