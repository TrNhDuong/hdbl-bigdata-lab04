from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


Operation = Literal["UPSERT", "DELETE"]


def utc_now() -> datetime:
    """Trả về thời gian UTC có timezone."""
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """Không cho phép field ngoài schema."""

    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
    )


class BaseEvent(StrictModel):
    schema_version: str = "1.0"
    event_time: datetime = Field(default_factory=utc_now)

    event_id: str
    op: Operation = "UPSERT"

    repo_id: str
    commit_sha: str

    file_id: str
    content_hash: str
    path: str


class NodePayload(StrictModel):
    node_id: str
    node_kind: str = "AST"
    ast_type: str
    structural_path: str

    lineno: int | None = None
    col_offset: int | None = None
    end_lineno: int | None = None
    end_col_offset: int | None = None

    name: str | None = None
    code_snippet: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class NodeEvent(BaseEvent):
    node: NodePayload


class EdgePayload(StrictModel):
    edge_id: str
    edge_type: str

    src_id: str
    dst_id: str

    properties: dict[str, Any] = Field(default_factory=dict)


class EdgeEvent(BaseEvent):
    edge: EdgePayload


class MetadataCounts(StrictModel):
    nodes: int = 0
    ast_edges: int = 0
    cfg_edges: int = 0
    dfg_edges: int = 0
    call_edges: int = 0


class MetadataEvent(BaseEvent):
    # Khi xuất JSON, field này có tên "_id".
    document_id: str = Field(alias="_id")

    size_bytes: int
    line_count: int
    parse_duration_ms: float
    status: Literal["SUCCESS", "ERROR"]

    counts: MetadataCounts


class ErrorEvent(BaseEvent):
    error_type: str
    message: str

    line: int | None = None
    column: int | None = None