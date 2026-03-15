"""
Embeddings module for AI Job Hunter Agent.

Provides text embedding generation using modern models for semantic similarity
in resume-job matching. Supports:
- OpenAI: text-embedding-3-large
- HuggingFace: BAAI/bge-large-en-v1.5

Includes in-memory cache to avoid duplicate API calls for the same text.
"""

import hashlib
import logging
from typing import Dict, List, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

# Lazy-loaded model instance (same for all embedding calls)
_embedding_model = None

# In-memory cache: text_hash -> embedding (avoids repeat API calls)
_embedding_cache: Dict[str, List[float]] = {}
_CACHE_MAX_SIZE = 2000  # cap size to avoid unbounded memory


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


def _text_hash(text: str) -> str:
    """Stable hash for cache key."""
    return hashlib.sha256((text or "").strip().encode("utf-8")).hexdigest()


def _cache_put(key: str, embedding: List[float]) -> None:
    """Add to cache; evict oldest if over capacity (simple FIFO via dict)."""
    global _embedding_cache
    if len(_embedding_cache) >= _CACHE_MAX_SIZE:
        # Remove oldest ~20%
        to_remove = list(_embedding_cache.keys())[: max(1, _CACHE_MAX_SIZE // 5)]
        for k in to_remove:
            del _embedding_cache[k]
    _embedding_cache[key] = embedding


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
    Uses in-memory cache to avoid duplicate API calls.

    Args:
        text: Text to embed.

    Returns:
        Embedding vector as list of floats.
    """
    if not text or not str(text).strip():
        text = " "  # Fallback for empty input
    key = _text_hash(text)
    if key in _embedding_cache:
        return _embedding_cache[key]
    model = _get_embedding_model()
    emb = model.embed_query(text)
    _cache_put(key, emb)
    return emb


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of text strings.
    Caches results; only calls API for texts not yet in cache.

    Args:
        texts: List of text strings to embed.

    Returns:
        List of embedding vectors (each a list of floats).
    """
    if not texts:
        return []

    valid_texts = [t if (t and str(t).strip()) else " " for t in texts]
    keys = [_text_hash(t) for t in valid_texts]
    result: List[List[float]] = [None] * len(valid_texts)  # type: ignore
    to_compute: List[Tuple[int, str]] = []

    for i, (key, text) in enumerate(zip(keys, valid_texts)):
        if key in _embedding_cache:
            result[i] = _embedding_cache[key]
        else:
            to_compute.append((i, text))

    if not to_compute:
        return result

    indices, uncached_texts = zip(*to_compute) if to_compute else ([], [])
    model = _get_embedding_model()
    computed = model.embed_documents(list(uncached_texts))
    for idx, emb in zip(indices, computed):
        result[idx] = emb
        _cache_put(keys[idx], emb)

    return result


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
