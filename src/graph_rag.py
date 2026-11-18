"""Entity extraction and Neo4j storage/retrieval for hybrid graph RAG."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from neo4j import GraphDatabase


EXTRACTION_SYSTEM_PROMPT = """Extract important medical concepts and explicit relationships from the supplied text.
Return only a JSON object with this shape:
{"entities":[{"name":"...","type":"..."}],"relationships":[{"source":"entity name","target":"entity name","type":"SHORT_RELATIONSHIP"}]}
Use concise canonical entity names. Include only entities and relationships supported by the text. Use an empty array when none are found. Do not infer medical facts."""

QUERY_ENTITY_PROMPT = """Find the medical entities explicitly mentioned in the question.
Return only a JSON object shaped like {"entities":[{"name":"...","type":"..."}]}. Do not answer the question. Return an empty array if no entities are present."""


def stable_chunk_id(document: Any, chunk_number: int) -> str:
    source = str(document.metadata.get("source", "unknown"))
    page = str(document.metadata.get("page", ""))
    payload = f"{source}|{page}|{chunk_number}|{document.page_content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    content = getattr(value, "content", value)
    if not isinstance(content, str):
        raise ValueError("Expected a JSON response from the extraction model")
    content = content.strip()
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.IGNORECASE)
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise ValueError("The extraction model did not return a JSON object")
    parsed = json.loads(content[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("The extraction response must be a JSON object")
    return parsed


def _clean_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.strip().split())[:200]


def _key(name: str) -> str:
    return name.casefold()


def extract_graph_data(text: str, llm: Any) -> dict[str, list[dict[str, str]]]:
    """Extract validated entities/relationships using Groq's JSON mode."""
    response = llm.invoke([
        ("system", EXTRACTION_SYSTEM_PROMPT),
        ("human", text),
    ])
    payload = _parse_json_object(response)

    entities: dict[str, dict[str, str]] = {}
    raw_entities = payload.get("entities", [])
    if not isinstance(raw_entities, list):
        raw_entities = []
    for item in raw_entities:
        if not isinstance(item, dict):
            continue
        name = _clean_name(item.get("name"))
        if not name:
            continue
        entities[_key(name)] = {
            "name": name,
            "key": _key(name),
            "type": _clean_name(item.get("type")) or "Medical concept",
        }

    relationships = []
    seen_relationships = set()
    raw_relationships = payload.get("relationships", [])
    if not isinstance(raw_relationships, list):
        raw_relationships = []
    for item in raw_relationships:
        if not isinstance(item, dict):
            continue
        source = _clean_name(item.get("source"))
        target = _clean_name(item.get("target"))
        relation = _clean_name(item.get("type"))
        source_key, target_key = _key(source), _key(target)
        if not source or not target or not relation:
            continue
        if source_key not in entities or target_key not in entities:
            continue
        signature = (source_key, target_key, relation.casefold())
        if signature in seen_relationships:
            continue
        seen_relationships.add(signature)
        relationships.append({
            "source_key": source_key,
            "target_key": target_key,
            "type": relation[:100],
        })
    return {"entities": list(entities.values()), "relationships": relationships}


def extract_query_entities(question: str, llm: Any) -> list[str]:
    response = llm.invoke([
        ("system", QUERY_ENTITY_PROMPT),
        ("human", question),
    ])
    payload = _parse_json_object(response)
    names = []
    raw_entities = payload.get("entities", [])
    if not isinstance(raw_entities, list):
        return names
    for item in raw_entities:
        if isinstance(item, dict):
            name = _clean_name(item.get("name"))
            if name and _key(name) not in {_key(existing) for existing in names}:
                names.append(name)
    return names[:12]


class Neo4jGraphStore:
    """Parameterised Cypher operations for graph ingestion and retrieval."""

    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        if not all((uri, username, password)):
            raise ValueError("NEO4J_URI, NEO4J_USERNAME, and NEO4J_PASSWORD are required")
        self.driver = GraphDatabase.driver(uri, auth=(username, password))
        self.database = database or "neo4j"
        self.driver.verify_connectivity()
        with self.driver.session(database=self.database) as session:
            session.run(
                "CREATE INDEX entity_key_index IF NOT EXISTS "
                "FOR (entity:Entity) ON (entity.key)"
            ).consume()

    def close(self) -> None:
        self.driver.close()

    def store_chunk(
        self,
        chunk_id: str,
        text: str,
        source: str,
        page: str,
        graph_data: dict[str, list[dict[str, str]]],
    ) -> None:
        with self.driver.session(database=self.database) as session:
            session.run(
                "MERGE (chunk:Chunk {id: $chunk_id}) "
                "SET chunk.text = $text, chunk.source = $source, chunk.page = $page",
                chunk_id=chunk_id, text=text, source=source, page=page,
            ).consume()
            session.run(
                "MATCH (chunk:Chunk {id: $chunk_id}) "
                "UNWIND $entities AS item "
                "MERGE (entity:Entity {key: item.key}) "
                "SET entity.name = item.name, entity.type = item.type "
                "MERGE (chunk)-[:MENTIONS]->(entity)",
                chunk_id=chunk_id, entities=graph_data["entities"],
            ).consume()
            session.run(
                "UNWIND $relationships AS item "
                "MATCH (source:Entity {key: item.source_key}) "
                "MATCH (target:Entity {key: item.target_key}) "
                "MERGE (source)-[relation:RELATED_TO {type: item.type}]->(target)",
                relationships=graph_data["relationships"],
            ).consume()

    def search(self, entity_names: list[str], limit: int = 12) -> list[dict[str, str]]:
        keys = list(dict.fromkeys(_key(name) for name in entity_names if name))
        if not keys:
            return []
        with self.driver.session(database=self.database) as session:
            records = session.run(
                "UNWIND $keys AS entity_key "
                "MATCH (entity:Entity {key: entity_key}) "
                "OPTIONAL MATCH (chunk:Chunk)-[:MENTIONS]->(entity) "
                "OPTIONAL MATCH (entity)-[relation:RELATED_TO]-(related:Entity) "
                "OPTIONAL MATCH (related_chunk:Chunk)-[:MENTIONS]->(related) "
                "RETURN entity.name AS entity, related.name AS related_entity, "
                "relation.type AS relationship, chunk.text AS evidence, "
                "chunk.source AS source, related_chunk.text AS related_evidence, "
                "related_chunk.source AS related_source "
                "LIMIT $limit",
                keys=keys, limit=limit,
            )
            return [dict(record) for record in records]
