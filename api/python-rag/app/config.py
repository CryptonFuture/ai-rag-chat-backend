from pydantic_settings import BaseSettings
from typing import Optional
import os


class Settings(BaseSettings):
    # OpenAI (optional – set OPENAI_API_KEY for real LLM)
    openai_api_key: Optional[str] = os.getenv("OPENAI_API_KEY", None)
    openai_model: str = "gpt-4o-mini"

    # Embedding model (local, free)
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    # Paths
    upload_dir: str = "uploads"
    vector_store_dir: str = "vector_store"

    # Chunking
    chunk_size: int = 800
    chunk_overlap: int = 150

    # Retrieval
    top_k: int = 4

    class Config:
        env_file = ".env"


settings = Settings()
