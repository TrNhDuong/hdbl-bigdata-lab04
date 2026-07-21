from __future__ import annotations

import hashlib


def stable_hash(*parts: str) -> str:
    """
    Tạo SHA-256 ổn định từ nhiều thành phần chuỗi.

    Dùng ký tự null làm dấu phân cách để tránh trường hợp:
    ("ab", "c") và ("a", "bc") tạo cùng chuỗi đầu vào.
    """
    normalized = "\0".join(parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def create_file_id(repo_id: str, relative_path: str) -> str:
    normalized_path = relative_path.replace("\\", "/")
    return stable_hash("file", repo_id, normalized_path)


def create_node_id(
    file_id: str,
    structural_path: str,
    ast_type: str,
) -> str:
    return stable_hash(
        "node",
        file_id,
        structural_path,
        ast_type,
    )


def create_edge_id(
    edge_type: str,
    source_id: str,
    target_id: str,
    edge_role: str = "",
) -> str:
    return stable_hash(
        "edge",
        edge_type,
        source_id,
        target_id,
        edge_role,
    )


def create_event_id(
    operation: str,
    entity_id: str,
    content_hash: str,
) -> str:
    return stable_hash(
        "event",
        operation,
        entity_id,
        content_hash,
    )