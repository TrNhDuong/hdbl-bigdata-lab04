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


TRY_TYPES = (ast.Try,)

if hasattr(ast, "TryStar"):
    TRY_TYPES = TRY_TYPES + (ast.TryStar,)


@dataclass
class CfgExtractionResult:
    node_events: list[NodeEvent] = field(default_factory=list)
    edge_events: list[EdgeEvent] = field(default_factory=list)


def build_structural_path_index(
    tree: ast.AST,
) -> dict[int, str]:
    """
    Tạo mapping từ AST object sang structural path.

    Cách duyệt phải giống ast_extractor.py để node ID
    được tạo ra giống hệt.
    """
    result: dict[int, str] = {}

    def visit(
        node: ast.AST,
        structural_path: str,
    ) -> None:
        result[id(node)] = structural_path

        for field_name, value in ast.iter_fields(node):
            if isinstance(value, ast.AST):
                visit(
                    value,
                    f"{structural_path}.{field_name}",
                )

            elif isinstance(value, list):
                for index, item in enumerate(value):
                    if not isinstance(item, ast.AST):
                        continue

                    visit(
                        item,
                        f"{structural_path}.{field_name}[{index}]",
                    )

    visit(tree, "root")
    return result


def extract_cfg_events(
    *,
    source: str,
    repo_id: str,
    commit_sha: str,
    file_id: str,
    content_hash: str,
    relative_path: str,
) -> CfgExtractionResult:
    """
    Tạo conservative CFG cho module, class và function.

    CFG dùng AST statement nodes làm điểm điều khiển và tạo
    thêm CFG_ENTRY/CFG_EXIT cho từng scope.
    """
    tree = ast.parse(
        source,
        filename=relative_path,
        type_comments=True,
    )

    structural_paths = build_structural_path_index(tree)
    result = CfgExtractionResult()

    created_node_ids: set[str] = set()
    created_edge_ids: set[str] = set()

    def get_ast_node_id(node: ast.AST) -> str:
        structural_path = structural_paths[id(node)]

        return create_node_id(
            file_id,
            structural_path,
            type(node).__name__,
        )

    def create_synthetic_node(
        *,
        structural_path: str,
        ast_type: str,
        scope_path: str,
    ) -> str:
        node_id = create_node_id(
            file_id,
            structural_path,
            ast_type,
        )

        if node_id in created_node_ids:
            return node_id

        created_node_ids.add(node_id)

        result.node_events.append(
            NodeEvent(
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
                    node_kind="CFG",
                    ast_type=ast_type,
                    structural_path=structural_path,
                    properties={
                        "scope_path": scope_path,
                    },
                ),
            )
        )

        return node_id

    def add_cfg_edge(
        source_id: str,
        target_id: str,
        branch: str,
    ) -> None:
        edge_id = create_edge_id(
            "CFG_NEXT",
            source_id,
            target_id,
            branch,
        )

        if edge_id in created_edge_ids:
            return

        created_edge_ids.add(edge_id)

        result.edge_events.append(
            EdgeEvent(
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
                    edge_type="CFG_NEXT",
                    src_id=source_id,
                    dst_id=target_id,
                    properties={
                        "branch": branch,
                    },
                ),
            )
        )

    def process_block(
        statements: list[ast.stmt],
        next_id: str,
        *,
        exit_id: str,
        break_target: str | None = None,
        continue_target: str | None = None,
    ) -> str:
        """
        Xử lý block theo chiều ngược để biết statement tiếp theo.
        """
        current_next = next_id

        for statement in reversed(statements):
            statement_id = get_ast_node_id(statement)

            if isinstance(statement, ast.Return):
                add_cfg_edge(
                    statement_id,
                    exit_id,
                    "RETURN",
                )

                current_next = statement_id
                continue

            if isinstance(statement, ast.Raise):
                add_cfg_edge(
                    statement_id,
                    exit_id,
                    "EXCEPTION",
                )

                current_next = statement_id
                continue

            if isinstance(statement, ast.Break):
                if break_target is not None:
                    add_cfg_edge(
                        statement_id,
                        break_target,
                        "BREAK",
                    )

                current_next = statement_id
                continue

            if isinstance(statement, ast.Continue):
                if continue_target is not None:
                    add_cfg_edge(
                        statement_id,
                        continue_target,
                        "CONTINUE",
                    )

                current_next = statement_id
                continue

            if isinstance(statement, ast.If):
                body_entry = process_block(
                    statement.body,
                    current_next,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                else_entry = process_block(
                    statement.orelse,
                    current_next,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                add_cfg_edge(
                    statement_id,
                    body_entry,
                    "TRUE",
                )

                add_cfg_edge(
                    statement_id,
                    else_entry,
                    "FALSE",
                )

                current_next = statement_id
                continue

            if isinstance(
                statement,
                (
                    ast.For,
                    ast.AsyncFor,
                    ast.While,
                ),
            ):
                normal_exit = process_block(
                    statement.orelse,
                    current_next,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                body_entry = process_block(
                    statement.body,
                    statement_id,
                    exit_id=exit_id,
                    break_target=current_next,
                    continue_target=statement_id,
                )

                add_cfg_edge(
                    statement_id,
                    body_entry,
                    "LOOP",
                )

                add_cfg_edge(
                    statement_id,
                    normal_exit,
                    "FALSE",
                )

                current_next = statement_id
                continue

            if isinstance(
                statement,
                (
                    ast.With,
                    ast.AsyncWith,
                ),
            ):
                body_entry = process_block(
                    statement.body,
                    current_next,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                add_cfg_edge(
                    statement_id,
                    body_entry,
                    "NEXT",
                )

                current_next = statement_id
                continue

            if isinstance(statement, TRY_TYPES):
                finally_entry = process_block(
                    statement.finalbody,
                    current_next,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                else_entry = process_block(
                    statement.orelse,
                    finally_entry,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                body_entry = process_block(
                    statement.body,
                    else_entry,
                    exit_id=exit_id,
                    break_target=break_target,
                    continue_target=continue_target,
                )

                add_cfg_edge(
                    statement_id,
                    body_entry,
                    "NEXT",
                )

                for handler in statement.handlers:
                    handler_entry = process_block(
                        handler.body,
                        finally_entry,
                        exit_id=exit_id,
                        break_target=break_target,
                        continue_target=continue_target,
                    )

                    add_cfg_edge(
                        statement_id,
                        handler_entry,
                        "EXCEPTION",
                    )

                current_next = statement_id
                continue

            if isinstance(statement, ast.Match):
                if not statement.cases:
                    add_cfg_edge(
                        statement_id,
                        current_next,
                        "NEXT",
                    )

                for index, match_case in enumerate(
                    statement.cases
                ):
                    case_entry = process_block(
                        match_case.body,
                        current_next,
                        exit_id=exit_id,
                        break_target=break_target,
                        continue_target=continue_target,
                    )

                    add_cfg_edge(
                        statement_id,
                        case_entry,
                        f"CASE_{index}",
                    )

                current_next = statement_id
                continue

            # Statement thông thường.
            add_cfg_edge(
                statement_id,
                current_next,
                "NEXT",
            )

            current_next = statement_id

        return current_next

    def process_scope(
        scope_node: ast.AST,
        body: list[ast.stmt],
    ) -> None:
        scope_path = structural_paths[id(scope_node)]

        entry_id = create_synthetic_node(
            structural_path=f"{scope_path}.cfg_entry",
            ast_type="CFG_ENTRY",
            scope_path=scope_path,
        )

        exit_id = create_synthetic_node(
            structural_path=f"{scope_path}.cfg_exit",
            ast_type="CFG_EXIT",
            scope_path=scope_path,
        )

        first_statement_id = process_block(
            body,
            exit_id,
            exit_id=exit_id,
        )

        add_cfg_edge(
            entry_id,
            first_statement_id,
            "ENTRY",
        )

    # CFG cho module.
    process_scope(
        tree,
        tree.body,
    )

    # CFG riêng cho function, async function và class.
    for node in ast.walk(tree):
        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            process_scope(
                node,
                node.body,
            )

    return result