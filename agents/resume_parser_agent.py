"""
Resume Parser Agent for AI Job Hunter Agent.

Extracts structured candidate information from uploaded resumes.
Steps:
1. Extract raw text from PDF/TXT
2. Use LLM to structure the information
3. Normalize: remove duplicates, convert to lowercase
4. Return structured JSON
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz  # PyMuPDF
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config.settings import settings

logger = logging.getLogger(__name__)

# Expected output schema
RESUME_PROFILE_SCHEMA = {
    "name": "",
    "skills": [],
    "tools": [],
    "frameworks": [],
    "experience_years": "",
    "projects": [],
    "preferred_roles": [],
}


def extract_text_from_pdf(file_path: str) -> Optional[str]:
    """
    Extract raw text from a PDF file using PyMuPDF.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text as string, or None on failure.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("Resume file not found: %s", file_path)
        return None

    if path.suffix.lower() != ".pdf":
        logger.warning("Expected PDF file, got: %s", path.suffix)
        return None

    try:
        doc = fitz.open(file_path)
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        raw_text = "\n".join(text_parts).strip()
        if not raw_text:
            logger.warning("No text extracted from PDF: %s", file_path)
        return raw_text if raw_text else None
    except Exception as e:
        logger.exception("Failed to extract text from PDF: %s", e)
        return None


def extract_text_from_file(file_path: str) -> Optional[str]:
    """
    Extract text from resume file (PDF, TXT, MD).

    Args:
        file_path: Path to the resume file.

    Returns:
        Extracted text or None on failure.
    """
    path = Path(file_path)
    if not path.exists():
        logger.error("File not found: %s", file_path)
        return None

    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return extract_text_from_pdf(file_path)
        if suffix in (".txt", ".md"):
            return path.read_text(encoding="utf-8", errors="ignore").strip()
        logger.warning("Unsupported format: %s", suffix)
        return None
    except Exception as e:
        logger.exception("Failed to read file %s: %s", file_path, e)
        return None


def _extract_json_from_llm_response(text: str) -> dict:
    """
    Parse JSON from LLM response, handling markdown code blocks and extra text.
    """
    # Remove markdown code block if present
    text = text.strip()
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()

    # Find JSON object boundaries
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError as e:
            logger.warning("JSON parse error: %s", e)
    return {}


def parse_resume(file_path: str) -> Optional[str]:
    """
    Extract text content from resume file.

    Convenience alias for extract_text_from_file for backward compatibility.

    Args:
        file_path: Path to resume file.

    Returns:
        Extracted text or None.
    """
    return extract_text_from_file(file_path)


def _normalize_list(items: Any) -> List[str]:
    """Convert to list of strings, dedupe, lowercase."""
    if not isinstance(items, list):
        return []
    seen = set()
    result = []
    for x in items:
        s = str(x).strip().lower()
        if s and s not in seen:
            seen.add(s)
            result.append(s)
    return result


class ResumeParserAgent:
    """
    Agent that parses resume text and extracts structured candidate profile.

    Uses an LLM to convert raw resume text into a standardized JSON schema.
    Output: name, skills, tools, frameworks, experience_years, projects, preferred_roles.
    """

    SYSTEM_PROMPT = """You are a resume parsing expert. Extract structured information from the resume text.

Return ONLY a valid JSON object with exactly these keys (no other text, no markdown):
- name: string - full name of the candidate
- skills: array of strings - technical and soft skills (e.g., Python, Machine Learning, SQL, communication)
- tools: array of strings - development/ops tools (e.g., Git, Docker, AWS, Jira, VS Code)
- frameworks: array of strings - frameworks and libraries (e.g., React, TensorFlow, FastAPI, LangChain)
- experience_years: string - total years of experience (e.g., "2", "1.5", "0-1")
- projects: array of strings - project names or brief descriptions (1 line each)
- preferred_roles: array of strings - job roles that match the candidate's profile (e.g., AI Engineer, ML Engineer)

If a field cannot be determined, use empty string "" or empty array [].
Keep arrays concise and relevant. Extract as much as you can from the resume."""

    def __init__(self, llm: Optional[ChatOpenAI] = None):
        self.llm = llm or ChatOpenAI(
            model=settings.llm_model,
            api_key=settings.openai_api_key,
            temperature=0,
        )

    def parse(self, resume_text: str) -> Dict[str, Any]:
        """
        Convert resume text into structured JSON profile.

        Args:
            resume_text: Raw resume text content.

        Returns:
            Dict with keys: name, skills, tools, frameworks, experience_years, projects, preferred_roles.
        """
        if not resume_text or not resume_text.strip():
            logger.warning("Empty resume text provided")
            return self._empty_profile()

        # Truncate to avoid token limits (keep ~6000 chars for most models)
        text = resume_text[:8000].strip()

        try:
            response = self.llm.invoke(
                [
                    SystemMessage(content=self.SYSTEM_PROMPT),
                    HumanMessage(content=f"Parse this resume:\n\n{text}"),
                ]
            )
            content = response.content if hasattr(response, "content") else str(response)
            parsed = _extract_json_from_llm_response(content)
            return self._normalize_profile(parsed)
        except Exception as e:
            logger.exception("LLM resume parsing failed: %s", e)
            return self._empty_profile()

    def _empty_profile(self) -> Dict[str, Any]:
        """Return schema-compliant empty profile."""
        return dict(RESUME_PROFILE_SCHEMA)

    def _normalize_profile(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure output matches schema: dedupe list fields, convert to lowercase."""
        return {
            "name": str(raw.get("name", "") or "").strip().lower(),
            "skills": _normalize_list(raw.get("skills")),
            "tools": _normalize_list(raw.get("tools")),
            "frameworks": _normalize_list(raw.get("frameworks")),
            "experience_years": str(raw.get("experience_years", "") or "").strip().lower(),
            "projects": _normalize_list(raw.get("projects")),
            "preferred_roles": _normalize_list(raw.get("preferred_roles")),
        }

    def parse_pdf(self, file_path: str) -> dict[str, Any]:
        """
        Load PDF, extract text, and return structured profile.

        Args:
            file_path: Path to resume PDF.

        Returns:
            Structured profile dict.
        """
        text = extract_text_from_pdf(file_path)
        if not text:
            return self._empty_profile()
        return self.parse(text)


def build_candidate_profile_text(profile: Dict[str, Any]) -> str:
    """
    Convert structured profile into optimized text for embedding.

    Produces concise, keyword-rich text suitable for semantic similarity.
    Example: "AI Engineer with 1 year experience. Skills: python, machine learning,
    langchain, rag, vector databases, sql."

    Args:
        profile: Structured profile with name, skills, tools, frameworks,
                 experience_years, projects, preferred_roles.

    Returns:
        Optimized text for embedding.
    """
    if not profile:
        return ""

    parts = []

    # Role and experience
    roles = profile.get("preferred_roles") or []
    role = roles[0] if roles else ""
    exp = str(profile.get("experience_years") or "").strip()
    if role or exp:
        if role and exp:
            suffix = " year experience." if exp == "1" else " years experience."
            parts.append(f"{role} with {exp}{suffix}")
        elif role:
            parts.append(f"{role}.")
        elif exp:
            parts.append(f"{exp} years experience.")

    # Combined skills: skills + tools + frameworks (deduped)
    all_skills = []
    seen = set()
    for key in ("skills", "tools", "frameworks"):
        for item in profile.get(key) or []:
            s = str(item).strip().lower()
            if s and s not in seen:
                seen.add(s)
                all_skills.append(s)
    if all_skills:
        parts.append("Skills: " + ", ".join(all_skills[:30]) + ".")

    return " ".join(parts).strip() or ""


def create_resume_parser_agent(llm: Optional[ChatOpenAI] = None) -> ResumeParserAgent:
    """
    Create ResumeParserAgent for structured extraction via LLM.

    Args:
        llm: Optional LLM instance. Uses settings if None.

    Returns:
        ResumeParserAgent instance.
    """
    return ResumeParserAgent(llm=llm)


# -----------------------------------------------------------------------------
# Example usage
# -----------------------------------------------------------------------------

SAMPLE_RESUME_TEXT = """
John Doe
Email: john.doe@email.com | LinkedIn: linkedin.com/in/johndoe

SUMMARY
Software Engineer with 2 years of experience in ML and backend development.

SKILLS
Python, TensorFlow, PyTorch, FastAPI, SQL, Docker, AWS, Git

EXPERIENCE
- AI Engineer at TechCorp (2022–Present): Built ML pipelines, deployed models.
- Junior Developer at StartupXYZ (2021–2022): REST APIs, data processing.

PROJECTS
- Resume Parser using NLP
- Real-time recommendation engine
"""


def example_usage() -> None:
    """
    Example usage of the Resume Parser Agent.

    Usage:
        # From project root (ai_job_hunter_agent/), with OPENAI_API_KEY set:
        PYTHONPATH=. python agents/resume_parser_agent.py
        PYTHONPATH=. python agents/resume_parser_agent.py path/to/resume.pdf
    """
    import os
    import sys

    logging.basicConfig(level=logging.INFO)

    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. LLM parsing will fail.")
        print("Set it in .env or: export OPENAI_API_KEY=your_key\n")

    agent = ResumeParserAgent()

    # Example 1: Parse from PDF file path
    resume_path = sys.argv[1] if len(sys.argv) > 1 else None

    if resume_path:
        path = Path(resume_path)
        if path.exists():
            profile = agent.parse_pdf(resume_path)
        else:
            print(f"File not found: {resume_path}. Using sample text.\n")
            profile = agent.parse(SAMPLE_RESUME_TEXT)
    else:
        # Example 2: Parse from raw text (no PDF)
        print("No file path provided. Parsing sample resume text.\n")
        profile = agent.parse(SAMPLE_RESUME_TEXT)

    print("Structured profile:")
    print(json.dumps(profile, indent=2))


if __name__ == "__main__":
    example_usage()
