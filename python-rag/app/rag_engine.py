"""
RAG Engine: document ingestion, embedding, retrieval & generation.
Uses sentence-transformers for embeddings (local) + OpenAI for generation (optional).
Falls back to a simple template response if no OpenAI key is set.
"""

import os
import uuid
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_core.documents import Document
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

from .config import settings


class RAGEngine:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.embedding_model,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        self.vector_store: Optional[FAISS] = None
        self.vector_store_path = Path(settings.vector_store_dir) / "faiss_index"
        self._load_or_create_store()

        # LLM (optional)
        self.llm = None
        if settings.openai_api_key:
            self.llm = ChatOpenAI(
                model=settings.openai_model,
                api_key=settings.openai_api_key,
                temperature=0.3,
            )

    def _load_or_create_store(self):
        if self.vector_store_path.exists():
            try:
                self.vector_store = FAISS.load_local(
                    str(self.vector_store_path),
                    self.embeddings,
                    allow_dangerous_deserialization=True,
                )
                print("✅ Loaded existing FAISS index")
            except Exception as e:
                print(f"⚠️ Could not load index: {e}. Creating new one.")
                self.vector_store = None
        if self.vector_store is None:
            # Create empty store with a dummy doc
            dummy = [Document(page_content="RAG system initialized.", metadata={"source": "system"})]
            self.vector_store = FAISS.from_documents(dummy, self.embeddings)
            self._save_store()

    def _save_store(self):
        self.vector_store_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_store.save_local(str(self.vector_store_path))

    def _load_document(self, file_path: str) -> List[Document]:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            loader = PyPDFLoader(file_path)
        elif ext in [".txt", ".md"]:
            loader = TextLoader(file_path, encoding="utf-8")
        elif ext in [".docx", ".doc"]:
            loader = Docx2txtLoader(file_path)
        else:
            raise ValueError(f"Unsupported file type: {ext}")
        return loader.load()

    def ingest_file(self, file_path: str, doc_id: str, filename: str) -> Dict[str, Any]:
        """Ingest a single file into the vector store."""
        docs = self._load_document(file_path)
        for d in docs:
            d.metadata["doc_id"] = doc_id
            d.metadata["filename"] = filename
            d.metadata["source"] = filename

        chunks = self.text_splitter.split_documents(docs)
        if not chunks:
            raise ValueError("No text content extracted from file")

        self.vector_store.add_documents(chunks)
        self._save_store()

        return {
            "doc_id": doc_id,
            "filename": filename,
            "chunks": len(chunks),
            "pages": len(docs),
        }

    def delete_document(self, doc_id: str) -> bool:
        """Remove all chunks belonging to a document (rebuild index)."""
        # FAISS does not support easy deletion; we filter and rebuild
        try:
            # Get all docs
            all_docs = list(self.vector_store.docstore._dict.values())
            remaining = [d for d in all_docs if d.metadata.get("doc_id") != doc_id]
            if len(remaining) == len(all_docs):
                return False  # nothing removed
            if not remaining:
                remaining = [Document(page_content="Empty store", metadata={"source": "system"})]
            self.vector_store = FAISS.from_documents(remaining, self.embeddings)
            self._save_store()
            return True
        except Exception as e:
            print(f"Delete error: {e}")
            return False

    def retrieve(self, query: str, top_k: int = None) -> List[Document]:
        k = top_k or settings.top_k
        return self.vector_store.similarity_search(query, k=k)

    def query(self, question: str, top_k: int = None, chat_history: List[Dict] = None) -> Dict[str, Any]:
        """Full RAG pipeline: retrieve + generate."""
        docs = self.retrieve(question, top_k)
        context = "\n\n".join(
            f"[Source: {d.metadata.get('filename', 'unknown')}]\n{d.page_content}"
            for d in docs
        )

        sources = [
            {
                "filename": d.metadata.get("filename", "unknown"),
                "doc_id": d.metadata.get("doc_id"),
                "snippet": d.page_content[:200] + "...",
            }
            for d in docs
        ]

        if self.llm:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a helpful AI assistant that answers questions based on the provided context. "
                        "If the answer is not in the context, say you don't know based on the available documents. "
                        "Be concise and accurate. Cite sources when possible.\n\nContext:\n{context}",
                    ),
                    ("human", "{question}"),
                ]
            )
            chain = (
                {"context": lambda x: context, "question": RunnablePassthrough()}
                | prompt
                | self.llm
                | StrOutputParser()
            )
            answer = chain.invoke(question)
        else:
            # Fallback without OpenAI
            answer = (
                f"**Answer (demo mode – set OPENAI_API_KEY for real LLM):**\n\n"
                f"Based on the retrieved documents, here is the relevant context:\n\n"
                f"{context[:1500]}...\n\n"
                f"*(To get full AI-generated answers, add your OpenAI API key in the Python service .env file.)*"
            )

        return {
            "answer": answer,
            "sources": sources,
            "context_used": len(docs),
        }


# Singleton
rag_engine = RAGEngine()
