from src.parser_service.ast_extractor import (
    extract_ast_events,
)
from src.parser_service.ids import create_file_id


SOURCE = """\
def add_one(value: int) -> int:
    result = value + 1
    return result
"""


def extract_sample():
    file_id = create_file_id(
        "github:huggingface/trl",
        "sample.py",
    )

    return extract_ast_events(
        source=SOURCE,
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id=file_id,
        content_hash="content-hash-123",
        relative_path="sample.py",
    )


def test_ast_extractor_creates_nodes() -> None:
    result = extract_sample()

    assert len(result.node_events) > 0


def test_ast_tree_has_one_less_edge_than_nodes() -> None:
    result = extract_sample()

    assert (
        len(result.edge_events)
        == len(result.node_events) - 1
    )


def test_ast_extractor_finds_function_definition() -> None:
    result = extract_sample()

    function_nodes = [
        event
        for event in result.node_events
        if event.node.ast_type == "FunctionDef"
    ]

    assert len(function_nodes) == 1
    assert function_nodes[0].node.name == "add_one"


def test_reprocessing_produces_same_node_ids() -> None:
    first = extract_sample()
    second = extract_sample()

    first_ids = [
        event.node.node_id
        for event in first.node_events
    ]

    second_ids = [
        event.node.node_id
        for event in second.node_events
    ]

    assert first_ids == second_ids


def test_all_ast_edges_have_stable_ids() -> None:
    first = extract_sample()
    second = extract_sample()

    first_ids = [
        event.edge.edge_id
        for event in first.edge_events
    ]

    second_ids = [
        event.edge.edge_id
        for event in second.edge_events
    ]

    assert first_ids == second_ids