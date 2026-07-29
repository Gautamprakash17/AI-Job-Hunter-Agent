"""
FastAPI backend for AI Job Hunter Agent.

Provides REST endpoints for resume upload, job discovery,
workflow execution, and application tracking.
"""

import logging
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import settings
from database.db import get_db, init_db
from database.models import Application, Job, Resume
from workflows.job_agent_graph import run_job_hunter_workflow
from agents.custom_search_agent import run_custom_search_for_user
from notifications.scheduler import get_scheduler

logger = logging.getLogger(__name__)

router = APIRouter()

# Ensure data directory exists
UPLOAD_DIR = Path("data/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class JobHunterRequest(BaseModel):
    """Request body for job hunter workflow."""

    resume_path: str
    target_role: str
    location: Optional[str] = None
    experience_years: Optional[float] = None


class JobHunterResponse(BaseModel):
    """Response for job hunter workflow."""

    success: bool
    ranked_jobs: List[dict]
    error: Optional[str] = None


@router.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "ai-job-hunter-agent"}


@router.post("/upload-resume", response_model=dict)
async def upload_resume(file: UploadFile = File(...)):
    """
    Upload a resume file (PDF, TXT) and return stored path.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix.lower()
    if suffix not in (".pdf", ".txt", ".md"):
        raise HTTPException(
            status_code=400,
            detail="Unsupported format. Use PDF, TXT, or MD.",
        )

    dest = UPLOAD_DIR / file.filename
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"path": str(dest), "filename": file.filename}
    except Exception as e:
        logger.exception("Upload failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/run-workflow", response_model=JobHunterResponse)
def run_workflow(request: JobHunterRequest):
    """
    Run the full job hunter workflow: parse resume, discover, rank jobs.
    """
    try:
        result = run_job_hunter_workflow(
            resume_path=request.resume_path,
            target_role=request.target_role,
            location=request.location,
            experience_years=request.experience_years,
        )
        ranked = [
            {"job": job, "score": float(score)}
            for job, score in result.get("ranked_jobs", [])
        ]
        return JobHunterResponse(
            success=result.get("error") is None,
            ranked_jobs=ranked,
            error=result.get("error"),
        )
    except Exception as e:
        logger.exception("Workflow failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/applications")
def list_applications(resume_id: Optional[int] = None, db: Session = Depends(get_db)):
    """List applications, optionally filtered by resume_id."""
    from database.models import Application

    q = db.query(Application)
    if resume_id is not None:
        q = q.filter(Application.resume_id == resume_id)
    apps = q.order_by(Application.created_at.desc()).limit(100).all()
    return [
        {
            "id": a.id,
            "resume_id": a.resume_id,
            "job_id": a.job_id,
            "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
        }
        for a in apps
    ]


@router.get("/jobs")
def list_jobs(limit: int = 50, db: Session = Depends(get_db)):
    """List discovered jobs."""
    jobs = db.query(Job).order_by(Job.created_at.desc()).limit(limit).all()
    return [
        {
            "id": j.id,
            "title": j.title,
            "company": j.company,
            "portal": j.portal,
            "url": j.url,
        }
        for j in jobs
    ]


class CustomSearchRequest(BaseModel):
    """Request body for custom job search with WhatsApp notifications."""

    resume_id: int
    user_phone: str  # Format: +1234567890
    location: Optional[str] = None
    min_score: float = 0.7
    max_jobs_per_search: int = 5
    portals: Optional[List[str]] = None


class ScheduleSearchRequest(BaseModel):
    """Request body for scheduling periodic job searches."""

    resume_id: int
    user_phone: str
    frequency: str = "daily"  # hourly, daily, weekly, every_4h, etc.
    location: Optional[str] = None
    min_score: float = 0.7
    max_jobs_per_search: int = 5
    portals: Optional[List[str]] = None
    hour: int = 9  # Hour for daily/weekly (0-23)
    minute: int = 0  # Minute (0-59)


@router.post("/custom-search")
def run_custom_search(request: CustomSearchRequest):
    """
    Run custom job search and send WhatsApp notifications.
    
    Searches for jobs based on user's resume, ranks them,
    and sends top matches via WhatsApp.
    """
    try:
        result = run_custom_search_for_user(
            resume_id=request.resume_id,
            user_phone=request.user_phone,
            location=request.location,
            min_score=request.min_score,
            max_jobs_per_search=request.max_jobs_per_search,
            portals=request.portals,
        )
        return result
    except Exception as e:
        logger.exception("Custom search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/schedule-search")
def schedule_search(request: ScheduleSearchRequest):
    """
    Schedule periodic job searches with WhatsApp notifications.
    
    Sets up automatic job searching at specified intervals.
    """
    try:
        scheduler = get_scheduler()
        
        # Start scheduler if not running
        if not scheduler.is_running():
            scheduler.start()
        
        job_id = scheduler.add_scheduled_search(
            resume_id=request.resume_id,
            user_phone=request.user_phone,
            frequency=request.frequency,
            location=request.location,
            min_score=request.min_score,
            max_jobs_per_search=request.max_jobs_per_search,
            portals=request.portals,
            hour=request.hour,
            minute=request.minute,
        )
        
        return {
            "success": True,
            "job_id": job_id,
            "message": f"Scheduled {request.frequency} search for resume_id={request.resume_id}",
        }
    except Exception as e:
        logger.exception("Schedule search failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/schedule-search/{resume_id}")
def remove_scheduled_search(resume_id: int):
    """Remove scheduled job search for a resume."""
    try:
        scheduler = get_scheduler()
        if scheduler.remove_scheduled_search(resume_id):
            return {
                "success": True,
                "message": f"Removed scheduled search for resume_id={resume_id}",
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"No scheduled search found for resume_id={resume_id}",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Remove schedule failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scheduled-searches")
def list_scheduled_searches():
    """List all scheduled job searches."""
    try:
        scheduler = get_scheduler()
        searches = scheduler.get_scheduled_searches()
        return {
            "success": True,
            "count": len(searches),
            "searches": searches,
        }
    except Exception as e:
        logger.exception("List schedules failed: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/resumes")
def list_resumes(limit: int = 50, db: Session = Depends(get_db)):
    """List uploaded resumes."""
    resumes = db.query(Resume).order_by(Resume.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "filename": r.filename,
            "target_role": r.target_role,
            "experience_years": r.experience_years,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in resumes
    ]


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    init_db()
    app = FastAPI(
        title="AI Job Hunter Agent API",
        description="REST API for job discovery, ranking, and application tracking.",
        version="0.1.0",
    )
    app.include_router(router, prefix="/api", tags=["job-hunter"])
    return app


app = create_app()
