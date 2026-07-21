from __future__ import annotations

import ast
from collections.abc import Iterable
from dataclasses import dataclass, field

from src.parser_service.cfg_builder import (
    build_structural_path_index,
)
from src.parser_service.event_models import (
    EdgeEvent,
    EdgePayload,
)
from src.parser_service.ids import (
    create_edge_id,
    create_event_id,
    create_node_id,
)


DefinitionEnvironment = dict[str, set[str]]


@dataclass
class DfgExtractionResult:
    edge_events: list[EdgeEvent] = field(
        default_factory=list
    )


def clone_environment(
    environment: DefinitionEnvironment,
) -> DefinitionEnvironment:
    return {
        symbol: set(definitions)
        for symbol, definitions in environment.items()
    }


def merge_environments(
    *environments: DefinitionEnvironment,
) -> DefinitionEnvironment:
    merged: DefinitionEnvironment = {}

    for environment in environments:
        for symbol, definitions in environment.items():
            merged.setdefault(symbol, set()).update(
                definitions
            )

    return merged


def extract_dfg_events(
    *,
    source: str,
    repo_id: str,
    commit_sha: str,
    file_id: str,
    content_hash: str,
    relative_path: str,
) -> DfgExtractionResult:
    """
    Tạo conservative DFG nối definition node với use node.

    Các trường hợp được hỗ trợ:
    - Function arguments
    - Assign, AnnAssign, AugAssign
    - NamedExpr
    - for target
    - with alias
    - except alias
    - import và import-from
    - if/else branch merge
    - loop body merge
    """

    tree = ast.parse(
        source,
        filename=relative_path,
        type_comments=True,
    )

    structural_paths = build_structural_path_index(tree)

    result = DfgExtractionResult()
    created_edge_ids: set[str] = set()

    def get_ast_node_id(node: ast.AST) -> str:
        return create_node_id(
            file_id,
            structural_paths[id(node)],
            type(node).__name__,
        )

    def add_def_use_edge(
        definition_id: str,
        use_node: ast.AST,
        symbol: str,
        scope_path: str,
    ) -> None:
        use_id = get_ast_node_id(use_node)

        edge_id = create_edge_id(
            "DFG_DEF_USE",
            definition_id,
            use_id,
            symbol,
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
                    edge_type="DFG_DEF_USE",
                    src_id=definition_id,
                    dst_id=use_id,
                    properties={
                        "symbol": symbol,
                        "scope_path": scope_path,
                    },
                ),
            )
        )

    def read_expression(
        expression: ast.AST | None,
        environment: DefinitionEnvironment,
        scope_path: str,
    ) -> None:
        if expression is None:
            return

        for node in ast.walk(expression):
            if not isinstance(node, ast.Name):
                continue

            if not isinstance(node.ctx, ast.Load):
                continue

            definitions = environment.get(
                node.id,
                set(),
            )

            for definition_id in definitions:
                add_def_use_edge(
                    definition_id,
                    node,
                    node.id,
                    scope_path,
                )

    def target_definitions(
        target: ast.AST,
    ) -> list[tuple[str, str]]:
        """
        Trả về danh sách (symbol, definition_node_id).
        """

        definitions: list[tuple[str, str]] = []

        if isinstance(target, ast.Name):
            definitions.append(
                (
                    target.id,
                    get_ast_node_id(target),
                )
            )

        elif isinstance(
            target,
            (
                ast.Tuple,
                ast.List,
            ),
        ):
            for element in target.elts:
                definitions.extend(
                    target_definitions(element)
                )

        elif isinstance(target, ast.Starred):
            definitions.extend(
                target_definitions(target.value)
            )

        return definitions

    def define_target(
        target: ast.AST,
        environment: DefinitionEnvironment,
    ) -> None:
        for symbol, definition_id in target_definitions(
            target
        ):
            environment[symbol] = {
                definition_id
            }

    def process_statement_list(
        statements: Iterable[ast.stmt],
        environment: DefinitionEnvironment,
        scope_path: str,
    ) -> DefinitionEnvironment:
        current = clone_environment(environment)

        for statement in statements:
            current = process_statement(
                statement,
                current,
                scope_path,
            )

        return current

    def process_statement(
        statement: ast.stmt,
        environment: DefinitionEnvironment,
        scope_path: str,
    ) -> DefinitionEnvironment:
        current = clone_environment(environment)

        if isinstance(statement, ast.Assign):
            read_expression(
                statement.value,
                current,
                scope_path,
            )

            for target in statement.targets:
                define_target(
                    target,
                    current,
                )

            return current

        if isinstance(statement, ast.AnnAssign):
            read_expression(
                statement.annotation,
                current,
                scope_path,
            )

            read_expression(
                statement.value,
                current,
                scope_path,
            )

            define_target(
                statement.target,
                current,
            )

            return current

        if isinstance(statement, ast.AugAssign):
            # x += value vừa đọc x cũ, vừa tạo definition mới.
            read_expression(
                statement.target,
                current,
                scope_path,
            )

            read_expression(
                statement.value,
                current,
                scope_path,
            )

            define_target(
                statement.target,
                current,
            )

            return current

        if isinstance(statement, ast.Expr):
            read_expression(
                statement.value,
                current,
                scope_path,
            )
            return current

        if isinstance(statement, ast.Return):
            read_expression(
                statement.value,
                current,
                scope_path,
            )
            return current

        if isinstance(statement, ast.Raise):
            read_expression(
                statement.exc,
                current,
                scope_path,
            )
            read_expression(
                statement.cause,
                current,
                scope_path,
            )
            return current

        if isinstance(statement, ast.Assert):
            read_expression(
                statement.test,
                current,
                scope_path,
            )
            read_expression(
                statement.msg,
                current,
                scope_path,
            )
            return current

        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    current.pop(
                        target.id,
                        None,
                    )

            return current

        if isinstance(statement, ast.If):
            read_expression(
                statement.test,
                current,
                scope_path,
            )

            body_environment = process_statement_list(
                statement.body,
                clone_environment(current),
                scope_path,
            )

            else_environment = process_statement_list(
                statement.orelse,
                clone_environment(current),
                scope_path,
            )

            return merge_environments(
                body_environment,
                else_environment,
            )

        if isinstance(
            statement,
            (
                ast.For,
                ast.AsyncFor,
            ),
        ):
            read_expression(
                statement.iter,
                current,
                scope_path,
            )

            loop_environment = clone_environment(
                current
            )

            define_target(
                statement.target,
                loop_environment,
            )

            body_environment = process_statement_list(
                statement.body,
                loop_environment,
                scope_path,
            )

            else_environment = process_statement_list(
                statement.orelse,
                clone_environment(current),
                scope_path,
            )

            return merge_environments(
                current,
                body_environment,
                else_environment,
            )

        if isinstance(statement, ast.While):
            read_expression(
                statement.test,
                current,
                scope_path,
            )

            body_environment = process_statement_list(
                statement.body,
                clone_environment(current),
                scope_path,
            )

            else_environment = process_statement_list(
                statement.orelse,
                clone_environment(current),
                scope_path,
            )

            return merge_environments(
                current,
                body_environment,
                else_environment,
            )

        if isinstance(
            statement,
            (
                ast.With,
                ast.AsyncWith,
            ),
        ):
            with_environment = clone_environment(
                current
            )

            for item in statement.items:
                read_expression(
                    item.context_expr,
                    with_environment,
                    scope_path,
                )

                if item.optional_vars is not None:
                    define_target(
                        item.optional_vars,
                        with_environment,
                    )

            return process_statement_list(
                statement.body,
                with_environment,
                scope_path,
            )

        try_types: tuple[type[ast.AST], ...] = (
            ast.Try,
        )

        if hasattr(ast, "TryStar"):
            try_types = try_types + (
                ast.TryStar,
            )

        if isinstance(statement, try_types):
            body_environment = process_statement_list(
                statement.body,
                clone_environment(current),
                scope_path,
            )

            branch_environments = [
                body_environment
            ]

            for handler in statement.handlers:
                handler_environment = clone_environment(
                    current
                )

                if handler.type is not None:
                    read_expression(
                        handler.type,
                        handler_environment,
                        scope_path,
                    )

                if handler.name:
                    handler_environment[
                        handler.name
                    ] = {
                        get_ast_node_id(handler)
                    }

                handler_environment = (
                    process_statement_list(
                        handler.body,
                        handler_environment,
                        scope_path,
                    )
                )

                branch_environments.append(
                    handler_environment
                )

            merged = merge_environments(
                *branch_environments
            )

            merged = process_statement_list(
                statement.orelse,
                merged,
                scope_path,
            )

            merged = process_statement_list(
                statement.finalbody,
                merged,
                scope_path,
            )

            return merged

        if isinstance(
            statement,
            (
                ast.Import,
                ast.ImportFrom,
            ),
        ):
            for alias in statement.names:
                if alias.asname:
                    symbol = alias.asname
                else:
                    symbol = alias.name.split(".")[0]

                current[symbol] = {
                    get_ast_node_id(alias)
                }

            return current

        if isinstance(
            statement,
            (
                ast.FunctionDef,
                ast.AsyncFunctionDef,
            ),
        ):
            # Decorator và default expression chạy ở scope ngoài.
            for decorator in statement.decorator_list:
                read_expression(
                    decorator,
                    current,
                    scope_path,
                )

            for default in statement.args.defaults:
                read_expression(
                    default,
                    current,
                    scope_path,
                )

            for default in statement.args.kw_defaults:
                read_expression(
                    default,
                    current,
                    scope_path,
                )

            # Tên function được định nghĩa ở scope ngoài.
            current[statement.name] = {
                get_ast_node_id(statement)
            }

            process_function_scope(statement)
            return current

        if isinstance(statement, ast.ClassDef):
            for decorator in statement.decorator_list:
                read_expression(
                    decorator,
                    current,
                    scope_path,
                )

            for base in statement.bases:
                read_expression(
                    base,
                    current,
                    scope_path,
                )

            current[statement.name] = {
                get_ast_node_id(statement)
            }

            process_class_scope(statement)
            return current

        if isinstance(statement, ast.Match):
            read_expression(
                statement.subject,
                current,
                scope_path,
            )

            case_environments = []

            for match_case in statement.cases:
                case_environment = clone_environment(
                    current
                )

                read_expression(
                    match_case.guard,
                    case_environment,
                    scope_path,
                )

                case_environment = (
                    process_statement_list(
                        match_case.body,
                        case_environment,
                        scope_path,
                    )
                )

                case_environments.append(
                    case_environment
                )

            if case_environments:
                return merge_environments(
                    current,
                    *case_environments,
                )

            return current

        # Fallback: đọc các expression nằm trong statement.
        read_expression(
            statement,
            current,
            scope_path,
        )

        return current

    def process_function_scope(
        function: ast.FunctionDef
        | ast.AsyncFunctionDef,
    ) -> None:
        function_path = structural_paths[
            id(function)
        ]

        environment: DefinitionEnvironment = {}

        arguments = [
            *function.args.posonlyargs,
            *function.args.args,
            *function.args.kwonlyargs,
        ]

        if function.args.vararg is not None:
            arguments.append(
                function.args.vararg
            )

        if function.args.kwarg is not None:
            arguments.append(
                function.args.kwarg
            )

        for argument in arguments:
            environment[argument.arg] = {
                get_ast_node_id(argument)
            }

        process_statement_list(
            function.body,
            environment,
            function_path,
        )

    def process_class_scope(
        class_node: ast.ClassDef,
    ) -> None:
        class_path = structural_paths[
            id(class_node)
        ]

        process_statement_list(
            class_node.body,
            {},
            class_path,
        )

    process_statement_list(
        tree.body,
        {},
        "root",
    )

    return result