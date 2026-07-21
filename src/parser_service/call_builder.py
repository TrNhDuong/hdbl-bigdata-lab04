from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from src.parser_service.cfg_builder import (
    build_structural_path_index,
)
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
    stable_hash,
)


@dataclass
class CallExtractionResult:
    node_events: list[NodeEvent] = field(default_factory=list)
    edge_events: list[EdgeEvent] = field(default_factory=list)


@dataclass(frozen=True)
class LocalSymbol:
    node_id: str
    qualified_name: str


def module_name_from_path(relative_path: str) -> str:
    """
    trl/data_utils.py -> trl.data_utils
    trl/__init__.py  -> trl
    """
    path = PurePosixPath(relative_path)

    parts = list(path.with_suffix("").parts)

    if parts and parts[-1] == "__init__":
        parts.pop()

    return ".".join(parts)


def expression_to_dotted_name(
    expression: ast.AST,
) -> str | None:
    """
    Chuyển biểu thức callee thành tên dạng chấm.

    foo                 -> foo
    module.function     -> module.function
    self.method         -> self.method
    """
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        prefix = expression_to_dotted_name(
            expression.value
        )

        if prefix is None:
            return expression.attr

        return f"{prefix}.{expression.attr}"

    return None


def extract_call_events(
    *,
    source: str,
    repo_id: str,
    commit_sha: str,
    file_id: str,
    content_hash: str,
    relative_path: str,
) -> CallExtractionResult:
    """
    Tạo CALLS edges với ba mức phân giải:

    EXACT_LOCAL:
        Target là FunctionDef/ClassDef trong cùng file.

    IMPORTED_SYMBOL:
        Target được suy ra từ import hoặc import alias.

    SYMBOLIC:
        Không xác định chính xác target bằng static analysis.
    """
    tree = ast.parse(
        source,
        filename=relative_path,
        type_comments=True,
    )

    structural_paths = build_structural_path_index(
        tree
    )

    module_name = module_name_from_path(
        relative_path
    )

    result = CallExtractionResult()

    created_node_ids: set[str] = set()
    created_edge_ids: set[str] = set()

    scope_parent: dict[str, str | None] = {
        "root": None
    }

    scope_symbols: dict[
        str,
        dict[str, LocalSymbol],
    ] = {
        "root": {}
    }

    scope_imports: dict[
        str,
        dict[str, str],
    ] = {
        "root": {}
    }

    scope_class: dict[str, str | None] = {
        "root": None
    }

    definitions_by_qualified_name: dict[
        str,
        LocalSymbol,
    ] = {}

    def ast_node_id(node: ast.AST) -> str:
        return create_node_id(
            file_id,
            structural_paths[id(node)],
            type(node).__name__,
        )

    def register_imports(
        statements: list[ast.stmt],
        scope_path: str,
    ) -> None:
        imports = scope_imports.setdefault(
            scope_path,
            {},
        )

        for statement in statements:
            if isinstance(statement, ast.Import):
                for alias in statement.names:
                    local_name = (
                        alias.asname
                        or alias.name.split(".")[0]
                    )

                    imports[local_name] = alias.name

            elif isinstance(
                statement,
                ast.ImportFrom,
            ):
                module = statement.module or ""

                if statement.level:
                    prefix = "." * statement.level
                    module = f"{prefix}{module}"

                for alias in statement.names:
                    if alias.name == "*":
                        continue

                    local_name = (
                        alias.asname
                        or alias.name
                    )

                    if module:
                        qualified_name = (
                            f"{module}.{alias.name}"
                        )
                    else:
                        qualified_name = alias.name

                    imports[local_name] = qualified_name

    def register_scope(
        *,
        scope_node: ast.AST,
        body: list[ast.stmt],
        scope_path: str,
        parent_scope_path: str | None,
        qualified_prefix: str,
        current_class: str | None,
    ) -> None:
        scope_parent[scope_path] = parent_scope_path
        scope_symbols.setdefault(scope_path, {})
        scope_imports.setdefault(scope_path, {})
        scope_class[scope_path] = current_class

        register_imports(
            body,
            scope_path,
        )

        # Pass 1: đăng ký function/class trong scope hiện tại.
        for statement in body:
            if not isinstance(
                statement,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                continue

            qualified_name = (
                f"{qualified_prefix}.{statement.name}"
                if qualified_prefix
                else statement.name
            )

            symbol = LocalSymbol(
                node_id=ast_node_id(statement),
                qualified_name=qualified_name,
            )

            scope_symbols[
                scope_path
            ][statement.name] = symbol

            definitions_by_qualified_name[
                qualified_name
            ] = symbol

        # Pass 2: tạo scope con.
        for statement in body:
            if not isinstance(
                statement,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                    ast.ClassDef,
                ),
            ):
                continue

            child_scope_path = structural_paths[
                id(statement)
            ]

            qualified_name = (
                f"{qualified_prefix}.{statement.name}"
                if qualified_prefix
                else statement.name
            )

            child_class = current_class

            if isinstance(statement, ast.ClassDef):
                child_class = qualified_name

            register_scope(
                scope_node=statement,
                body=statement.body,
                scope_path=child_scope_path,
                parent_scope_path=scope_path,
                qualified_prefix=qualified_name,
                current_class=child_class,
            )

    register_scope(
        scope_node=tree,
        body=tree.body,
        scope_path="root",
        parent_scope_path=None,
        qualified_prefix=module_name,
        current_class=None,
    )

    def find_local_symbol(
        name: str,
        scope_path: str,
    ) -> LocalSymbol | None:
        current_scope: str | None = scope_path

        while current_scope is not None:
            symbol = scope_symbols.get(
                current_scope,
                {},
            ).get(name)

            if symbol is not None:
                return symbol

            current_scope = scope_parent.get(
                current_scope
            )

        return None

    def find_import(
        name: str,
        scope_path: str,
    ) -> str | None:
        current_scope: str | None = scope_path

        while current_scope is not None:
            imported_name = scope_imports.get(
                current_scope,
                {},
            ).get(name)

            if imported_name is not None:
                return imported_name

            current_scope = scope_parent.get(
                current_scope
            )

        return None

    def create_symbol_target(
        *,
        qualified_name: str,
        resolution: str,
    ) -> str:
        """
        Tạo synthetic target cho imported hoặc unresolved call.
        """
        target_id = stable_hash(
            "call-target",
            repo_id,
            qualified_name,
        )

        if target_id in created_node_ids:
            return target_id

        created_node_ids.add(target_id)

        result.node_events.append(
            NodeEvent(
                event_id=create_event_id(
                    "UPSERT",
                    target_id,
                    content_hash,
                ),
                op="UPSERT",
                repo_id=repo_id,
                commit_sha=commit_sha,
                file_id=file_id,
                content_hash=content_hash,
                path=relative_path,
                node=NodePayload(
                    node_id=target_id,
                    node_kind="SYMBOL",
                    ast_type="CALL_TARGET",
                    structural_path=(
                        f"symbol::{qualified_name}"
                    ),
                    name=qualified_name.split(".")[-1],
                    properties={
                        "qualified_name":
                            qualified_name,
                        "resolution":
                            resolution,
                    },
                ),
            )
        )

        return target_id

    def resolve_call(
        *,
        callee: str,
        scope_path: str,
    ) -> tuple[str, str, str]:
        """
        Trả về:
        target_id, target_qualified_name, resolution
        """
        parts = callee.split(".")
        first_part = parts[0]

        # foo()
        if len(parts) == 1:
            local_symbol = find_local_symbol(
                callee,
                scope_path,
            )

            if local_symbol is not None:
                return (
                    local_symbol.node_id,
                    local_symbol.qualified_name,
                    "EXACT_LOCAL",
                )

            imported_name = find_import(
                callee,
                scope_path,
            )

            if imported_name is not None:
                target_id = create_symbol_target(
                    qualified_name=imported_name,
                    resolution="IMPORTED_SYMBOL",
                )

                return (
                    target_id,
                    imported_name,
                    "IMPORTED_SYMBOL",
                )

            target_id = create_symbol_target(
                qualified_name=callee,
                resolution="SYMBOLIC",
            )

            return (
                target_id,
                callee,
                "SYMBOLIC",
            )

        # self.method() hoặc cls.method()
        if first_part in {"self", "cls"}:
            class_name = scope_class.get(
                scope_path
            )

            if class_name is not None:
                candidate_name = (
                    f"{class_name}.{parts[-1]}"
                )

                local_symbol = (
                    definitions_by_qualified_name.get(
                        candidate_name
                    )
                )

                if local_symbol is not None:
                    return (
                        local_symbol.node_id,
                        local_symbol.qualified_name,
                        "EXACT_LOCAL",
                    )

        # alias.function()
        imported_prefix = find_import(
            first_part,
            scope_path,
        )

        if imported_prefix is not None:
            qualified_name = ".".join(
                [
                    imported_prefix,
                    *parts[1:],
                ]
            )

            target_id = create_symbol_target(
                qualified_name=qualified_name,
                resolution="IMPORTED_SYMBOL",
            )

            return (
                target_id,
                qualified_name,
                "IMPORTED_SYMBOL",
            )

        target_id = create_symbol_target(
            qualified_name=callee,
            resolution="SYMBOLIC",
        )

        return (
            target_id,
            callee,
            "SYMBOLIC",
        )

    def add_call_edge(
        *,
        call_node: ast.Call,
        callee: str,
        scope_path: str,
    ) -> None:
        call_node_id = ast_node_id(call_node)

        (
            target_id,
            target_qualified_name,
            resolution,
        ) = resolve_call(
            callee=callee,
            scope_path=scope_path,
        )

        edge_id = create_edge_id(
            "CALLS",
            call_node_id,
            target_id,
            f"{resolution}:{callee}",
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
                    edge_type="CALLS",
                    src_id=call_node_id,
                    dst_id=target_id,
                    properties={
                        "callee": callee,
                        "resolution": resolution,
                        "target_qualified_name":
                            target_qualified_name,
                    },
                ),
            )
        )

    def visit(
        node: ast.AST,
        scope_path: str,
    ) -> None:
        current_scope = scope_path

        if isinstance(
            node,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
            ),
        ):
            current_scope = structural_paths[
                id(node)
            ]

        if isinstance(node, ast.Call):
            callee = expression_to_dotted_name(
                node.func
            )

            if callee is None:
                callee = ast.dump(
                    node.func,
                    include_attributes=False,
                )

            add_call_edge(
                call_node=node,
                callee=callee,
                scope_path=current_scope,
            )

        for child in ast.iter_child_nodes(node):
            visit(
                child,
                current_scope,
            )

    visit(
        tree,
        "root",
    )

    return result