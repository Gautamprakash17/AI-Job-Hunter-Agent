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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications = relationship("Application", back_populates="resume")


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
