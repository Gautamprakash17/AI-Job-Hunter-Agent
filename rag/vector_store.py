"""
Vector store module for AI Job Hunter Agent.

Manages Chroma vector database for storing and retrieving
resume chunks and job descriptions for semantic search.
"""

import logging
from pathlib import Path
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Chroma

from config.settings import settings
from rag.embeddings import get_embedding_model

logger = logging.getLogger(__name__)


def get_chunk_splitter() -> RecursiveCharacterTextSplitter:
    """
    Create text splitter for chunking documents.

    Returns:
        Configured RecursiveCharacterTextSplitter instance.
    """
    return RecursiveCharacterTextSplitter(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def create_vector_store(
    collection_name: str = "job_hunter",
    persist_directory: Optional[Path] = None,
) -> Chroma:
    """
    Create or load a Chroma vector store.

    Args:
        collection_name: Name of the Chroma collection.
        persist_directory: Path for persisting the store. Uses settings if None.

    Returns:
        Chroma vector store instance.
    """
    persist_path = str(persist_directory or settings.chroma_path)
    settings.chroma_path.mkdir(parents=True, exist_ok=True)

    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embedding_model(),
        persist_directory=persist_path,
    )


def add_resume_to_store(
    resume_text: str,
    resume_id: str,
    vector_store: Optional[Chroma] = None,
) -> Chroma:
    """
    Chunk resume text and add to vector store with metadata.

    Args:
        resume_text: Raw resume content.
        resume_id: Unique identifier for the resume.
        vector_store: Existing store or None to create new one.

    Returns:
        Chroma vector store with resume chunks added.
    """
    store = vector_store or create_vector_store()
    splitter = get_chunk_splitter()
    chunks = splitter.split_text(resume_text)

    metadatas = [{"resume_id": resume_id, "chunk_index": i} for i in range(len(chunks))]
    store.add_texts(texts=chunks, metadatas=metadatas)
    logger.info("Added %d resume chunks to vector store", len(chunks))
    return store


def add_jobs_to_store(
    job_descriptions: List[str],
    job_metadata: List[dict],
    vector_store: Optional[Chroma] = None,
) -> Chroma:
    """
    Add job descriptions to vector store with metadata.

    Args:
        job_descriptions: List of job description texts.
        job_metadata: List of dicts with job_id, title, company, etc.
        vector_store: Existing store or None.

    Returns:
        Chroma vector store with job chunks added.
    """
    store = vector_store or create_vector_store()
    splitter = get_chunk_splitter()

    all_texts = []
    all_metadatas = []
    for desc, meta in zip(job_descriptions, job_metadata):
        chunks = splitter.split_text(desc)
        for i, chunk in enumerate(chunks):
            all_texts.append(chunk)
            all_metadatas.append({**meta, "chunk_index": i})

    if all_texts:
        store.add_texts(texts=all_texts, metadatas=all_metadatas)
        logger.info("Added %d job chunks to vector store", len(all_texts))
    return store
