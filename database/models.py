"""
SQLAlchemy models for AI Job Hunter Agent.

Defines schema for Resume, Job, Application, and related entities.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON
from sqlalchemy.orm import relationship

from database.db import Base


class Resume(Base):
    """Stored resume metadata and parsed content."""

    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100), nullable=True)
    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    parsed_content = Column(Text, nullable=True)
    target_role = Column(String(255), nullable=True)
    experience_years = Column(Float, nullable=True)
    
    # User preferences for custom search
    user_phone = Column(String(20), nullable=True)  # WhatsApp number
    preferred_location = Column(String(255), nullable=True)
    min_match_score = Column(Float, default=0.7)
    notification_enabled = Column(Integer, default=1)  # 1=enabled, 0=disabled
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = relationship("Application", back_populates="resume")
    search_history = relationship("SearchHistory", back_populates="resume")


class Job(Base):
    """Discovered job listing from various portals."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(String(255), nullable=True, index=True)
    portal = Column(String(50), nullable=False)  # linkedin, naukri, etc.
    title = Column(String(255), nullable=False)
    company = Column(String(255), nullable=True)
    location = Column(String(255), nullable=True)
    url = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    salary_range = Column(String(100), nullable=True)
    posted_date = Column(String(100), nullable=True)
    extra_metadata = Column(JSON, nullable=True)  # Renamed from metadata (SQLAlchemy reserved)
    created_at = Column(DateTime, default=datetime.utcnow)

    applications = relationship("Application", back_populates="job")


class Application(Base):
    """Tracks job application status (resume-job link)."""

    __tablename__ = "applications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(50), default="pending")  # pending, applied, rejected, interview
    applied_at = Column(DateTime, nullable=True)
    cover_letter = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resume = relationship("Resume", back_populates="applications")
    job = relationship("Job", back_populates="applications")


class SearchHistory(Base):
    """Tracks custom search execution history and results."""

    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False)
    search_type = Column(String(50), default="custom")  # custom, scheduled, manual
    jobs_found = Column(Integer, default=0)
    jobs_notified = Column(Integer, default=0)
    location = Column(String(255), nullable=True)
    min_score = Column(Float, nullable=True)
    portals_used = Column(JSON, nullable=True)  # List of portal names
    notification_sent = Column(Integer, default=0)  # 1=sent, 0=failed
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=datetime.utcnow)

    resume = relationship("Resume", back_populates="search_history")
