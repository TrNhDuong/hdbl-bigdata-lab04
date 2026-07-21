from src.parser_service.cfg_builder import (
    extract_cfg_events,
)
from src.parser_service.ids import create_file_id


SOURCE = """\
def absolute_value(value: int) -> int:
    if value >= 0:
        result = value
    else:
        result = -value

    return result
"""


def extract_sample():
    file_id = create_file_id(
        "github:huggingface/trl",
        "sample.py",
    )

    return extract_cfg_events(
        source=SOURCE,
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id=file_id,
        content_hash="content-hash-123",
        relative_path="sample.py",
    )


def test_cfg_creates_entry_and_exit_nodes() -> None:
    result = extract_sample()

    node_types = {
        event.node.ast_type
        for event in result.node_events
    }

    assert "CFG_ENTRY" in node_types
    assert "CFG_EXIT" in node_types


def test_cfg_creates_cfg_next_edges() -> None:
    result = extract_sample()

    assert len(result.edge_events) > 0

    assert all(
        event.edge.edge_type == "CFG_NEXT"
        for event in result.edge_events
    )


def test_cfg_contains_true_and_false_branches() -> None:
    result = extract_sample()

    branches = {
        event.edge.properties.get("branch")
        for event in result.edge_events
    }

    assert "TRUE" in branches
    assert "FALSE" in branches


def test_cfg_contains_return_edge() -> None:
    result = extract_sample()

    branches = {
        event.edge.properties.get("branch")
        for event in result.edge_events
    }

    assert "RETURN" in branches


def test_cfg_ids_are_stable() -> None:
    first = extract_sample()
    second = extract_sample()

    first_node_ids = [
        event.node.node_id
        for event in first.node_events
    ]

    second_node_ids = [
        event.node.node_id
        for event in second.node_events
    ]

    first_edge_ids = [
        event.edge.edge_id
        for event in first.edge_events
    ]

    second_edge_ids = [
        event.edge.edge_id
        for event in second.edge_events
    ]

    assert first_node_ids == second_node_ids
    assert first_edge_ids == second_edge_ids


def test_cfg_has_no_duplicate_edge_ids() -> None:
    result = extract_sample()

    edge_ids = [
        event.edge.edge_id
        for event in result.edge_events
    ]

    assert len(edge_ids) == len(set(edge_ids))