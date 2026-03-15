"""
Database module for AI Job Hunter Agent.

Provides SQLite connection, session management, and table definitions
for resumes, jobs, applications, and tracking state.
"""

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from config.settings import settings

logger = logging.getLogger(__name__)

Base = declarative_base()

# Create engine with SQLite
engine = create_engine(
    f"sqlite:///{settings.db_path}",
    connect_args={"check_same_thread": False},
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# -----------------------------------------------------------------------------
# Job application tracking (job_applications table)
# Columns: job_id, company, role, portal, status, date_applied
# -----------------------------------------------------------------------------

_APPLICATIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL,
    company TEXT,
    role TEXT,
    portal TEXT,
    status TEXT DEFAULT 'pending',
    date_applied TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id, portal)
)
"""


def _get_tracking_connection() -> sqlite3.Connection:
    """Get a connection for the applications tracking table."""
    path = str(settings.db_path)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables() -> None:
    """
    Create the job_applications table if it does not exist.
    Prevents duplicate applications via UNIQUE(job_id, portal).
    """
    conn = _get_tracking_connection()
    try:
        conn.execute(_APPLICATIONS_SCHEMA)
        conn.commit()
        logger.info("Created/verified job_applications table at %s", settings.db_path)
    finally:
        conn.close()


def save_application(job: Dict[str, Any]) -> bool:
    """
    Save a job application. Prevents duplicates by (job_id, portal).

    Args:
        job: Dict with keys job_id, company, role, portal, status, date_applied.
             job_id and portal are required for deduplication.

    Returns:
        True if saved, False if duplicate (already applied).
    """
    job_id = str(job.get("job_id") or "")
    portal = str(job.get("portal") or "unknown")
    if not job_id:
        logger.warning("save_application: job_id is required, skipping")
        return False

    company = job.get("company") or ""
    role = job.get("role") or job.get("title") or ""
    status = job.get("status") or "pending"
    date_applied = job.get("date_applied")
    if date_applied is None:
        date_applied = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    elif hasattr(date_applied, "strftime"):
        date_applied = date_applied.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_applied = str(date_applied)

    conn = _get_tracking_connection()
    try:
        conn.execute(
            """
            INSERT INTO job_applications (job_id, company, role, portal, status, date_applied)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, company, role, portal, status, date_applied),
        )
        conn.commit()
        logger.info("Saved application: job_id=%s, company=%s", job_id, company)
        return True
    except sqlite3.IntegrityError as e:
        if "UNIQUE" in str(e):
            logger.debug("Duplicate application ignored: job_id=%s portal=%s", job_id, portal)
            return False
        raise
    finally:
        conn.close()


def save_or_update_application(job: Dict[str, Any]) -> bool:
    """
    Insert or update application by (job_id, portal).
    Updates status if record exists; inserts if new.

    Args:
        job: Dict with keys job_id, company, role, portal, status, date_applied.

    Returns:
        True if saved or updated.
    """
    job_id = str(job.get("job_id") or "")
    portal = str(job.get("portal") or "unknown")
    if not job_id:
        logger.warning("save_or_update_application: job_id is required, skipping")
        return False

    company = job.get("company") or ""
    role = job.get("role") or job.get("title") or ""
    status = job.get("status") or "pending"
    date_applied = job.get("date_applied")
    if date_applied is None:
        date_applied = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    elif hasattr(date_applied, "strftime"):
        date_applied = date_applied.strftime("%Y-%m-%d %H:%M:%S")
    else:
        date_applied = str(date_applied)

    conn = _get_tracking_connection()
    try:
        cur = conn.execute(
            "UPDATE job_applications SET company=?, role=?, status=?, date_applied=? WHERE job_id=? AND portal=?",
            (company, role, status, date_applied, job_id, portal),
        )
        if cur.rowcount > 0:
            conn.commit()
            logger.info("Updated application: job_id=%s, status=%s", job_id, status)
            return True
        conn.execute(
            """
            INSERT INTO job_applications (job_id, company, role, portal, status, date_applied)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, company, role, portal, status, date_applied),
        )
        conn.commit()
        logger.info("Saved application: job_id=%s, company=%s", job_id, company)
        return True
    finally:
        conn.close()


def check_if_applied(job_id: str, portal: Optional[str] = None) -> bool:
    """
    Check if an application already exists for the given job.

    Args:
        job_id: Job identifier (external ID from portal).
        portal: Optional portal name. If given, checks (job_id, portal).
                If None, checks any row with this job_id.

    Returns:
        True if already applied, False otherwise.
    """
    conn = _get_tracking_connection()
    try:
        if portal is not None:
            row = conn.execute(
                "SELECT 1 FROM job_applications WHERE job_id = ? AND portal = ?",
                (str(job_id), str(portal)),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT 1 FROM job_applications WHERE job_id = ?",
                (str(job_id),),
            ).fetchone()
        return row is not None
    finally:
        conn.close()


def get_all_applications() -> List[Dict[str, Any]]:
    """
    Return all applications, ordered by date_applied descending.

    Returns:
        List of dicts with job_id, company, role, portal, status, date_applied.
    """
    create_tables()
    conn = _get_tracking_connection()
    try:
        rows = conn.execute(
            """
            SELECT job_id, company, role, portal, status, date_applied, created_at
            FROM job_applications
            ORDER BY COALESCE(date_applied, created_at) DESC
            """
        ).fetchall()
        return [
            {
                "job_id": r["job_id"],
                "company": r["company"],
                "role": r["role"],
                "portal": r["portal"],
                "status": r["status"],
                "date_applied": r["date_applied"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# SQLAlchemy session management
# -----------------------------------------------------------------------------


def init_db() -> None:
    """
    Initialize database tables.

    Creates applications tracking table and SQLAlchemy models if they do not exist.
    """
    create_tables()
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized at %s", settings.db_path)


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Provide a transactional scope around a series of operations.

    Yields a database session and ensures proper commit/rollback
    and connection cleanup.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency for database session.

    Yields a session for the request lifecycle.
    """
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
