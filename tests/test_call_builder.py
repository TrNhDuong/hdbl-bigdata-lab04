from src.parser_service.call_builder import (
    extract_call_events,
)
from src.parser_service.ids import create_file_id


def extract_source(source: str):
    file_id = create_file_id(
        "github:huggingface/trl",
        "sample.py",
    )

    return extract_call_events(
        source=source,
        repo_id="github:huggingface/trl",
        commit_sha="commit-123",
        file_id=file_id,
        content_hash="content-hash-123",
        relative_path="sample.py",
    )


def test_local_function_call_is_exact() -> None:
    source = """\
def helper(value):
    return value

def run():
    return helper(10)
"""

    result = extract_source(source)

    exact_edges = [
        event
        for event in result.edge_events
        if event.edge.properties.get(
            "resolution"
        ) == "EXACT_LOCAL"
    ]

    assert len(exact_edges) == 1

    assert (
        exact_edges[0].edge.properties[
            "callee"
        ]
        == "helper"
    )


def test_import_alias_is_resolved() -> None:
    source = """\
import numpy as np

def run(values):
    return np.array(values)
"""

    result = extract_source(source)

    imported_edges = [
        event
        for event in result.edge_events
        if event.edge.properties.get(
            "resolution"
        ) == "IMPORTED_SYMBOL"
    ]

    assert len(imported_edges) == 1

    assert (
        imported_edges[0].edge.properties[
            "target_qualified_name"
        ]
        == "numpy.array"
    )


def test_from_import_alias_is_resolved() -> None:
    source = """\
from package.tools import transform as apply_transform

def run(value):
    return apply_transform(value)
"""

    result = extract_source(source)

    imported_edges = [
        event
        for event in result.edge_events
        if event.edge.properties.get(
            "resolution"
        ) == "IMPORTED_SYMBOL"
    ]

    assert len(imported_edges) == 1

    assert (
        imported_edges[0].edge.properties[
            "target_qualified_name"
        ]
        == "package.tools.transform"
    )


def test_unknown_call_becomes_symbolic() -> None:
    source = """\
def run(value):
    return unknown_function(value)
"""

    result = extract_source(source)

    symbolic_edges = [
        event
        for event in result.edge_events
        if event.edge.properties.get(
            "resolution"
        ) == "SYMBOLIC"
    ]

    assert len(symbolic_edges) == 1


def test_method_call_on_self_is_exact() -> None:
    source = """\
class Processor:
    def transform(self, value):
        return value

    def run(self, value):
        return self.transform(value)
"""

    result = extract_source(source)

    exact_edges = [
        event
        for event in result.edge_events
        if event.edge.properties.get(
            "resolution"
        ) == "EXACT_LOCAL"
    ]

    assert len(exact_edges) == 1

    assert (
        exact_edges[0].edge.properties[
            "callee"
        ]
        == "self.transform"
    )


def test_call_ids_are_stable() -> None:
    source = """\
def helper(value):
    return value

def run():
    return helper(10)
"""

    first = extract_source(source)
    second = extract_source(source)

    first_edge_ids = [
        event.edge.edge_id
        for event in first.edge_events
    ]

    second_edge_ids = [
        event.edge.edge_id
        for event in second.edge_events
    ]

    first_node_ids = [
        event.node.node_id
        for event in first.node_events
    ]

    second_node_ids = [
        event.node.node_id
        for event in second.node_events
    ]

    assert first_edge_ids == second_edge_ids
    assert first_node_ids == second_node_ids


def test_no_duplicate_call_edges() -> None:
    source = """\
def run(value):
    print(value)
    print(value)
"""

    result = extract_source(source)

    edge_ids = [
        event.edge.edge_id
        for event in result.edge_events
    ]

    assert len(edge_ids) == len(set(edge_ids))