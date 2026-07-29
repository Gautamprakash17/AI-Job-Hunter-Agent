"""
WhatsApp notification service for AI Job Hunter Agent.

Uses Twilio API to send WhatsApp messages with job alerts.
Alternative: Can also use WhatsApp Business API or other providers.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)


def send_whatsapp_notification(
    phone_number: str,
    message: str,
) -> Dict[str, Any]:
    """
    Send WhatsApp message using Twilio.

    Args:
        phone_number: Recipient's phone number (format: +1234567890)
        message: Message text to send

    Returns:
        Dict with success status and message_sid or error
    """
    try:
        # Check if Twilio is configured
        if not settings.twilio_account_sid or not settings.twilio_auth_token:
            logger.warning("Twilio not configured, logging message instead")
            logger.info("Would send WhatsApp to %s: %s", phone_number, message[:100])
            return {
                "success": False,
                "error": "Twilio not configured (set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)",
                "message": message,
            }

        from twilio.rest import Client

        client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

        # Send WhatsApp message
        # Format: whatsapp:+1234567890
        message_obj = client.messages.create(
            body=message,
            from_=f"whatsapp:{settings.twilio_whatsapp_number}",
            to=f"whatsapp:{phone_number}",
        )

        logger.info("WhatsApp sent to %s: %s", phone_number, message_obj.sid)
        return {
            "success": True,
            "message_sid": message_obj.sid,
            "phone_number": phone_number,
        }

    except Exception as e:
        logger.exception("WhatsApp notification failed: %s", e)
        return {
            "success": False,
            "error": str(e),
            "phone_number": phone_number,
        }


def format_job_notification(
    job: Dict[str, Any],
    score: float,
    rank: int = 1,
) -> str:
    """
    Format a single job notification message.

    Args:
        job: Job dict with title, company, location, url
        score: Match score (0-1)
        rank: Ranking position

    Returns:
        Formatted message string
    """
    title = job.get("title", "Unknown Position")
    company = job.get("company", "Unknown Company")
    location = job.get("location", "Location not specified")
    url = job.get("url", "")
    portal = job.get("portal", "").title()

    score_emoji = "🔥" if score >= 0.85 else "⭐" if score >= 0.75 else "✅"
    
    message = f"""
{score_emoji} *Job Match #{rank}* ({int(score * 100)}% match)

*{title}*
🏢 {company}
📍 {location}
🌐 Portal: {portal}

🔗 Apply: {url}

---
💼 Powered by AI Job Hunter Agent
""".strip()

    return message


def format_bulk_job_notification(
    jobs_with_scores: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    resume_name: str = "your resume",
) -> str:
    """
    Format multiple jobs into a single notification message.

    Args:
        jobs_with_scores: List of (job_dict, score_info) tuples
        resume_name: Name of the resume used

    Returns:
        Formatted message string
    """
    if not jobs_with_scores:
        return "No new job matches found."

    count = len(jobs_with_scores)
    header = f"""
🔍 *New Job Matches Found!*

Found {count} high-match job{"s" if count != 1 else ""} based on {resume_name}

---
""".strip()

    job_messages = []
    for i, (job, score_info) in enumerate(jobs_with_scores[:5], 1):  # Max 5 in one message
        score = score_info.get("final_score", 0)
        title = job.get("title", "Unknown Position")
        company = job.get("company", "Unknown Company")
        url = job.get("url", "")
        
        score_emoji = "🔥" if score >= 0.85 else "⭐" if score >= 0.75 else "✅"
        
        job_msg = f"""
{score_emoji} *{i}. {title}*
🏢 {company}
📊 Match: {int(score * 100)}%
🔗 {url}
""".strip()
        job_messages.append(job_msg)

    footer = """

---
💡 Tip: Click the links to apply directly!
💼 AI Job Hunter Agent
""".strip()

    return header + "\n\n" + "\n\n".join(job_messages) + "\n" + footer


def send_job_notification(
    phone_number: str,
    job: Dict[str, Any],
    score: float,
    rank: int = 1,
) -> Dict[str, Any]:
    """
    Send a single job notification via WhatsApp.

    Args:
        phone_number: Recipient's phone number
        job: Job dict
        score: Match score
        rank: Ranking position

    Returns:
        Notification result dict
    """
    message = format_job_notification(job, score, rank)
    return send_whatsapp_notification(phone_number, message)


def send_bulk_job_notifications(
    phone_number: str,
    jobs_with_scores: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    resume_name: str = "your resume",
) -> Dict[str, Any]:
    """
    Send multiple job notifications in a single WhatsApp message.

    Args:
        phone_number: Recipient's phone number
        jobs_with_scores: List of (job_dict, score_info) tuples
        resume_name: Resume filename or identifier

    Returns:
        Notification result dict
    """
    message = format_bulk_job_notification(jobs_with_scores, resume_name)
    return send_whatsapp_notification(phone_number, message)


def send_daily_digest(
    phone_number: str,
    jobs_count: int,
    top_jobs: List[Tuple[Dict[str, Any], float]],
) -> Dict[str, Any]:
    """
    Send daily job search digest.

    Args:
        phone_number: Recipient's phone number
        jobs_count: Total jobs found today
        top_jobs: Top 3 jobs with scores

    Returns:
        Notification result dict
    """
    if not top_jobs:
        message = """
🌅 *Daily Job Digest*

No new high-match jobs found today.

💡 Tip: Try adjusting your search criteria or check back tomorrow!

💼 AI Job Hunter Agent
""".strip()
    else:
        header = f"""
🌅 *Daily Job Digest*

Found {jobs_count} new jobs today. Here are your top matches:

---
""".strip()

        job_lines = []
        for i, (job, score) in enumerate(top_jobs[:3], 1):
            title = job.get("title", "Unknown")
            company = job.get("company", "Unknown")
            emoji = "🔥" if score >= 0.85 else "⭐" if score >= 0.75 else "✅"
            job_lines.append(f"{emoji} {i}. {title} @ {company} ({int(score * 100)}%)")

        footer = """

---
🔍 Log in to see all matches
💼 AI Job Hunter Agent
""".strip()

        message = header + "\n\n" + "\n".join(job_lines) + "\n" + footer

    return send_whatsapp_notification(phone_number, message)


# Example usage and testing
if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)

    # Test with sample data
    sample_job = {
        "title": "Senior AI Engineer",
        "company": "TechCorp",
        "location": "Bangalore, India",
        "url": "https://example.com/job/123",
        "portal": "linkedin",
    }

    if len(sys.argv) > 1:
        phone = sys.argv[1]
        print(f"Sending test WhatsApp notification to {phone}")
        result = send_job_notification(phone, sample_job, score=0.87, rank=1)
        print(f"Result: {result}")
    else:
        print("Usage: python whatsapp_service.py <phone_number>")
        print("Example: python whatsapp_service.py +919876543210")
        print("\nFormatted message preview:")
        print(format_job_notification(sample_job, score=0.87, rank=1))
