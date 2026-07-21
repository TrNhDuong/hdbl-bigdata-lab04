CREATE CONSTRAINT repository_repo_id IF NOT EXISTS
FOR (repository:Repository)
REQUIRE repository.repo_id IS UNIQUE;

CREATE CONSTRAINT source_file_file_id IF NOT EXISTS
FOR (source_file:SourceFile)
REQUIRE source_file.file_id IS UNIQUE;

CREATE CONSTRAINT cpg_node_node_id IF NOT EXISTS
FOR (node:CPGNode)
REQUIRE node.node_id IS UNIQUE;

CREATE INDEX cpg_node_file_id IF NOT EXISTS
FOR (node:CPGNode)
ON (node.file_id);