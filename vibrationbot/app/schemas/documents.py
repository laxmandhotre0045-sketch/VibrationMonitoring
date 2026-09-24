"""Document, chunk and ingestion DTOs."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ChunkType(str, Enum):
    CLAUSE = "clause"
    SECTION_SUMMARY = "section_summary"
    CHAPTER_SUMMARY = "chapter_summary"
    TABLE = "table"
    DIAGRAM = "diagram"
    IMAGE = "image"


class DocumentStatus(str, Enum):
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ChunkRecord(BaseModel):
    chunk_id: str
    chunk_type: ChunkType
    text: str
    node_id: str
    page_start: int
    page_end: int
    section_path: str
    meta: dict[str, Any] = Field(default_factory=dict)


class DocumentRegistry(BaseModel):
    doc_id: str
    title: str
    department: str = ""
    version: str = ""
    effective_date: str = ""
    confidentiality: str = ""
    source_path: str = ""


class DocumentUploadResponse(BaseModel):
    doc_id: str
    status: DocumentStatus


class DocumentSummary(BaseModel):
    doc_id: str
    title: str
    status: DocumentStatus
    chunk_count: int = 0
    index_status: str = "missing"


class DocumentDetail(DocumentSummary):
    registry: DocumentRegistry
    index_ready: bool = False


class ChunksPage(BaseModel):
    doc_id: str
    total: int
    offset: int
    limit: int
    chunks: list[ChunkRecord]
