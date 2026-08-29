"""
Python RAG Microservice – FastAPI
Endpoints:
  POST /ingest          – upload & embed document
  POST /query           – ask question (RAG)
  GET  /documents       – list ingested docs (from vector store metadata)
  DELETE /documents/{doc_id}
  GET  /health
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .config import settings
from .rag_engine import rag_engine

app = FastAPI(
    title="RAG AI Service",
    description="Retrieval-Augmented Generation microservice for document Q&A",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload dir exists
Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)


# ---------- Schemas ----------
class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    top_k: Optional[int] = 4
    chat_history: Optional[List[dict]] = []


class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    context_used: int


class IngestResponse(BaseModel):
    doc_id: str
    filename: str
    chunks: int
    pages: int
    message: str = "Document ingested successfully"


class HealthResponse(BaseModel):
    status: str
    has_llm: bool
    embedding_model: str


# ---------- Endpoints ----------
@app.get("/health", response_model=HealthResponse)
async def health():
    return {
        "status": "ok",
        "has_llm": rag_engine.llm is not None,
        "embedding_model": settings.embedding_model,
    }


@app.post("/ingest", response_model=IngestResponse)
async def ingest_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    doc_id: Optional[str] = Form(None),
):
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    allowed = {".pdf", ".txt", ".md", ".docx", ".doc"}
    ext = Path(file.filename).suffix.lower()
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported file type. Allowed: {allowed}")

    doc_id = doc_id or str(uuid.uuid4())
    save_path = Path(settings.upload_dir) / f"{doc_id}{ext}"

    try:
        with open(save_path, "wb") as f:
            content = await file.read()
            f.write(content)

        result = rag_engine.ingest_file(str(save_path), doc_id, file.filename)
        return {**result, "message": "Document ingested successfully"}
    except Exception as e:
        if save_path.exists():
            save_path.unlink()
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@app.post("/query", response_model=QueryResponse)
async def query_rag(req: QueryRequest):
    try:
        result = rag_engine.query(
            question=req.question,
            top_k=req.top_k,
            chat_history=req.chat_history or [],
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Query failed: {str(e)}")


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    success = rag_engine.delete_document(doc_id)
    # also remove uploaded file if present
    for f in Path(settings.upload_dir).glob(f"{doc_id}.*"):
        f.unlink(missing_ok=True)
    if not success:
        raise HTTPException(404, "Document not found or already deleted")
    return {"message": "Document deleted", "doc_id": doc_id}


@app.get("/")
async def root():
    return {
        "service": "RAG AI Microservice",
        "docs": "/docs",
        "health": "/health",
    }
