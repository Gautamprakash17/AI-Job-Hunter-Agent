"""
Application Agent for AI Job Hunter Agent.

Auto Job Application Agent: applies to jobs only when the portal supports
quick apply (e.g., LinkedIn Easy Apply, Indeed Apply Now). If the job
redirects to an external site, marks as manual_apply_needed.

Portal-specific automation:
- linkedin_easy_apply(): LinkedIn Easy Apply / Apply now
- indeed_apply(): Indeed Apply Now / Easily apply
- Other portals → manual_apply_needed
"""

import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from config.settings import settings
from tools.browser_automation import (
    get_browser,
    get_browser_context,
    navigate_and_wait,
)

logger = logging.getLogger(__name__)

# Timeout (ms) for finding quick apply button - if not found, assume manual apply
BUTTON_TIMEOUT_MS = 5000

# Text that indicates external redirect (do NOT auto-apply)
EXTERNAL_REDIRECT_INDICATORS = [
    "apply on company website",
    "apply on company site",
    "company website",
]

# Resume upload input selector
RESUME_INPUT_SELECTOR = "input[type='file']"

# -----------------------------------------------------------------------------
# Cover Letter Generation
# -----------------------------------------------------------------------------


def generate_cover_letter(
    job_title: str,
    company: str,
    resume_summary: str,
    llm: Optional[ChatOpenAI] = None,
) -> str:
    """
    Generate a tailored cover letter for a job application.

    Args:
        job_title: Target job title.
        company: Company name.
        resume_summary: Resume summary for personalization.
        llm: Optional LLM instance.

    Returns:
        Generated cover letter text.
    """
    llm = llm or ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.openai_api_key,
        temperature=0.7,
    )

    prompt = f"""Write a concise, professional cover letter (150-200 words) for:
Job: {job_title}
Company: {company}

Candidate background (use to tailor): {resume_summary[:500]}

Keep it professional, avoid generic phrases, highlight relevant fit."""

    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        return response.content if hasattr(response, "content") else str(response)
    except Exception as e:
        logger.exception("Cover letter generation failed: %s", e)
        return ""


# -----------------------------------------------------------------------------
# Shared Helpers
# -----------------------------------------------------------------------------


def _page_contains_text(page: Page, text_patterns: List[str]) -> bool:
    """Check if page body contains any of the given text patterns (case-insensitive)."""
    try:
        body = page.query_selector("body")
        if not body:
            return False
        text = (body.text_content() or "").lower()
        return any(p.lower() in text for p in text_patterns)
    except Exception:
        return False


def _upload_resume_if_present(page: Page, resume_path: str) -> bool:
    """
    Find file input and upload resume using page.set_input_files.
    Returns True if upload succeeded.
    """
    path = Path(resume_path).resolve()
    if not path.exists():
        logger.warning("Resume file not found: %s", resume_path)
        return False

    try:
        page.set_input_files(RESUME_INPUT_SELECTOR, str(path), timeout=BUTTON_TIMEOUT_MS)
        logger.info("Uploaded resume via %s", RESUME_INPUT_SELECTOR)
        return True
    except Exception as e:
        logger.debug("Resume upload failed: %s", e)
    return False


def _attempt_submit(page: Page) -> bool:
    """
    Look for and click Submit/Next/Continue/Review button.
    Returns True if a submit-like action was performed.
    """
    submit_selectors = [
        "button:has-text('Submit')",
        "button:has-text('Submit application')",
        "button[aria-label*='Submit']",
        "button:has-text('Review')",
        "button:has-text('Next')",
        "button:has-text('Continue')",
    ]
    for sel in submit_selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=2000)
            loc.click()
            time.sleep(1)
            return True
        except Exception:
            pass
    return False


# -----------------------------------------------------------------------------
# Portal-Specific Automation
# -----------------------------------------------------------------------------


def linkedin_easy_apply(
    page: Page,
    job: Dict[str, Any],
    resume_path: str,
    timeout: int = BUTTON_TIMEOUT_MS,
) -> Tuple[str, str]:
    """
    LinkedIn Easy Apply automation.

    Detects buttons: "Easy Apply", "Apply now".
    Uses Playwright selectors: page.get_by_text, page.locator.
    If button not found within timeout, returns manual_apply_needed.

    Returns:
        (status, message) - status: "applied" | "manual_apply_needed" | "failed"
    """
    try:
        # Check for external redirect
        if _page_contains_text(page, EXTERNAL_REDIRECT_INDICATORS):
            return ("manual_apply_needed", "Job requires application on company website")

        # Detect Easy Apply / Apply now buttons (5s timeout)
        apply_btn = None
        for text in ["Easy Apply", "Apply now"]:
            try:
                loc = page.get_by_text(text, exact=False).first
                loc.wait_for(state="visible", timeout=timeout)
                apply_btn = loc
                break
            except PlaywrightTimeout:
                continue

        if not apply_btn:
            try:
                loc = page.locator("button:has-text('Apply')").first
                loc.wait_for(state="visible", timeout=timeout)
                apply_btn = loc
            except PlaywrightTimeout:
                pass

        if not apply_btn:
            return ("manual_apply_needed", "No Easy Apply or Apply now button found")

        # Click apply button
        apply_btn.click()
        time.sleep(2)

        # Upload resume
        _upload_resume_if_present(page, resume_path)
        time.sleep(1)

        # Attempt submit
        if _attempt_submit(page):
            return ("applied", "Application submitted")
        return ("manual_apply_needed", "Apply clicked but submit not completed")

    except Exception as e:
        logger.exception("LinkedIn easy apply failed: %s", e)
        return ("failed", str(e))


def indeed_apply(
    page: Page,
    job: Dict[str, Any],
    resume_path: str,
    timeout: int = BUTTON_TIMEOUT_MS,
) -> Tuple[str, str]:
    """
    Indeed Apply automation.

    Detects buttons: "Apply Now", "Easily apply".
    If button not found within timeout, returns manual_apply_needed.

    Returns:
        (status, message) - status: "applied" | "manual_apply_needed" | "failed"
    """
    try:
        # Check for external redirect
        if _page_contains_text(page, EXTERNAL_REDIRECT_INDICATORS):
            return ("manual_apply_needed", "Job requires application on company website")

        # Detect Apply Now / Easily apply buttons (5s timeout)
        apply_btn = None
        for text in ["Apply Now", "Easily apply"]:
            try:
                loc = page.get_by_text(text, exact=False).first
                loc.wait_for(state="visible", timeout=timeout)
                apply_btn = loc
                break
            except PlaywrightTimeout:
                continue

        if not apply_btn:
            try:
                loc = page.locator("button:has-text('Apply')").first
                loc.wait_for(state="visible", timeout=timeout)
                apply_btn = loc
            except PlaywrightTimeout:
                pass

        if not apply_btn:
            return ("manual_apply_needed", "No Apply Now or Easily apply button found")

        # Click apply button
        apply_btn.click()
        time.sleep(2)

        # Upload resume
        _upload_resume_if_present(page, resume_path)
        time.sleep(1)

        # Attempt submit
        if _attempt_submit(page):
            return ("applied", "Application submitted")
        return ("manual_apply_needed", "Apply clicked but submit not completed")

    except Exception as e:
        logger.exception("Indeed apply failed: %s", e)
        return ("failed", str(e))


# -----------------------------------------------------------------------------
# Main Application Function
# -----------------------------------------------------------------------------


def apply_to_job(
    job: Dict[str, Any],
    resume_path: str,
    headless: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Apply to a job if it supports quick apply; otherwise mark as manual_apply_needed.

    Routes by portal:
    - linkedin → linkedin_easy_apply()
    - indeed → indeed_apply()
    - else → manual_apply_needed

    Returns status: "applied" | "manual_apply_needed" | "failed".

    Args:
        job: Job dict with keys: url, company, portal, external_id/title.
        resume_path: Path to resume file (PDF preferred).
        headless: Override settings; default uses application_headless (False for debugging).

    Returns:
        {job_id, company, portal, status, message}
    """
    job_id = str(job.get("external_id") or job.get("url", "") or "")
    company = str(job.get("company") or "")
    portal = str(job.get("portal") or "unknown").lower()
    url = str(job.get("url") or "").strip()

    result: Dict[str, Any] = {
        "job_id": job_id,
        "company": company,
        "portal": portal,
        "status": "failed",
    }

    if not url or url.startswith("https://example.com"):
        result["status"] = "manual_apply_needed"
        result["message"] = "Invalid or demo URL"
        return result

    # Unknown portal → manual_apply_needed without opening browser
    if portal not in ("linkedin", "indeed"):
        result["status"] = "manual_apply_needed"
        result["message"] = f"Portal '{portal}' not supported for automation"
        logger.info("Job %s: portal %s requires manual apply", job_id, portal)
        return result

    use_headless = headless if headless is not None else getattr(
        settings, "application_headless", False
    )

    try:
        with get_browser(headless=use_headless) as browser:
            with get_browser_context(browser) as context:
                page = context.new_page()

                if not navigate_and_wait(page, url):
                    result["status"] = "failed"
                    result["message"] = "Failed to load job page"
                    return result

                time.sleep(2)  # Allow dynamic content

                # Route to portal-specific automation
                if portal == "linkedin":
                    status, message = linkedin_easy_apply(
                        page, job, resume_path, timeout=BUTTON_TIMEOUT_MS
                    )
                elif portal == "indeed":
                    status, message = indeed_apply(
                        page, job, resume_path, timeout=BUTTON_TIMEOUT_MS
                    )
                else:
                    status = "manual_apply_needed"
                    message = f"Portal '{portal}' not supported"

                result["status"] = status
                result["message"] = message

                if status == "applied":
                    logger.info("Applied to job %s at %s", job_id, company)

                page.close()

    except Exception as e:
        logger.exception("Application failed for job %s: %s", job_id, e)
        result["status"] = "failed"
        result["message"] = str(e)

    return result


def apply_to_jobs(
    jobs: List[Dict[str, Any]],
    resume_path: str,
    headless: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """
    Apply to multiple jobs. Returns list of results from apply_to_job.
    """
    results = []
    for job in jobs:
        r = apply_to_job(job, resume_path, headless=headless)
        results.append(r)
        time.sleep(1)  # Rate limit between jobs
    return results
