"""Chat request/response DTOs, including the mode=graph additions."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str
    doc_ids: Optional[list[str]] = None
    session_id: Optional[str] = None
    top_k: int = 6
    # Measurement context (mode=graph). All optional, so existing clients are
    # unaffected.
    machine_id: Optional[str] = None
    point_id: Optional[str] = None
    signal_ids: list[str] = Field(default_factory=list)
    chart_ids: list[str] = Field(default_factory=list)


class SourceCitation(BaseModel):
    chunk_id: str
    text: str
    section_path: str
    page_start: int
    page_end: int
    score: float
    doc_id: str
    chunk_type: str = "clause"
    asset_url: Optional[str] = None


class ComputationRecordOut(BaseModel):
    """A deterministic calculation, with everything needed to reproduce it.

    Kept out of ``sources``: SourceCitation requires integer page numbers, so a
    computation folded in there would render as "pp.0-0" in the UI.
    """

    id: str
    tool: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    formula: str = ""
    assumptions: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    supporting_chunk_id: Optional[str] = None
    supporting_doc_id: Optional[str] = None


class PlotRef(BaseModel):
    plot_id: str
    url: str
    title: str = ""
    kind: str = ""
    path: Optional[str] = None


class TraceStep(BaseModel):
    node: str
    detail: str = ""
    duration_ms: Optional[int] = None


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]
    session_id: str
    # Added for mode=graph. All default, and FastAPI's response_model filters
    # undeclared fields — which is why these live on ChatResponse itself rather
    # than on a subclass, where they would be silently dropped.
    route: Optional[str] = None
    computations: list[ComputationRecordOut] = Field(default_factory=list)
    plots: list[PlotRef] = Field(default_factory=list)
    grounded: bool = True
    trace: list[TraceStep] = Field(default_factory=list)
