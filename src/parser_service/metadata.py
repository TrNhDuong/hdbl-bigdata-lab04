from __future__ import annotations

from src.parser_service.event_models import (
    MetadataCounts,
    MetadataEvent,
)
from src.parser_service.ids import create_event_id
from src.parser_service.source_reader import SourceFile


def build_metadata_event(
    *,
    source_file: SourceFile,
    repo_id: str,
    commit_sha: str,
    file_id: str,
    parse_duration_ms: float,
    node_count: int,
    ast_edge_count: int,
    cfg_edge_count: int = 0,
    dfg_edge_count: int = 0,
) -> MetadataEvent:
    return MetadataEvent(
        event_id=create_event_id(
            "UPSERT",
            file_id,
            source_file.content_hash,
        ),
        op="UPSERT",
        repo_id=repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        content_hash=source_file.content_hash,
        path=source_file.relative_path,
        document_id=file_id,
        size_bytes=source_file.size_bytes,
        line_count=source_file.line_count,
        parse_duration_ms=round(
            parse_duration_ms,
            3,
        ),
        status="SUCCESS",
        counts=MetadataCounts(
            nodes=node_count,
            ast_edges=ast_edge_count,
            cfg_edges=cfg_edge_count,
            dfg_edges=dfg_edge_count,
            call_edges=0,
        ),
    )