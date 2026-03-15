"""RAG module for semantic search and retrieval."""

from rag.embeddings import embed_query, embed_texts, generate_embedding, get_embedding_model
from rag.retriever import get_retriever, retrieve_similar_jobs
from rag.vector_store import (
    add_jobs_to_store,
    add_resume_to_store,
    create_vector_store,
    get_chunk_splitter,
)

__all__ = [
    "get_embedding_model",
    "generate_embedding",
    "embed_texts",
    "embed_query",
    "create_vector_store",
    "get_chunk_splitter",
    "add_resume_to_store",
    "add_jobs_to_store",
    "get_retriever",
    "retrieve_similar_jobs",
]
