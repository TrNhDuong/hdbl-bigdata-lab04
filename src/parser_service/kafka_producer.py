from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from confluent_kafka import Producer
from pydantic import BaseModel

from src.parser_service.event_models import (
    EdgeEvent,
    MetadataEvent,
    NodeEvent,
)


NODE_TOPIC = "trl-cpg-nodes-v1"
EDGE_TOPIC = "trl-cpg-edges-v1"
METADATA_TOPIC = "trl-source-metadata-v1"
ERROR_TOPIC = "trl-parser-errors-v1"


class KafkaPublishError(RuntimeError):
    """Lỗi xảy ra khi event không được Kafka xác nhận."""


class KafkaEventPublisher:
    def __init__(
        self,
        bootstrap_servers: str,
        producer: Any | None = None,
    ) -> None:
        self._delivery_errors: list[str] = []

        self._producer = producer or Producer(
            {
                "bootstrap.servers": bootstrap_servers,
                "client.id": "trl-cpg-parser-service",
                "enable.idempotence": True,
                "acks": "all",
                "compression.type": "snappy",
                "delivery.timeout.ms": 120_000,
                "broker.address.family": "v4",
            }
        )

    def _delivery_callback(
        self,
        error: object | None,
        message: object,
    ) -> None:
        if error is not None:
            self._delivery_errors.append(str(error))

    def _publish_event(
        self,
        *,
        topic: str,
        key: str,
        event: BaseModel,
    ) -> None:
        value = event.model_dump_json(
            by_alias=True
        ).encode("utf-8")

        encoded_key = key.encode("utf-8")

        while True:
            try:
                self._producer.produce(
                    topic=topic,
                    key=encoded_key,
                    value=value,
                    on_delivery=self._delivery_callback,
                )
                break
            except BufferError:
                # Hàng đợi producer đầy, chờ Kafka xử lý bớt.
                self._producer.poll(0.1)

        # Cho phép callback của các message trước được xử lý.
        self._producer.poll(0)

    def publish_node_events(
        self,
        events: Iterable[NodeEvent],
    ) -> int:
        count = 0

        for event in events:
            self._publish_event(
                topic=NODE_TOPIC,
                key=event.node.node_id,
                event=event,
            )
            count += 1

        return count

    def publish_edge_events(
        self,
        events: Iterable[EdgeEvent],
    ) -> int:
        count = 0

        for event in events:
            self._publish_event(
                topic=EDGE_TOPIC,
                key=event.edge.edge_id,
                event=event,
            )
            count += 1

        return count

    def publish_metadata_event(
        self,
        event: MetadataEvent,
    ) -> None:
        self._publish_event(
            topic=METADATA_TOPIC,
            key=event.file_id,
            event=event,
        )

    def flush(
        self,
        timeout_seconds: float = 30.0,
    ) -> None:
        remaining_messages = self._producer.flush(
            timeout_seconds
        )

        if remaining_messages > 0:
            raise KafkaPublishError(
                f"{remaining_messages} Kafka message(s) "
                "chưa được giao sau khi hết thời gian chờ."
            )

        if self._delivery_errors:
            error_summary = "; ".join(
                self._delivery_errors[:5]
            )

            raise KafkaPublishError(
                "Kafka delivery failed: "
                f"{error_summary}"
            )