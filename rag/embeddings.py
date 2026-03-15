"""
Embeddings module for AI Job Hunter Agent.

Provides text embedding generation using modern models for semantic similarity
in resume-job matching. Supports:
- OpenAI: text-embedding-3-large
- HuggingFace: BAAI/bge-large-en-v1.5

The same model is used for candidate profile and job descriptions.
"""

import logging
from typing import List

from config.settings import settings

logger = logging.getLogger(__name__)

# Lazy-loaded model instance (same for all embedding calls)
_embedding_model = None


def _get_embedding_model():
    """Create or return the configured embedding model (singleton)."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    provider = getattr(settings, "embedding_provider", "openai").lower()

    if provider == "huggingface":
        from langchain_community.embeddings import HuggingFaceEmbeddings

        model_name = getattr(settings, "huggingface_embedding_model", "BAAI/bge-large-en-v1.5")
        _embedding_model = HuggingFaceEmbeddings(model_name=model_name)
        logger.info("Using HuggingFace embedding model: %s", model_name)
    else:
        from langchain_openai import OpenAIEmbeddings

        model_name = settings.embedding_model
        _embedding_model = OpenAIEmbeddings(
            model=model_name,
            api_key=settings.openai_api_key,
        )
        logger.info("Using OpenAI embedding model: %s", model_name)

    return _embedding_model


def get_embedding_model():
    """
    Return the configured embedding model (LangChain-compatible).

    Same model used for candidate profile and job descriptions.
    Compatible with Chroma vector store.
    """
    return _get_embedding_model()


def generate_embedding(text: str) -> List[float]:
    """
    Generate embedding for a single text using the configured model.

    The same model is used for candidate profile and job descriptions
    to ensure consistent similarity accuracy.

    Args:
        text: Text to embed.

    Returns:
        Embedding vector as list of floats.
    """
    if not text or not str(text).strip():
        text = " "  # Fallback for empty input

    model = _get_embedding_model()
    return model.embed_query(text)


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of text strings.

    Uses the same model as generate_embedding for consistency.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    if not texts:
        return []

    valid_texts = [t if (t and str(t).strip()) else " " for t in texts]
    model = _get_embedding_model()
    return model.embed_documents(valid_texts)


def embed_query(query: str) -> List[float]:
    """
    Generate embedding for a single query string.

    Uses generate_embedding internally - same model for profile and job texts.

    Args:
        query: Query text to embed.

    Returns:
        Embedding vector as list of floats.
    """
    return generate_embedding(query)
