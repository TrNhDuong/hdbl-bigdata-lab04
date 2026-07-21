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
from src.parser_service.kafka_producer import (
    KafkaEventPublisher,
)
from src.parser_service.cfg_builder import (
    extract_cfg_events,
)
from src.parser_service.dfg_builder import (
    extract_dfg_events,
)
from src.parser_service.call_builder import (
    extract_call_events,
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

    parse_file_parser.add_argument(
        "--publish-kafka",
        action="store_true",
        help="Gửi event vào Kafka sau khi parse",
    )

    parse_file_parser.add_argument(
        "--bootstrap-servers",
        default="localhost:9092",
        help="Kafka bootstrap servers",
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

    cfg_extraction = extract_cfg_events(
        source=source_file.source,
        repo_id=args.repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        content_hash=source_file.content_hash,
        relative_path=source_file.relative_path,
    )

    dfg_extraction = extract_dfg_events(
        source=source_file.source,
        repo_id=args.repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        content_hash=source_file.content_hash,
        relative_path=source_file.relative_path,
    )

    call_extraction = extract_call_events(
        source=source_file.source,
        repo_id=args.repo_id,
        commit_sha=commit_sha,
        file_id=file_id,
        content_hash=source_file.content_hash,
        relative_path=source_file.relative_path,
    )

    all_node_events = (
        extraction.node_events
        + cfg_extraction.node_events
        + call_extraction.node_events
    )

    all_edge_events = (
        extraction.edge_events
        + cfg_extraction.edge_events
        + dfg_extraction.edge_events
        + call_extraction.edge_events
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
        cfg_edge_count=len(cfg_extraction.edge_events),
        dfg_edge_count=len(dfg_extraction.edge_events),
        call_edge_count=len(call_extraction.edge_events),
    )

    writer = LocalEventWriter(args.output)

    node_path = writer.write_events(
        "nodes.jsonl",
        all_node_events,
    )

    edge_path = writer.write_events(
        "edges.jsonl",
        all_edge_events,
    )

    metadata_path = writer.write_events(
        "metadata.jsonl",
        [metadata_event],
    )

    published_to_kafka = False

    if args.publish_kafka:
        publisher = KafkaEventPublisher(
            bootstrap_servers=args.bootstrap_servers,
        )

        published_node_count = (
            publisher.publish_node_events(
                all_node_events
            )
        )

        published_edge_count = (
            publisher.publish_edge_events(
                all_edge_events
            )
        )

        publisher.publish_metadata_event(
            metadata_event
        )

        publisher.flush()
        published_to_kafka = True

        print("Kafka publishing completed")
        print(
            f"Published node events: "
            f"{published_node_count}"
        )
        print(
            f"Published edge events: "
            f"{published_edge_count}"
        )
        print("Published metadata events: 1")

    print("Parse completed")
    print(f"File: {source_file.relative_path}")
    print(f"File ID: {file_id}")
    print(f"Content hash: {source_file.content_hash}")
    print(f"AST nodes: {len(extraction.node_events)}")
    print(f"CFG synthetic nodes: {len(cfg_extraction.node_events)}")
    print(f"AST edges: {len(extraction.edge_events)}")
    print(f"CFG edges: {len(cfg_extraction.edge_events)}")
    print(f"DFG edges: {len(dfg_extraction.edge_events)}")
    print(f"Call target nodes: {len(call_extraction.node_events)}")
    print(f"CALLS edges: {len(call_extraction.edge_events)}")
    print(f"Parse duration: {parse_duration_ms:.3f} ms")
    print(f"Nodes output: {node_path}")
    print(f"Edges output: {edge_path}")
    print(f"Metadata output: {metadata_path}")

    if not published_to_kafka:
        print(
            "Kafka publishing skipped. "
            "Use --publish-kafka to enable it."
        )
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