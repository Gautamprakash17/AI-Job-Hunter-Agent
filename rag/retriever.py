"""
Retriever module for AI Job Hunter Agent.

Provides semantic retrieval for ranking jobs against resumes
using vector similarity search.
"""

import logging
from math import sqrt
from typing import List, Optional

from langchain_community.vectorstores import Chroma

from config.settings import settings
from rag.embeddings import embed_query, embed_texts
from rag.vector_store import create_vector_store

logger = logging.getLogger(__name__)


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sqrt(sum(x**2 for x in a))
    norm_b = sqrt(sum(x**2 for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def get_retriever(
    vector_store: Optional[Chroma] = None,
    k: Optional[int] = None,
):
    """
    Create a retriever from the vector store.

    Args:
        vector_store: Existing Chroma store or None.
        k: Number of documents to retrieve. Uses settings if None.

    Returns:
        VectorStoreRetriever instance.
    """
    store = vector_store or create_vector_store()
    return store.as_retriever(search_kwargs={"k": k or settings.top_k_retrieval})


def retrieve_similar_jobs(
    query: str,
    vector_store: Optional[Chroma] = None,
    top_k: Optional[int] = None,
) -> List[dict]:
    """
    Retrieve jobs most semantically similar to the query (e.g. resume summary).

    Args:
        query: Query text (typically resume or role description).
        vector_store: Chroma store containing job chunks.
        top_k: Number of results. Uses settings if None.

    Returns:
        List of dicts with content and metadata.
    """
    store = vector_store or create_vector_store()
    k = top_k or settings.top_k_retrieval

    docs = store.similarity_search_with_score(query, k=k)
    return [
        {
            "content": doc.page_content,
            "metadata": doc.metadata,
            "score": float(score),
        }
        for doc, score in docs
    ]


def compute_similarity_scores(
    resume_summary: str,
    job_descriptions: List[str],
) -> List[float]:
    """
    Compute semantic similarity between resume and each job description.

    Args:
        resume_summary: Summary of resume / target role.
        job_descriptions: List of job description texts.

    Returns:
        List of similarity scores (higher = more similar).
    """
    if not job_descriptions:
        return []

    query_embedding = embed_query(resume_summary)
    job_embeddings = embed_texts(job_descriptions)
    return [_cosine_similarity(query_embedding, je) for je in job_embeddings]
