"""
Custom Job Search Agent for AI Job Hunter Agent.

Autonomous agent that:
1. Searches for jobs based on user's resume and preferences
2. Ranks jobs using semantic similarity
3. Sends WhatsApp notifications for high-match jobs
4. Can be scheduled to run periodically
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from agents.job_discovery_agent import discover_jobs
from agents.job_ranking_agent import rank_jobs_with_details
from agents.resume_parser_agent import parse_resume, ResumeParserAgent
from config.settings import settings
from database.db import get_db
from database.models import Job, Resume, Application
from notifications.whatsapp_service import send_whatsapp_notification, send_bulk_job_notifications

logger = logging.getLogger(__name__)


class CustomSearchAgent:
    """
    Autonomous job search agent that runs based on user preferences.
    
    Features:
    - Resume-based automatic job discovery
    - Intelligent ranking and filtering
    - WhatsApp notifications for top matches
    - Deduplication to avoid repeat notifications
    - Configurable search frequency and criteria
    """

    def __init__(
        self,
        resume_id: int,
        user_phone: str,
        min_score: float = 0.7,
        max_jobs_per_search: int = 5,
        portals: Optional[List[str]] = None,
    ):
        """
        Initialize custom search agent.

        Args:
            resume_id: Database ID of the resume to use
            user_phone: WhatsApp number (format: +1234567890)
            min_score: Minimum job match score (0-1)
            max_jobs_per_search: Max jobs to notify per search
            portals: Job portals to search (default: all)
        """
        self.resume_id = resume_id
        self.user_phone = user_phone
        self.min_score = min_score
        self.max_jobs_per_search = max_jobs_per_search
        self.portals = portals or ["linkedin", "indeed", "naukri"]

    def run_search(
        self,
        location: Optional[str] = None,
        max_per_portal: int = 20,
    ) -> Dict[str, Any]:
        """
        Run a complete job search cycle.

        Steps:
        1. Load resume and parse profile
        2. Discover jobs from portals
        3. Rank jobs by relevance
        4. Filter high-match jobs (above min_score)
        5. Send WhatsApp notifications
        6. Save to database

        Args:
            location: Optional location filter
            max_per_portal: Max jobs to fetch per portal

        Returns:
            Dict with search results and notification status
        """
        logger.info(
            "Starting custom search for resume_id=%d, phone=%s",
            self.resume_id,
            self.user_phone,
        )

        try:
            # Step 1: Load resume and get profile
            db = next(get_db())
            resume = db.query(Resume).filter(Resume.id == self.resume_id).first()
            
            if not resume:
                logger.error("Resume not found: id=%d", self.resume_id)
                return {"success": False, "error": "Resume not found"}

            # Parse resume if not already parsed
            if not resume.parsed_content:
                resume_text = parse_resume(resume.file_path)
                if resume_text:
                    parser = ResumeParserAgent()
                    profile = parser.parse(resume_text)
                    resume.parsed_content = str(profile)
                    db.commit()
                else:
                    return {"success": False, "error": "Failed to parse resume"}
            else:
                # Use existing parsed content
                import ast
                try:
                    profile = ast.literal_eval(resume.parsed_content)
                except:
                    profile = {}

            target_role = resume.target_role or (
                profile.get("preferred_roles", ["Software Engineer"])[0]
                if profile.get("preferred_roles")
                else "Software Engineer"
            )

            # Step 2: Discover jobs
            logger.info("Discovering jobs for role: %s", target_role)
            jobs = discover_jobs(
                target_role=target_role,
                location=location,
                experience_years=resume.experience_years,
                portals=self.portals,
                max_per_portal=max_per_portal,
                fetch_descriptions=True,
            )

            if not jobs:
                logger.info("No jobs found")
                return {
                    "success": True,
                    "jobs_found": 0,
                    "jobs_notified": 0,
                    "message": "No new jobs found",
                }

            # Step 3: Rank jobs
            logger.info("Ranking %d jobs", len(jobs))
            ranked = rank_jobs_with_details(
                jobs=jobs,
                candidate_profile=profile,
                min_score=self.min_score,
                top_k=None,  # Get all above threshold
            )

            # Step 4: Filter and deduplicate
            high_match_jobs = []
            seen_urls = set()
            
            # Get already notified job URLs from database
            existing_jobs = db.query(Job).filter(
                Job.url.in_([j[0].get("url") for j in ranked if j[0].get("url")])
            ).all()
            notified_urls = {j.url for j in existing_jobs}

            for job_dict, score_info in ranked[:self.max_jobs_per_search * 2]:
                url = job_dict.get("url")
                if not url or url in seen_urls or url in notified_urls:
                    continue
                    
                seen_urls.add(url)
                high_match_jobs.append((job_dict, score_info))
                
                if len(high_match_jobs) >= self.max_jobs_per_search:
                    break

            if not high_match_jobs:
                logger.info("No new high-match jobs (all already notified)")
                return {
                    "success": True,
                    "jobs_found": len(jobs),
                    "jobs_ranked": len(ranked),
                    "jobs_notified": 0,
                    "message": "No new jobs above threshold",
                }

            # Step 5: Save jobs to database
            saved_job_ids = []
            for job_dict, score_info in high_match_jobs:
                job_record = Job(
                    external_id=job_dict.get("external_id"),
                    portal=job_dict.get("portal", "unknown"),
                    title=job_dict.get("title", "Unknown"),
                    company=job_dict.get("company", "Unknown"),
                    location=job_dict.get("location"),
                    url=job_dict.get("url"),
                    description=job_dict.get("description"),
                    extra_metadata={
                        "match_score": score_info.get("final_score"),
                        "embedding_score": score_info.get("embedding_score"),
                        "title_match": score_info.get("title_match"),
                    },
                )
                db.add(job_record)
                db.flush()
                saved_job_ids.append(job_record.id)

            db.commit()

            # Step 6: Send WhatsApp notifications
            logger.info("Sending WhatsApp notifications for %d jobs", len(high_match_jobs))
            notification_result = send_bulk_job_notifications(
                phone_number=self.user_phone,
                jobs_with_scores=high_match_jobs,
                resume_name=resume.filename,
            )

            return {
                "success": True,
                "jobs_found": len(jobs),
                "jobs_ranked": len(ranked),
                "jobs_notified": len(high_match_jobs),
                "notification_sent": notification_result.get("success", False),
                "jobs": [
                    {
                        "title": j[0].get("title"),
                        "company": j[0].get("company"),
                        "score": j[1].get("final_score"),
                        "url": j[0].get("url"),
                    }
                    for j in high_match_jobs
                ],
            }

        except Exception as e:
            logger.exception("Custom search failed: %s", e)
            return {"success": False, "error": str(e)}


def run_custom_search_for_user(
    resume_id: int,
    user_phone: str,
    location: Optional[str] = None,
    min_score: float = 0.7,
    max_jobs_per_search: int = 5,
    portals: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Convenience function to run custom search.

    Args:
        resume_id: Database ID of resume
        user_phone: WhatsApp number (format: +1234567890)
        location: Optional location filter
        min_score: Minimum job match score
        max_jobs_per_search: Max jobs to notify
        portals: Job portals to search

    Returns:
        Search result dict
    """
    agent = CustomSearchAgent(
        resume_id=resume_id,
        user_phone=user_phone,
        min_score=min_score,
        max_jobs_per_search=max_jobs_per_search,
        portals=portals,
    )
    return agent.run_search(location=location)


# Example usage
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) < 3:
        print("Usage: python custom_search_agent.py <resume_id> <phone_number> [location]")
        print("Example: python custom_search_agent.py 1 +919876543210 'Bangalore'")
        sys.exit(1)
    
    resume_id = int(sys.argv[1])
    phone = sys.argv[2]
    location = sys.argv[3] if len(sys.argv) > 3 else None
    
    result = run_custom_search_for_user(
        resume_id=resume_id,
        user_phone=phone,
        location=location,
        min_score=0.7,
        max_jobs_per_search=5,
    )
    
    print("\n=== Custom Search Results ===")
    print(f"Success: {result.get('success')}")
    print(f"Jobs Found: {result.get('jobs_found', 0)}")
    print(f"Jobs Notified: {result.get('jobs_notified', 0)}")
    print(f"Notification Sent: {result.get('notification_sent', False)}")
    
    if result.get("jobs"):
        print("\nTop Matches:")
        for i, job in enumerate(result["jobs"], 1):
            print(f"{i}. {job['title']} @ {job['company']} - Score: {job['score']:.2f}")
