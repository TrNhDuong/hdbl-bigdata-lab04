from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

CONNECT_URL = (
    "http://localhost:8083"
    "/connectors/neo4j-cpg-sink/config"
)

NODE_TOPIC = "trl-cpg-nodes-v1"
EDGE_TOPIC = "trl-cpg-edges-v1"


NODE_CYPHER = """
WITH __value AS value

MERGE (repository:Repository {
    repo_id: value.repo_id
})
SET
    repository.commit_sha = value.commit_sha,
    repository.updated_at = value.event_time

MERGE (source_file:SourceFile {
    file_id: value.file_id
})
SET
    source_file.repo_id = value.repo_id,
    source_file.path = value.path,
    source_file.commit_sha = value.commit_sha,
    source_file.content_hash = value.content_hash,
    source_file.updated_at = value.event_time

MERGE (node:CPGNode {
    node_id: value.node.node_id
})
SET
    node.file_id = value.file_id,
    node.content_hash = value.content_hash,
    node.node_kind = value.node.node_kind,
    node.ast_type = value.node.ast_type,
    node.structural_path = value.node.structural_path,
    node.lineno = value.node.lineno,
    node.col_offset = value.node.col_offset,
    node.end_lineno = value.node.end_lineno,
    node.end_col_offset = value.node.end_col_offset,
    node.name = value.node.name,
    node.code_snippet = value.node.code_snippet,
    node.context = value.node.properties.context,
    node.literal_value = value.node.properties.value,
    node.operator = value.node.properties.operator,
    node.placeholder = false,
    node.updated_at = value.event_time

MERGE (repository)-[:CONTAINS]->(source_file)
MERGE (source_file)-[:DECLARES]->(node)
"""


EDGE_CYPHER = """
WITH __value AS value

MERGE (source:CPGNode {
    node_id: value.edge.src_id
})
ON CREATE SET
    source.placeholder = true

MERGE (target:CPGNode {
    node_id: value.edge.dst_id
})
ON CREATE SET
    target.placeholder = true

MERGE (source)-[edge:CPG_EDGE {
    edge_id: value.edge.edge_id
}]->(target)
SET
    edge.edge_type = value.edge.edge_type,
    edge.file_id = value.file_id,
    edge.content_hash = value.content_hash,
    edge.role = value.edge.properties.role,
    edge.branch = value.edge.properties.branch,
    edge.symbol = value.edge.properties.symbol,
    edge.resolution = value.edge.properties.resolution,
    edge.callee = value.edge.properties.callee,
    edge.target_qualified_name = value.edge.properties.target_qualified_name,
    edge.updated_at = value.event_time
"""


def compact_cypher(query: str) -> str:
    """Đổi multiline Cypher thành một dòng dùng trong connector config."""
    return " ".join(query.split())


def load_password() -> str:
    environment = {
        **dotenv_values(ENV_PATH),
        **os.environ,
    }

    password = environment.get("NEO4J_PASSWORD")

    if not password:
        raise RuntimeError(
            "Không tìm thấy NEO4J_PASSWORD trong .env."
        )

    return str(password)


def build_connector_config(
    password: str,
) -> dict[str, str]:
    return {
        "connector.class":
            "org.neo4j.connectors.kafka.sink.Neo4jConnector",

        "tasks.max": "1",

        "topics": f"{NODE_TOPIC},{EDGE_TOPIC}",

        # Producer Python gửi key là UTF-8 string.
        "key.converter":
            "org.apache.kafka.connect.storage.StringConverter",

        # Producer Python gửi JSON không có schema envelope.
        "value.converter":
            "org.apache.kafka.connect.json.JsonConverter",

        "value.converter.schemas.enable": "false",

        # Kafka Connect và Neo4j cùng Docker network.
        "neo4j.uri": "neo4j://neo4j:7687",
        "neo4j.database": "neo4j",

        "neo4j.authentication.type": "BASIC",
        "neo4j.authentication.basic.username": "neo4j",
        "neo4j.authentication.basic.password": password,

        "neo4j.batch-size": "100",
        "neo4j.batch-timeout": "1s",

        "neo4j.cypher.bind-value-as": "__value",
        "neo4j.cypher.bind-value-as-event": "false",

        f"neo4j.cypher.topic.{NODE_TOPIC}":
            compact_cypher(NODE_CYPHER),

        f"neo4j.cypher.topic.{EDGE_TOPIC}":
            compact_cypher(EDGE_CYPHER),

        # Khi phát triển, dừng task ngay nếu message lỗi.
        "errors.tolerance": "none",
    }


def save_sanitized_config(
    config: dict[str, str],
) -> None:
    sanitized: dict[str, Any] = dict(config)

    sanitized[
        "neo4j.authentication.basic.password"
    ] = "${NEO4J_PASSWORD}"

    output_path = (
        PROJECT_ROOT
        / "workspace"
        / "artifacts"
        / "neo4j_sink_config_sanitized.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path.write_text(
        json.dumps(
            {
                "name": "neo4j-cpg-sink",
                "config": sanitized,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(f"Saved sanitized config: {output_path}")


def register_connector(
    config: dict[str, str],
) -> None:
    request = urllib.request.Request(
        CONNECT_URL,
        data=json.dumps(config).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="PUT",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30,
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

    except urllib.error.HTTPError as error:
        response_body = error.read().decode(
            "utf-8",
            errors="replace",
        )

        raise RuntimeError(
            f"Kafka Connect HTTP {error.code}: "
            f"{response_body}"
        ) from error

    except urllib.error.URLError as error:
        raise RuntimeError(
            f"Không kết nối được Kafka Connect: {error}"
        ) from error

    print(
        json.dumps(
            result,
            indent=2,
            ensure_ascii=False,
        )
    )


def main() -> int:
    try:
        password = load_password()
        config = build_connector_config(password)

        register_connector(config)
        save_sanitized_config(config)

    except Exception as error:
        print(
            f"Connector registration failed: {error}",
            file=sys.stderr,
        )
        return 1

    print("Neo4j sink connector registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())