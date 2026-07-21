from typing import Any

from src.parser_service.event_models import (
    EdgeEvent,
    EdgePayload,
    MetadataCounts,
    MetadataEvent,
    NodeEvent,
    NodePayload,
)
from src.parser_service.kafka_producer import (
    EDGE_TOPIC,
    METADATA_TOPIC,
    NODE_TOPIC,
    KafkaEventPublisher,
)


class FakeProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    def produce(
        self,
        *,
        topic: str,
        key: bytes,
        value: bytes,
        on_delivery: Any,
    ) -> None:
        self.messages.append(
            {
                "topic": topic,
                "key": key,
                "value": value,
            }
        )

        on_delivery(None, object())

    def poll(self, timeout: float) -> None:
        return None

    def flush(self, timeout: float) -> int:
        return 0


def create_node_event() -> NodeEvent:
    return NodeEvent(
        event_id="node-event-1",
        repo_id="github:huggingface/trl",
        commit_sha="commit-1",
        file_id="file-1",
        content_hash="hash-1",
        path="trl/example.py",
        node=NodePayload(
            node_id="node-1",
            ast_type="FunctionDef",
            structural_path="root.body[0]",
        ),
    )


def create_edge_event() -> EdgeEvent:
    return EdgeEvent(
        event_id="edge-event-1",
        repo_id="github:huggingface/trl",
        commit_sha="commit-1",
        file_id="file-1",
        content_hash="hash-1",
        path="trl/example.py",
        edge=EdgePayload(
            edge_id="edge-1",
            edge_type="AST_CHILD",
            src_id="node-1",
            dst_id="node-2",
        ),
    )


def create_metadata_event() -> MetadataEvent:
    return MetadataEvent(
        event_id="metadata-event-1",
        repo_id="github:huggingface/trl",
        commit_sha="commit-1",
        file_id="file-1",
        content_hash="hash-1",
        path="trl/example.py",
        document_id="file-1",
        size_bytes=100,
        line_count=10,
        parse_duration_ms=2.5,
        status="SUCCESS",
        counts=MetadataCounts(
            nodes=2,
            ast_edges=1,
        ),
    )


def test_node_event_uses_node_topic_and_node_id_key() -> None:
    fake_producer = FakeProducer()

    publisher = KafkaEventPublisher(
        bootstrap_servers="unused:9092",
        producer=fake_producer,
    )

    publisher.publish_node_events(
        [create_node_event()]
    )
    publisher.flush()

    message = fake_producer.messages[0]

    assert message["topic"] == NODE_TOPIC
    assert message["key"] == b"node-1"


def test_edge_event_uses_edge_topic_and_edge_id_key() -> None:
    fake_producer = FakeProducer()

    publisher = KafkaEventPublisher(
        bootstrap_servers="unused:9092",
        producer=fake_producer,
    )

    publisher.publish_edge_events(
        [create_edge_event()]
    )
    publisher.flush()

    message = fake_producer.messages[0]

    assert message["topic"] == EDGE_TOPIC
    assert message["key"] == b"edge-1"


def test_metadata_event_uses_file_id_key() -> None:
    fake_producer = FakeProducer()

    publisher = KafkaEventPublisher(
        bootstrap_servers="unused:9092",
        producer=fake_producer,
    )

    publisher.publish_metadata_event(
        create_metadata_event()
    )
    publisher.flush()

    message = fake_producer.messages[0]

    assert message["topic"] == METADATA_TOPIC
    assert message["key"] == b"file-1"