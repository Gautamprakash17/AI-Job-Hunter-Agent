"""
Configuration settings for the AI Job Hunter Agent.

Centralizes all configurable parameters including database paths,
API keys, model settings, and application constants.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "AI Job Hunter Agent"
    debug: bool = False

    # Database
    database_path: str = "data/job_hunter.db"
    chroma_persist_directory: str = "data/chroma_db"

    # LLM & Embeddings
    openai_api_key: Optional[str] = None
    # Embedding: "openai" (text-embedding-3-large) or "huggingface" (BAAI/bge-large-en-v1.5)
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-large"
    huggingface_embedding_model: str = "BAAI/bge-large-en-v1.5"
    llm_model: str = "gpt-4o-mini"

    # RAG
    chunk_size: int = 500
    chunk_overlap: int = 50
    top_k_retrieval: int = 5

    # Browser automation
    headless: bool = True
    # Application agent: run visible for debugging (set False in .env for headless)
    application_headless: bool = False
    browser_timeout_ms: int = 30000

    # Demo mode: use mock jobs when scrapers return 0 (set False for live-only)
    use_demo_jobs_on_empty: bool = True

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # Dashboard
    dashboard_port: int = 8501

    @property
    def db_path(self) -> Path:
        """Resolve database path and ensure parent directory exists."""
        path = Path(self.database_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def chroma_path(self) -> Path:
        """Resolve Chroma persist directory."""
        return Path(self.chroma_persist_directory)


settings = Settings()
