from __future__ import annotations

import ast
from dataclasses import dataclass, field

from src.parser_service.event_models import (
    EdgeEvent,
    EdgePayload,
    NodeEvent,
    NodePayload,
)
from src.parser_service.ids import (
    create_edge_id,
    create_event_id,
    create_node_id,
)


MAX_CODE_SNIPPET_LENGTH = 300


@dataclass
class AstExtractionResult:
    node_events: list[NodeEvent] = field(default_factory=list)
    edge_events: list[EdgeEvent] = field(default_factory=list)


def get_node_name(node: ast.AST) -> str | None:
    if isinstance(
        node,
        (
            ast.FunctionDef,
            ast.AsyncFunctionDef,
            ast.ClassDef,
        ),
    ):
        return node.name

    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.arg):
        return node.arg

    if isinstance(node, ast.Attribute):
        return node.attr

    if isinstance(node, ast.alias):
        return node.asname or node.name

    return None


def get_node_properties(node: ast.AST) -> dict[str, object]:
    properties: dict[str, object] = {}

    if isinstance(node, ast.Constant):
        value = repr(node.value)

        if len(value) > 200:
            value = value[:197] + "..."

        properties["value"] = value

    if isinstance(node, ast.Name):
        properties["context"] = type(node.ctx).__name__

    if isinstance(node, ast.Attribute):
        properties["context"] = type(node.ctx).__name__

    return properties


def get_code_snippet(
    source: str,
    node: ast.AST,
) -> str | None:
    snippet = ast.get_source_segment(source, node)

    if snippet is None:
        return None

    snippet = snippet.strip()

    if len(snippet) > MAX_CODE_SNIPPET_LENGTH:
        snippet = (
            snippet[: MAX_CODE_SNIPPET_LENGTH - 3]
            + "..."
        )

    return snippet


def extract_ast_events(
    *,
    source: str,
    repo_id: str,
    commit_sha: str,
    file_id: str,
    content_hash: str,
    relative_path: str,
) -> AstExtractionResult:
    tree = ast.parse(
        source,
        filename=relative_path,
        type_comments=True,
    )

    result = AstExtractionResult()

    def visit_node(
        node: ast.AST,
        structural_path: str,
        parent_id: str | None = None,
        edge_role: str | None = None,
    ) -> str:
        ast_type = type(node).__name__

        node_id = create_node_id(
            file_id,
            structural_path,
            ast_type,
        )

        node_event = NodeEvent(
            event_id=create_event_id(
                "UPSERT",
                node_id,
                content_hash,
            ),
            op="UPSERT",
            repo_id=repo_id,
            commit_sha=commit_sha,
            file_id=file_id,
            content_hash=content_hash,
            path=relative_path,
            node=NodePayload(
                node_id=node_id,
                node_kind="AST",
                ast_type=ast_type,
                structural_path=structural_path,
                lineno=getattr(node, "lineno", None),
                col_offset=getattr(
                    node,
                    "col_offset",
                    None,
                ),
                end_lineno=getattr(
                    node,
                    "end_lineno",
                    None,
                ),
                end_col_offset=getattr(
                    node,
                    "end_col_offset",
                    None,
                ),
                name=get_node_name(node),
                code_snippet=get_code_snippet(
                    source,
                    node,
                ),
                properties=get_node_properties(node),
            ),
        )

        result.node_events.append(node_event)

        if parent_id is not None and edge_role is not None:
            edge_id = create_edge_id(
                "AST_CHILD",
                parent_id,
                node_id,
                edge_role,
            )

            edge_event = EdgeEvent(
                event_id=create_event_id(
                    "UPSERT",
                    edge_id,
                    content_hash,
                ),
                op="UPSERT",
                repo_id=repo_id,
                commit_sha=commit_sha,
                file_id=file_id,
                content_hash=content_hash,
                path=relative_path,
                edge=EdgePayload(
                    edge_id=edge_id,
                    edge_type="AST_CHILD",
                    src_id=parent_id,
                    dst_id=node_id,
                    properties={
                        "role": edge_role,
                    },
                ),
            )

            result.edge_events.append(edge_event)

        for field_name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                child_path = (
                    f"{structural_path}.{field_name}"
                )

                visit_node(
                    value,
                    child_path,
                    parent_id=node_id,
                    edge_role=field_name,
                )

            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if not isinstance(item, ast.AST):
                        continue

                    role = f"{field_name}[{index}]"
                    child_path = (
                        f"{structural_path}.{role}"
                    )

                    visit_node(
                        item,
                        child_path,
                        parent_id=node_id,
                        edge_role=role,
                    )

        return node_id

    visit_node(
        tree,
        structural_path="root",
    )

    return result