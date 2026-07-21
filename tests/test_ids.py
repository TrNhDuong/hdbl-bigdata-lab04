from src.parser_service.ids import (
    create_edge_id,
    create_file_id,
    create_node_id,
)


def test_same_file_input_produces_same_id() -> None:
    first = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    second = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    assert first == second


def test_windows_and_posix_paths_produce_same_file_id() -> None:
    windows_id = create_file_id(
        "github:huggingface/trl",
        r"trl\data_utils.py",
    )

    posix_id = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    assert windows_id == posix_id


def test_different_files_produce_different_ids() -> None:
    first = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    second = create_file_id(
        "github:huggingface/trl",
        "trl/models/utils.py",
    )

    assert first != second


def test_same_node_input_produces_same_id() -> None:
    file_id = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    first = create_node_id(
        file_id,
        "body[0]",
        "FunctionDef",
    )

    second = create_node_id(
        file_id,
        "body[0]",
        "FunctionDef",
    )

    assert first == second


def test_different_structural_paths_produce_different_node_ids() -> None:
    file_id = create_file_id(
        "github:huggingface/trl",
        "trl/data_utils.py",
    )

    first = create_node_id(
        file_id,
        "body[0]",
        "FunctionDef",
    )

    second = create_node_id(
        file_id,
        "body[1]",
        "FunctionDef",
    )

    assert first != second


def test_same_edge_input_produces_same_id() -> None:
    first = create_edge_id(
        "AST_CHILD",
        "parent-node",
        "child-node",
        "body[0]",
    )

    second = create_edge_id(
        "AST_CHILD",
        "parent-node",
        "child-node",
        "body[0]",
    )

    assert first == second