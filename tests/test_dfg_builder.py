from src.parser_service.dfg_builder import (
    extract_dfg_events,
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

    return extract_dfg_events(
        source=SOURCE,
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id=file_id,
        content_hash="content-hash-123",
        relative_path="sample.py",
    )


def test_dfg_creates_def_use_edges() -> None:
    result = extract_sample()

    assert len(result.edge_events) >= 2


def test_all_edges_are_dfg_def_use() -> None:
    result = extract_sample()

    assert all(
        event.edge.edge_type == "DFG_DEF_USE"
        for event in result.edge_events
    )


def test_dfg_contains_argument_flow() -> None:
    result = extract_sample()

    symbols = {
        event.edge.properties.get("symbol")
        for event in result.edge_events
    }

    assert "value" in symbols


def test_dfg_contains_assignment_flow() -> None:
    result = extract_sample()

    symbols = {
        event.edge.properties.get("symbol")
        for event in result.edge_events
    }

    assert "result" in symbols


def test_dfg_ids_are_stable() -> None:
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


def test_dfg_has_no_duplicate_edge_ids() -> None:
    result = extract_sample()

    edge_ids = [
        event.edge.edge_id
        for event in result.edge_events
    ]

    assert len(edge_ids) == len(set(edge_ids))

BRANCH_SOURCE = """\
def choose(flag: bool) -> int:
    if flag:
        result = 1
    else:
        result = 2

    return result
"""


def test_branch_merge_keeps_both_definitions() -> None:
    file_id = create_file_id(
        "github:huggingface/trl",
        "branch.py",
    )

    extraction = extract_dfg_events(
        source=BRANCH_SOURCE,
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id=file_id,
        content_hash="branch-content-hash",
        relative_path="branch.py",
    )

    result_edges = [
        event
        for event in extraction.edge_events
        if event.edge.properties.get("symbol")
        == "result"
    ]

    # result trong return có thể nhận dữ liệu từ cả hai nhánh.
    assert len(result_edges) == 2