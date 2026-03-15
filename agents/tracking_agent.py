"""
Tracking Agent for AI Job Hunter Agent.

Manages application state, status updates, and tracking across
resumes and jobs in the database.
"""

import logging
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from database.models import Application, Job, Resume

logger = logging.getLogger(__name__)


def create_application(
    db: Session,
    resume_id: int,
    job_id: int,
    status: str = "pending",
    cover_letter: Optional[str] = None,
) -> Application:
    """
    Create a new application record.

    Args:
        db: Database session.
        resume_id: Resume ID.
        job_id: Job ID.
        status: Initial status (e.g., 'pending', 'applied').
        cover_letter: Optional cover letter text.

    Returns:
        Created Application instance.
    """
    app = Application(
        resume_id=resume_id,
        job_id=job_id,
        status=status,
        cover_letter=cover_letter,
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return app


def update_application_status(
    db: Session,
    application_id: int,
    status: str,
    notes: Optional[str] = None,
) -> Optional[Application]:
    """
    Update application status.

    Args:
        db: Database session.
        application_id: Application ID.
        status: New status (applied, rejected, interview, etc.).
        notes: Optional notes.

    Returns:
        Updated Application or None.
    """
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        return None

    app.status = status
    if notes is not None:
        app.notes = notes
    if status == "applied":
        app.applied_at = datetime.utcnow()

    db.commit()
    db.refresh(app)
    return app


def get_applications_by_resume(
    db: Session,
    resume_id: int,
    status: Optional[str] = None,
) -> List[Application]:
    """
    Get all applications for a resume, optionally filtered by status.

    Args:
        db: Database session.
        resume_id: Resume ID.
        status: Optional status filter.

    Returns:
        List of Application instances.
    """
    q = db.query(Application).filter(Application.resume_id == resume_id)
    if status:
        q = q.filter(Application.status == status)
    return q.order_by(Application.created_at.desc()).all()


def get_application_stats(db: Session, resume_id: int) -> dict:
    """
    Get application statistics for a resume.

    Args:
        db: Database session.
        resume_id: Resume ID.

    Returns:
        Dict with counts by status.
    """
    apps = db.query(Application).filter(Application.resume_id == resume_id).all()
    stats = {"total": len(apps), "pending": 0, "applied": 0, "rejected": 0, "interview": 0}
    for app in apps:
        if app.status in stats:
            stats[app.status] += 1
    return stats
