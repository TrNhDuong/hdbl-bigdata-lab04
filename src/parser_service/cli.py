from __future__ import annotations

import argparse
import sys
from pathlib import Path
from time import perf_counter

from src.parser_service.ast_extractor import (
    extract_ast_events,
)
from src.parser_service.ids import create_file_id
from src.parser_service.local_writer import (
    LocalEventWriter,
)
from src.parser_service.metadata import (
    build_metadata_event,
)
from src.parser_service.source_reader import (
    get_git_commit_sha,
    read_source_file,
)


DEFAULT_REPO_ID = "github:huggingface/trl"


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Incremental Python CPG Parser Service",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    parse_file_parser = subparsers.add_parser(
        "parse-file",
        help="Parse một file Python",
    )

    parse_file_parser.add_argument(
        "--repo",
        required=True,
        help="Đường dẫn repository cần parse",
    )

    parse_file_parser.add_argument(
        "--path",
        required=True,
        help="Relative path của file Python",
    )

    parse_file_parser.add_argument(
        "--output",
        default="workspace/artifacts/sample_events",
        help="Thư mục chứa JSONL output",
    )

    parse_file_parser.add_argument(
        "--repo-id",
        default=DEFAULT_REPO_ID,
    )

    return parser


def parse_file_command(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo).resolve()

    source_file = read_source_file(
        repo_root,
        args.path,
    )

    commit_sha = get_git_commit_sha(repo_root)

    file_id = create_file_id(
        args.repo_id,
        source_file.relative_path,
    )

    start_time = perf_counter()

    extraction = extract_ast_events(
        source=source_file.source,
        repo_id=args.repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        content_hash=source_file.content_hash,
        relative_path=source_file.relative_path,
    )

    parse_duration_ms = (
        perf_counter() - start_time
    ) * 1000

    metadata_event = build_metadata_event(
        source_file=source_file,
        repo_id=args.repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        parse_duration_ms=parse_duration_ms,
        node_count=len(extraction.node_events),
        ast_edge_count=len(extraction.edge_events),
    )

    writer = LocalEventWriter(args.output)

    node_path = writer.write_events(
        "nodes.jsonl",
        extraction.node_events,
    )

    edge_path = writer.write_events(
        "edges.jsonl",
        extraction.edge_events,
    )

    metadata_path = writer.write_events(
        "metadata.jsonl",
        [metadata_event],
    )

    print("Parse completed")
    print(f"File: {source_file.relative_path}")
    print(f"File ID: {file_id}")
    print(f"Content hash: {source_file.content_hash}")
    print(f"AST nodes: {len(extraction.node_events)}")
    print(f"AST edges: {len(extraction.edge_events)}")
    print(
        f"Parse duration: "
        f"{parse_duration_ms:.3f} ms"
    )
    print(f"Nodes output: {node_path}")
    print(f"Edges output: {edge_path}")
    print(f"Metadata output: {metadata_path}")

    return 0


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        if args.command == "parse-file":
            return parse_file_command(args)

        parser.error(
            f"Unsupported command: {args.command}"
        )

    except Exception as exc:
        print(
            f"Parser failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )

        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())