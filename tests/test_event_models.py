from datetime import datetime

import pytest
from pydantic import ValidationError

from src.parser_service.event_models import (
    MetadataCounts,
    MetadataEvent,
    NodeEvent,
    NodePayload,
)


def create_sample_node_event() -> NodeEvent:
    return NodeEvent(
        event_id="event-1",
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id="file-123",
        content_hash="hash-123",
        path="trl/example.py",
        node=NodePayload(
            node_id="node-123",
            ast_type="FunctionDef",
            structural_path="root.body[0]",
            lineno=1,
            col_offset=0,
            name="example",
        ),
    )


def test_node_event_has_schema_version() -> None:
    event = create_sample_node_event()

    assert event.schema_version == "1.0"
    assert event.op == "UPSERT"


def test_node_event_has_timezone_aware_event_time() -> None:
    event = create_sample_node_event()

    assert isinstance(event.event_time, datetime)
    assert event.event_time.tzinfo is not None


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        NodeEvent(
            event_id="event-1",
            repo_id="github:huggingface/trl",
            commit_sha="commit-123",
            file_id="file-123",
            content_hash="hash-123",
            path="trl/example.py",
            node=NodePayload(
                node_id="node-123",
                ast_type="FunctionDef",
                structural_path="root.body[0]",
            ),
            unknown_field="not-allowed",
        )


def test_metadata_id_is_serialized_as_mongodb_id() -> None:
    event = MetadataEvent(
        event_id="metadata-event-1",
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id="file-123",
        content_hash="hash-123",
        path="trl/example.py",
        document_id="file-123",
        size_bytes=100,
        line_count=10,
        parse_duration_ms=12.5,
        status="SUCCESS",
        counts=MetadataCounts(
            nodes=5,
            ast_edges=4,
        ),
    )

    data = event.model_dump(
        mode="json",
        by_alias=True,
    )

    assert data["_id"] == "file-123"
    assert "document_id" not in data