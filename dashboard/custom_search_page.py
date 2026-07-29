"""
Custom Search Dashboard Page for AI Job Hunter Agent.

Allows users to:
1. Upload resume and set WhatsApp number
2. Configure search preferences
3. Run one-time custom search
4. Schedule periodic searches
5. View search history
"""

import logging
from pathlib import Path

import streamlit as st

from config.settings import settings
from database.db import get_db, init_db
from database.models import Resume, SearchHistory
from agents.custom_search_agent import run_custom_search_for_user
from notifications.scheduler import get_scheduler

logger = logging.getLogger(__name__)


def render_custom_search_page():
    """Render the custom search dashboard page."""
    st.title("🔔 Custom Job Search with WhatsApp Notifications")
    
    st.markdown("""
    Upload your resume once, and let AI automatically search for matching jobs and notify you on WhatsApp!
    
    **Features:**
    - 🤖 Autonomous job hunting based on your resume
    - 📱 WhatsApp notifications for high-match jobs
    - ⏰ Schedule periodic searches (hourly, daily, weekly)
    - 📊 Track search history and results
    """)
    
    init_db()
    
    # Sidebar: Resume selection/upload
    with st.sidebar:
        st.header("📄 Your Resume")
        
        db = next(get_db())
        resumes = db.query(Resume).order_by(Resume.created_at.desc()).all()
        
        if resumes:
            resume_options = {
                f"{r.filename} (ID: {r.id})": r.id for r in resumes
            }
            selected = st.selectbox("Select existing resume", list(resume_options.keys()))
            resume_id = resume_options[selected]
            resume = db.query(Resume).filter(Resume.id == resume_id).first()
        else:
            st.info("No resumes found. Upload one below.")
            resume = None
            resume_id = None
        
        # Upload new resume
        with st.expander("➕ Upload New Resume"):
            uploaded_file = st.file_uploader(
                "Upload resume (PDF, TXT)",
                type=["pdf", "txt", "md"],
                key="custom_search_upload",
            )
            target_role = st.text_input("Target Role", value="AI Engineer")
            experience = st.number_input("Years of Experience", min_value=0.0, max_value=30.0, value=2.0)
            phone = st.text_input("WhatsApp Number", placeholder="+919876543210")
            
            if st.button("Upload & Parse"):
                if not uploaded_file:
                    st.error("Please upload a resume")
                elif not phone:
                    st.error("Please enter WhatsApp number")
                else:
                    # Save resume
                    save_dir = Path("data/uploads")
                    save_dir.mkdir(parents=True, exist_ok=True)
                    save_path = save_dir / uploaded_file.name
                    with open(save_path, "wb") as f:
                        f.write(uploaded_file.getvalue())
                    
                    # Parse resume
                    from agents.resume_parser_agent import parse_resume, ResumeParserAgent
                    resume_text = parse_resume(str(save_path))
                    if resume_text:
                        parser = ResumeParserAgent()
                        profile = parser.parse(resume_text)
                        
                        # Save to database
                        new_resume = Resume(
                            filename=uploaded_file.name,
                            file_path=str(save_path),
                            parsed_content=str(profile),
                            target_role=target_role,
                            experience_years=experience,
                            user_phone=phone,
                        )
                        db.add(new_resume)
                        db.commit()
                        
                        st.success(f"✅ Resume uploaded! ID: {new_resume.id}")
                        st.rerun()
                    else:
                        st.error("Failed to parse resume")
    
    if not resume:
        st.warning("Please upload a resume to continue")
        return
    
    # Main content: Tabs for different features
    tab1, tab2, tab3, tab4 = st.tabs(["🔍 One-Time Search", "⏰ Scheduled Search", "📊 Search History", "⚙️ Settings"])
    
    # Tab 1: One-time custom search
    with tab1:
        st.header("Run Custom Search Now")
        st.markdown("Search for jobs matching your resume and get WhatsApp notifications instantly.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            search_location = st.text_input(
                "Location (optional)",
                value=resume.preferred_location or "",
                placeholder="Bangalore, Remote, etc.",
            )
            min_score = st.slider(
                "Minimum Match Score",
                min_value=0.5,
                max_value=1.0,
                value=resume.min_match_score or 0.7,
                step=0.05,
                help="Only notify for jobs above this score",
            )
        
        with col2:
            max_jobs = st.number_input(
                "Max Jobs to Notify",
                min_value=1,
                max_value=20,
                value=5,
                help="Maximum jobs to send in one notification",
            )
            portals = st.multiselect(
                "Job Portals",
                ["linkedin", "indeed", "naukri"],
                default=["linkedin", "indeed", "naukri"],
            )
        
        user_phone = st.text_input(
            "WhatsApp Number",
            value=resume.user_phone or "",
            placeholder="+919876543210",
            help="Format: +[country_code][number]",
        )
        
        if st.button("🚀 Search & Notify Now", type="primary"):
            if not user_phone:
                st.error("Please enter your WhatsApp number")
            elif not portals:
                st.error("Please select at least one job portal")
            else:
                with st.spinner("Searching for jobs and sending notifications..."):
                    try:
                        result = run_custom_search_for_user(
                            resume_id=resume.id,
                            user_phone=user_phone,
                            location=search_location or None,
                            min_score=min_score,
                            max_jobs_per_search=max_jobs,
                            portals=portals if portals else None,
                        )
                        
                        # Save to history
                        history = SearchHistory(
                            resume_id=resume.id,
                            search_type="manual",
                            jobs_found=result.get("jobs_found", 0),
                            jobs_notified=result.get("jobs_notified", 0),
                            location=search_location,
                            min_score=min_score,
                            portals_used=portals,
                            notification_sent=1 if result.get("notification_sent") else 0,
                            error_message=result.get("error"),
                        )
                        db.add(history)
                        db.commit()
                        
                        if result.get("success"):
                            st.success(
                                f"✅ Search completed! Found {result.get('jobs_found', 0)} jobs, "
                                f"notified you about {result.get('jobs_notified', 0)} high matches."
                            )
                            
                            if result.get("jobs"):
                                st.markdown("### Top Matches:")
                                for job in result["jobs"]:
                                    with st.expander(
                                        f"{job['title']} @ {job['company']} - {int(job['score'] * 100)}%"
                                    ):
                                        st.write(f"**Match Score:** {job['score']:.2f}")
                                        st.write(f"**URL:** {job['url']}")
                        else:
                            st.error(f"Search failed: {result.get('error', 'Unknown error')}")
                    
                    except Exception as e:
                        logger.exception("Custom search failed: %s", e)
                        st.error(f"Search failed: {e}")
    
    # Tab 2: Scheduled search
    with tab2:
        st.header("Schedule Automatic Searches")
        st.markdown("Set up periodic job searches that run automatically and notify you on WhatsApp.")
        
        scheduler = get_scheduler()
        
        # Check if search is already scheduled
        scheduled_searches = scheduler.get_scheduled_searches()
        current_schedule = next(
            (s for s in scheduled_searches if s["resume_id"] == resume.id),
            None,
        )
        
        if current_schedule:
            st.success(f"✅ Automatic search is active ({current_schedule['frequency']})")
            
            st.markdown("**Current Settings:**")
            st.write(f"- Frequency: {current_schedule['frequency']}")
            st.write(f"- Time: {current_schedule.get('hour', 9):02d}:{current_schedule.get('minute', 0):02d}")
            st.write(f"- Location: {current_schedule.get('location', 'Any')}")
            st.write(f"- Min Score: {current_schedule.get('min_score', 0.7)}")
            st.write(f"- Phone: {current_schedule.get('user_phone', 'N/A')}")
            
            if st.button("🛑 Stop Scheduled Search"):
                if scheduler.remove_scheduled_search(resume.id):
                    st.success("Scheduled search stopped")
                    st.rerun()
                else:
                    st.error("Failed to stop scheduled search")
        else:
            st.info("No scheduled search active. Configure one below.")
            
            col1, col2 = st.columns(2)
            
            with col1:
                frequency = st.selectbox(
                    "Frequency",
                    ["hourly", "every_4h", "every_12h", "daily", "weekly"],
                    index=3,
                    help="How often to search for new jobs",
                )
                
                if frequency in ["daily", "weekly"]:
                    hour = st.number_input("Hour (24-hour format)", min_value=0, max_value=23, value=9)
                    minute = st.number_input("Minute", min_value=0, max_value=59, value=0)
                else:
                    hour, minute = 9, 0
                
                schedule_location = st.text_input(
                    "Location",
                    value=resume.preferred_location or "",
                    placeholder="Bangalore, Remote, etc.",
                    key="schedule_location",
                )
            
            with col2:
                schedule_min_score = st.slider(
                    "Minimum Score",
                    min_value=0.5,
                    max_value=1.0,
                    value=resume.min_match_score or 0.7,
                    step=0.05,
                    key="schedule_min_score",
                )
                
                schedule_max_jobs = st.number_input(
                    "Max Jobs per Search",
                    min_value=1,
                    max_value=20,
                    value=5,
                    key="schedule_max_jobs",
                )
                
                schedule_portals = st.multiselect(
                    "Portals",
                    ["linkedin", "indeed", "naukri"],
                    default=["linkedin", "indeed"],
                    key="schedule_portals",
                )
            
            schedule_phone = st.text_input(
                "WhatsApp Number",
                value=resume.user_phone or "",
                placeholder="+919876543210",
                key="schedule_phone",
            )
            
            if st.button("⏰ Activate Scheduled Search", type="primary"):
                if not schedule_phone:
                    st.error("Please enter your WhatsApp number")
                else:
                    try:
                        if not scheduler.is_running():
                            scheduler.start()
                        
                        scheduler.add_scheduled_search(
                            resume_id=resume.id,
                            user_phone=schedule_phone,
                            frequency=frequency,
                            location=schedule_location or None,
                            min_score=schedule_min_score,
                            max_jobs_per_search=schedule_max_jobs,
                            portals=schedule_portals if schedule_portals else None,
                            hour=hour,
                            minute=minute,
                        )
                        
                        st.success(f"✅ Scheduled {frequency} search activated!")
                        st.rerun()
                    
                    except Exception as e:
                        logger.exception("Failed to schedule search: %s", e)
                        st.error(f"Failed to schedule: {e}")
    
    # Tab 3: Search history
    with tab3:
        st.header("Search History")
        
        history = (
            db.query(SearchHistory)
            .filter(SearchHistory.resume_id == resume.id)
            .order_by(SearchHistory.executed_at.desc())
            .limit(20)
            .all()
        )
        
        if not history:
            st.info("No search history yet. Run a search to see results here.")
        else:
            st.markdown(f"**Total Searches:** {len(history)}")
            
            for h in history:
                with st.expander(
                    f"{h.executed_at.strftime('%Y-%m-%d %H:%M')} - "
                    f"{h.search_type.title()} - "
                    f"{h.jobs_found} found, {h.jobs_notified} notified"
                ):
                    st.write(f"**Type:** {h.search_type}")
                    st.write(f"**Jobs Found:** {h.jobs_found}")
                    st.write(f"**Jobs Notified:** {h.jobs_notified}")
                    st.write(f"**Location:** {h.location or 'Any'}")
                    st.write(f"**Min Score:** {h.min_score or 0.7}")
                    st.write(f"**Portals:** {', '.join(h.portals_used or [])}")
                    st.write(f"**Notification Sent:** {'✅ Yes' if h.notification_sent else '❌ No'}")
                    if h.error_message:
                        st.error(f"Error: {h.error_message}")
    
    # Tab 4: Settings
    with tab4:
        st.header("Settings")
        
        with st.form("settings_form"):
            st.markdown("**Default Preferences**")
            
            new_phone = st.text_input("WhatsApp Number", value=resume.user_phone or "")
            new_location = st.text_input("Preferred Location", value=resume.preferred_location or "")
            new_min_score = st.slider(
                "Default Min Score",
                min_value=0.5,
                max_value=1.0,
                value=resume.min_match_score or 0.7,
                step=0.05,
            )
            new_target_role = st.text_input("Target Role", value=resume.target_role or "")
            
            if st.form_submit_button("💾 Save Settings"):
                resume.user_phone = new_phone or None
                resume.preferred_location = new_location or None
                resume.min_match_score = new_min_score
                resume.target_role = new_target_role or None
                db.commit()
                st.success("✅ Settings saved!")


if __name__ == "__main__":
    render_custom_search_page()
