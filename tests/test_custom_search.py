"""
Unit tests for Custom Job Search Agent.

Tests:
- WhatsApp notification formatting
- Custom search agent logic
- Scheduler functionality
- Database operations
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from agents.custom_search_agent import CustomSearchAgent
from notifications.whatsapp_service import (
    format_job_notification,
    format_bulk_job_notification,
)
from notifications.scheduler import JobSearchScheduler


class TestWhatsAppFormatting:
    """Test WhatsApp message formatting."""

    def test_format_single_job_notification(self):
        """Test formatting a single job notification."""
        job = {
            "title": "Senior AI Engineer",
            "company": "TechCorp",
            "location": "Bangalore, India",
            "url": "https://example.com/job/123",
            "portal": "linkedin",
        }
        
        message = format_job_notification(job, score=0.87, rank=1)
        
        assert "Senior AI Engineer" in message
        assert "TechCorp" in message
        assert "Bangalore, India" in message
        assert "https://example.com/job/123" in message
        assert "87%" in message
        assert "Job Match #1" in message
    
    def test_format_bulk_notification(self):
        """Test formatting multiple jobs in one notification."""
        jobs_with_scores = [
            (
                {
                    "title": "AI Engineer",
                    "company": "Company A",
                    "url": "https://example.com/1",
                },
                {"final_score": 0.85},
            ),
            (
                {
                    "title": "ML Engineer",
                    "company": "Company B",
                    "url": "https://example.com/2",
                },
                {"final_score": 0.78},
            ),
        ]
        
        message = format_bulk_job_notification(jobs_with_scores, "resume.pdf")
        
        assert "2 high-match jobs" in message
        assert "AI Engineer" in message
        assert "ML Engineer" in message
        assert "Company A" in message
        assert "Company B" in message
        assert "85%" in message
        assert "78%" in message
    
    def test_score_emoji_selection(self):
        """Test correct emoji based on score."""
        job = {
            "title": "Test Job",
            "company": "Test Co",
            "location": "Test City",
            "url": "https://test.com",
            "portal": "test",
        }
        
        # High score -> fire emoji
        high_score_msg = format_job_notification(job, score=0.88, rank=1)
        assert "🔥" in high_score_msg
        
        # Medium score -> star emoji
        med_score_msg = format_job_notification(job, score=0.76, rank=1)
        assert "⭐" in med_score_msg
        
        # Lower score -> checkmark emoji
        low_score_msg = format_job_notification(job, score=0.65, rank=1)
        assert "✅" in low_score_msg


class TestCustomSearchAgent:
    """Test Custom Search Agent functionality."""

    @patch("agents.custom_search_agent.discover_jobs")
    @patch("agents.custom_search_agent.rank_jobs_with_details")
    @patch("agents.custom_search_agent.send_bulk_job_notifications")
    @patch("agents.custom_search_agent.get_db")
    def test_run_search_success(
        self,
        mock_get_db,
        mock_send_notifications,
        mock_rank,
        mock_discover,
    ):
        """Test successful custom search execution."""
        # Mock database
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        
        mock_resume = Mock()
        mock_resume.id = 1
        mock_resume.file_path = "test_resume.pdf"
        mock_resume.parsed_content = str({
            "skills": ["python", "ml"],
            "preferred_roles": ["AI Engineer"],
        })
        mock_resume.target_role = "AI Engineer"
        mock_resume.experience_years = 2.0
        mock_resume.filename = "resume.pdf"
        
        mock_db.query.return_value.filter.return_value.first.return_value = mock_resume
        
        # Mock job discovery
        mock_discover.return_value = [
            {
                "title": "AI Engineer",
                "company": "TestCorp",
                "url": "https://test.com/job1",
                "location": "Remote",
                "portal": "linkedin",
            }
        ]
        
        # Mock ranking
        mock_rank.return_value = [
            (
                {
                    "title": "AI Engineer",
                    "company": "TestCorp",
                    "url": "https://test.com/job1",
                },
                {"final_score": 0.85, "embedding_score": 0.83, "title_match": 1},
            )
        ]
        
        # Mock notifications
        mock_send_notifications.return_value = {"success": True}
        
        # Run search
        agent = CustomSearchAgent(
            resume_id=1,
            user_phone="+919876543210",
            min_score=0.7,
            max_jobs_per_search=5,
        )
        
        with patch("agents.custom_search_agent.parse_resume", return_value="resume text"):
            result = agent.run_search()
        
        # Assertions
        assert result["success"] is True
        assert result["jobs_found"] == 1
        assert result["jobs_notified"] == 1
        mock_discover.assert_called_once()
        mock_rank.assert_called_once()


class TestScheduler:
    """Test job search scheduler."""

    def test_scheduler_creation(self):
        """Test creating a scheduler instance."""
        scheduler = JobSearchScheduler()
        assert scheduler is not None
        assert not scheduler.is_running()
    
    @patch("notifications.scheduler.BackgroundScheduler")
    def test_add_daily_schedule(self, mock_scheduler_class):
        """Test adding a daily scheduled search."""
        mock_scheduler = MagicMock()
        mock_scheduler_class.return_value = mock_scheduler
        
        scheduler = JobSearchScheduler()
        
        job_id = scheduler.add_scheduled_search(
            resume_id=1,
            user_phone="+919876543210",
            frequency="daily",
            hour=9,
            minute=0,
        )
        
        assert job_id == "search_1"
        mock_scheduler.add_job.assert_called_once()
    
    def test_frequency_parsing(self):
        """Test parsing different frequency options."""
        scheduler = JobSearchScheduler()
        
        # Test various frequencies
        frequencies = ["hourly", "daily", "weekly", "every_4h"]
        
        for freq in frequencies:
            job_id = scheduler.add_scheduled_search(
                resume_id=1,
                user_phone="+919876543210",
                frequency=freq,
            )
            assert job_id == "search_1"


class TestDatabaseModels:
    """Test database model additions."""

    def test_resume_model_fields(self):
        """Test that Resume model has new fields."""
        from database.models import Resume
        
        # Check that new fields exist
        assert hasattr(Resume, "user_phone")
        assert hasattr(Resume, "preferred_location")
        assert hasattr(Resume, "min_match_score")
        assert hasattr(Resume, "notification_enabled")
    
    def test_search_history_model(self):
        """Test SearchHistory model."""
        from database.models import SearchHistory
        
        # Check required fields
        assert hasattr(SearchHistory, "resume_id")
        assert hasattr(SearchHistory, "search_type")
        assert hasattr(SearchHistory, "jobs_found")
        assert hasattr(SearchHistory, "jobs_notified")
        assert hasattr(SearchHistory, "notification_sent")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
