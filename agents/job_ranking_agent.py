"""
Job Ranking Agent for AI Job Hunter Agent.

Ranks jobs using semantic similarity between candidate profile and job descriptions.
Uses LangChain embeddings; computes cosine similarity directly for reliable 0-1 scores.
"""

import logging
import re
from math import sqrt
from typing import Any, Dict, List, Optional, Set, Union

from rag.embeddings import embed_query, embed_texts

from agents.resume_parser_agent import build_candidate_profile_text

logger = logging.getLogger(__name__)

# Minimum similarity score to keep a job
MIN_SIMILARITY_SCORE = 0.5

# Ranking weights: embedding_similarity, title_match only (no skill overlap)
RANKING_WEIGHTS = (0.8, 0.2)

# Common target role keywords for title match (case-insensitive)
TITLE_MATCH_KEYWORDS = [
    "ai engineer", "machine learning engineer", "ml engineer", "llm engineer",
    "data scientist", "research scientist", "software engineer", "backend engineer",
    "full stack", "frontend engineer", "devops engineer", "data engineer",
]

# Section headers that typically start benefits/marketing content to remove
BENEFITS_SECTION_HEADERS = (
    r"\b(?:benefits|perks|compensation|why (?:join|work with) us|what we offer"
    r"|our benefits|employee benefits|we offer|life at|culture|about us"
    r"|company overview|equal opportunity|eoe|diversity|apply now|how to apply)\b"
)
# Common marketing filler (case-insensitive)
MARKETING_PATTERNS = [
    r"\b(?:join our|we are a|we're a|leading (?:provider|company|organization)|"
    r"fast-?paced (?:environment|team)|dynamic (?:environment|team)|"
    r"cutting-?edge|best-?in-?class|world-?class|innovative (?:company|team)|"
    r"mission-?driven|results-?oriented|team-?oriented|collaborative (?:culture|environment)|"
    r"great (?:place to work|culture|team)|exciting (?:opportunity|role)|"
    r"apply (?:today|now|at)\s*\S*)\b",
    r"https?://[^\s]+",  # URLs
]
_URL_PATTERN = re.compile(r"https?://[^\s)\]]+", re.IGNORECASE)


def clean_job_description(text: str) -> str:
    """
    Clean job description for better embedding quality.

    Removes:
    - URLs
    - Company marketing fluff
    - Benefits/perks sections

    Keeps: role-relevant content (responsibilities, required skills, tech stack).

    Args:
        text: Raw job description.

    Returns:
        Cleaned text suitable for embedding.
    """
    if not text or not text.strip():
        return ""

    t = text.strip()

    # 1. Remove URLs
    t = _URL_PATTERN.sub(" ", t)

    # 2. Remove benefits sections (from header to next ## or end)
    t = re.sub(
        rf"(?i)\n\s*[#\-\*]*\s*{BENEFITS_SECTION_HEADERS}[^\n]*(\n(?![#\-\*]).*)*",
        "\n",
        t,
    )

    # 3. Remove marketing phrases
    for pat in MARKETING_PATTERNS:
        t = re.sub(pat, " ", t, flags=re.IGNORECASE)

    # Normalize whitespace
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _extract_skills_from_text(text: str, max_terms: int = 25) -> List[str]:
    """Extract skill-like terms for embedding (lowercase, deduped)."""
    if not text:
        return []
    stop = {
        "the", "and", "for", "with", "or", "to", "of", "in", "on", "at", "by",
        "is", "are", "be", "have", "has", "will", "years", "experience", "required",
        "preferred", "etc", "e.g", "including", "such", "as", "this", "that",
    }
    # Split on punctuation and spaces; keep words 2-40 chars, alphanumeric/hyphen
    words = re.findall(r"[a-zA-Z0-9][a-zA-Z0-9\-]{1,39}", text)
    seen: Set[str] = set()
    out: List[str] = []
    for w in words:
        lower = w.lower()
        if lower in stop or lower in seen or len(lower) < 2:
            continue
        seen.add(lower)
        out.append(lower)
        if len(out) >= max_terms:
            break
    return out


def job_to_embedding_text(job: Dict[str, Any]) -> str:
    """
    Convert job dict into embedding-optimized text.

    Format: "{title} role requiring {skills}."
    Example: "AI Engineer role requiring python, machine learning, langchain, llm, vector database experience."

    Args:
        job: Dict with title, company, description.

    Returns:
        Optimized text for embedding.
    """
    title = str(job.get("title") or "").strip()
    desc = str(job.get("description") or "").strip()
    cleaned = clean_job_description(desc)
    skills = _extract_skills_from_text(cleaned)
    if skills:
        skills_str = ", ".join(skills)
        if title:
            return f"{title} role requiring {skills_str}."
        return f"Role requiring {skills_str}."
    # Fallback: use cleaned text (truncated)
    if cleaned:
        snippet = cleaned[:400].strip()
        if title:
            return f"{title} role. {snippet}"
        return snippet
    return title or "Job"


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x**2 for x in a))
    norm_b = sqrt(sum(x**2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _compute_title_match(job_title: str, target_roles: List[str]) -> float:
    """
    Title match score: 1 if job title contains target role keywords, else 0.

    Uses preferred_roles from profile plus common TITLE_MATCH_KEYWORDS.

    Args:
        job_title: Job title string.
        target_roles: Preferred roles from candidate profile.

    Returns:
        1.0 or 0.0.
    """
    if not job_title:
        return 0.0
    title_lower = job_title.lower()
    keywords = [r.lower() for r in target_roles if r] + TITLE_MATCH_KEYWORDS
    for kw in keywords:
        if kw in title_lower:
            return 1.0
    return 0.0


def _compute_final_score(
    embedding_sim: float,
    title_match: float,
    weights: tuple = RANKING_WEIGHTS,
) -> float:
    """Combine scores: 0.8 * embedding_similarity + 0.2 * title_match."""
    w_emb, w_title = weights
    return w_emb * embedding_sim + w_title * title_match


def profile_to_text(profile: Dict[str, Any]) -> str:
    """
    Convert candidate profile dict into a single text for embedding.

    Uses build_candidate_profile_text for optimized embedding output when
    profile has structured fields (skills, tools, frameworks, etc.).

    Args:
        profile: Dict from resume parser with name, skills, tools, frameworks,
                 experience_years, projects, preferred_roles.

    Returns:
        Optimized text representation for embedding.
    """
    text = build_candidate_profile_text(profile)
    if text:
        return text
    # Fallback for minimal profiles
    if not profile:
        return ""
    parts = [
        str(profile.get("name", "") or ""),
        " ".join(profile.get("skills", []) or []),
        str(profile.get("experience_years", "") or ""),
        " ".join(profile.get("preferred_roles", []) or []),
        " ".join(str(p) for p in (profile.get("projects", []) or [])[:5]),
    ]
    return " ".join(filter(None, parts)).strip()


def rank_jobs(
    jobs: List[dict],
    candidate_profile: Dict[str, Any],
    min_score: float = MIN_SIMILARITY_SCORE,
    top_k: Optional[int] = None,
) -> List[dict]:
    """
    Rank jobs using embedding similarity + title match only.

    Final score: 0.8 * embedding_similarity + 0.2 * title_match (no skill overlap).

    Args:
        jobs: List of job dicts with title, company, description.
        candidate_profile: Parsed resume profile (preferred_roles used for title match).
        min_score: Minimum similarity threshold.
        top_k: Maximum jobs to return. None = return all above threshold.

    Returns:
        List of dicts: [{"job": "AI Engineer - Amazon", "score": 0.87}, ...]
    """
    if not jobs:
        return []

    profile_text = profile_to_text(candidate_profile)
    if not profile_text.strip():
        profile_text = "Software Engineer"  # Fallback

    target_roles = [r for r in (candidate_profile.get("preferred_roles") or []) if r]

    job_texts = [job_to_embedding_text(job) or (job.get("title") or "Job") for job in jobs]
    query_embedding = embed_query(profile_text)
    job_embeddings = embed_texts(job_texts)

    scored: List[tuple] = []
    for i, job in enumerate(jobs):
        emb_sim = _cosine_similarity(query_embedding, job_embeddings[i])
        title_match = _compute_title_match(job.get("title") or "", target_roles)
        final_score = _compute_final_score(emb_sim, title_match)
        score_breakdown = {
            "final_score": round(final_score, 2),
            "embedding_score": round(emb_sim, 2),
            "title_match": int(title_match),
        }
        scored.append((job, final_score, score_breakdown))

    scored.sort(key=lambda x: x[1], reverse=True)

    ranked: List[dict] = []
    for job, score, breakdown in scored:
        if score < min_score:
            continue

        title = job.get("title", "")
        company = job.get("company", "")
        job_label = f"{title} - {company}".strip(" - ") or "Unknown"
        ranked.append({
            "job": job_label,
            "score": breakdown["final_score"],
            "final_score": breakdown["final_score"],
            "embedding_score": breakdown["embedding_score"],
            "title_match": breakdown["title_match"],
            "_job": job,
            "_score_breakdown": breakdown,
        })

        if top_k is not None and len(ranked) >= top_k:
            break

    if min_score > 0 or top_k is not None:
        logger.info("Ranked %d jobs (min_score=%.2f, top_k=%s) from %d total", len(ranked), min_score, top_k, len(jobs))
    else:
        logger.info("Ranked all %d jobs by relevance", len(ranked))
    return ranked


def rank_jobs_with_details(
    jobs: List[dict],
    candidate_profile: Dict[str, Any],
    min_score: float = MIN_SIMILARITY_SCORE,
    top_k: Optional[int] = None,
) -> List[tuple]:
    """
    Rank jobs and return full job dicts with score breakdown (for pipeline use).

    Returns:
        List of (job_dict, score_info) tuples, sorted by final_score descending.
        score_info: {final_score, embedding_score, title_match}
    """
    ranked_output = rank_jobs(
        jobs=jobs,
        candidate_profile=candidate_profile,
        min_score=min_score,
        top_k=top_k,
    )

    result = []
    for item in ranked_output:
        breakdown = item.get("_score_breakdown", {})
        score_info = {
            "final_score": item.get("final_score", item.get("score", 0)),
            "embedding_score": item.get("embedding_score", 0),
            "title_match": item.get("title_match", 0),
        }
        job_dict = item.get("_job")
        if job_dict is not None:
            result.append((job_dict, score_info))
        else:
            label = item["job"]
            for j in jobs:
                j_label = f"{j.get('title','')} - {j.get('company','')}".strip(" - ")
                if j_label == label:
                    result.append((j, score_info))
                    break

    return result


def rank_jobs_by_role(
    jobs: List[dict],
    target_role: str,
    min_score: float = MIN_SIMILARITY_SCORE,
    top_k: Optional[int] = None,
) -> List[dict]:
    """
    Rank jobs by semantic similarity between target role and job description.

    Does NOT use resume or skill extraction. Role-based only.

    Args:
        jobs: List of job dicts with title, company, description.
        target_role: Target job role (e.g., "AI Engineer").
        min_score: Minimum similarity threshold.
        top_k: Maximum jobs to return.

    Returns:
        List of dicts: [{"job": "...", "score": 0.87, ...}]
    """
    if not jobs:
        return []

    query_text = (target_role or "Software Engineer").strip()
    query_embedding = embed_query(query_text)

    job_texts = [job_to_embedding_text(j) or (j.get("title") or "Job") for j in jobs]
    job_embeddings = embed_texts(job_texts)

    target_roles_list = [target_role] if target_role else []
    scored: List[tuple] = []
    for i, job in enumerate(jobs):
        emb_sim = _cosine_similarity(query_embedding, job_embeddings[i])
        title_match = _compute_title_match(job.get("title") or "", target_roles_list)
        final = _compute_final_score(emb_sim, title_match)
        scored.append((job, emb_sim, title_match, final))
    scored.sort(key=lambda x: x[3], reverse=True)

    ranked: List[dict] = []
    for job, emb_sim, title_match, final in scored:
        if final < min_score:
            continue
        title, company = job.get("title", ""), job.get("company", "")
        job_label = f"{title} - {company}".strip(" - ") or "Unknown"
        ranked.append({
            "job": job_label,
            "score": round(final, 2),
            "final_score": round(final, 2),
            "embedding_score": round(emb_sim, 2),
            "title_match": int(title_match),
            "_job": job,
            "_score_breakdown": {
                "final_score": round(final, 2),
                "embedding_score": round(emb_sim, 2),
                "title_match": int(title_match),
            },
        })
        if top_k is not None and len(ranked) >= top_k:
            break

    logger.info("Ranked %d jobs by role '%s'", len(ranked), target_role)
    return ranked


def rank_jobs_by_role_with_details(
    jobs: List[dict],
    target_role: str,
    min_score: float = MIN_SIMILARITY_SCORE,
    top_k: Optional[int] = None,
) -> List[tuple]:
    """Rank jobs by role, return (job_dict, score_info). No resume dependency."""
    ranked_output = rank_jobs_by_role(jobs=jobs, target_role=target_role, min_score=min_score, top_k=top_k)
    result = []
    for item in ranked_output:
        breakdown = item.get("_score_breakdown", {})
        score_info = {
            "final_score": item.get("final_score", item.get("score", 0)),
            "embedding_score": item.get("embedding_score", 0),
            "title_match": item.get("title_match", 0),
        }
        if breakdown:
            score_info["final_score"] = breakdown.get("final_score", score_info["final_score"])
            score_info["embedding_score"] = breakdown.get("embedding_score", score_info["embedding_score"])
            score_info["title_match"] = breakdown.get("title_match", score_info["title_match"])
        job_dict = item.get("_job")
        if job_dict is not None:
            result.append((job_dict, score_info))
        else:
            for j in jobs:
                if f"{j.get('title','')} - {j.get('company','')}".strip(" - ") == item.get("job", ""):
                    result.append((j, score_info))
                    break
    return result


def filter_and_rank(
    jobs: List[dict],
    resume_summary: Union[str, Dict[str, Any]],
    min_score: float = 0.7,
    top_k: int = 20,
) -> List[tuple]:
    """
    Filter and rank jobs using resume summary or full profile.

    Args:
        jobs: List of job dicts.
        resume_summary: Full profile dict or text string.
        min_score: Minimum similarity threshold.
        top_k: Max jobs to return.

    Returns:
        List of (job_dict, score) tuples.
    """
    profile = (
        resume_summary
        if isinstance(resume_summary, dict)
        else {
            "name": "",
            "skills": resume_summary.split()[:30] if resume_summary else [],
            "experience_years": "",
            "projects": [],
            "preferred_roles": resume_summary.split()[:10] if resume_summary else [],
        }
    )
    return rank_jobs_with_details(
        jobs=jobs,
        candidate_profile=profile,
        min_score=min_score,
        top_k=top_k,
    )


# -----------------------------------------------------------------------------
# Example usage
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    # Example: rank jobs with candidate profile
    candidate_profile = {
        "name": "John Doe",
        "skills": ["Python", "Machine Learning", "TensorFlow", "FastAPI"],
        "experience_years": "2",
        "projects": ["ML pipeline", "Recommendation engine"],
        "preferred_roles": ["AI Engineer", "ML Engineer"],
    }

    sample_jobs = [
        {
            "title": "AI Engineer",
            "company": "Amazon",
            "description": "Build ML models with Python, TensorFlow. 2+ years experience.",
            "url": "https://example.com/1",
        },
        {
            "title": "ML Engineer",
            "company": "Startup",
            "description": "FastAPI, ML pipelines, recommendation systems.",
            "url": "https://example.com/2",
        },
    ]

    ranked = rank_jobs(
        jobs=sample_jobs,
        candidate_profile=candidate_profile,
        min_score=0.5,  # Lower for demo with short descriptions
    )
    for item in ranked:
        print(f"  {item['job']}: {item['score']}")
