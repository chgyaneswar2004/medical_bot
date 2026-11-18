import logging
import os

from dotenv import load_dotenv
from flask import Flask, render_template, request
from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from langchain_pinecone import PineconeVectorStore

from src.graph_rag import Neo4jGraphStore, extract_query_entities
from src.helper import download_hugging_face_embeddings
from src.prompt import system_prompt


logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger(__name__)

load_dotenv()

required_environment = ("PINECONE_API_KEY", "GROQ_API_KEY", "NEO4J_URI",
                        "NEO4J_USERNAME", "NEO4J_PASSWORD")
missing_environment = [name for name in required_environment if not os.getenv(name)]
if missing_environment:
    raise RuntimeError("Missing required environment variables: " + ", ".join(missing_environment))

app = Flask(__name__)

# The sentence-transformer model is loaded locally; vector and graph databases
# remain remote services.
embeddings = download_hugging_face_embeddings()
index_name = os.getenv("PINECONE_INDEX_NAME", "medical-chatbot")
vector_store = PineconeVectorStore.from_existing_index(
    index_name=index_name,
    embedding=embeddings,
)

graph_store = Neo4jGraphStore(
    uri=os.environ["NEO4J_URI"],
    username=os.environ["NEO4J_USERNAME"],
    password=os.environ["NEO4J_PASSWORD"],
    database=os.getenv("NEO4J_DATABASE", "neo4j"),
)

model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
chat_model = ChatGroq(model=model_name)
entity_model = ChatGroq(
    model=model_name,
    model_kwargs={"response_format": {"type": "json_object"}},
)
answer_prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    ("human", "Question: {input}\n\nRetrieved context:\n{context}"),
])


def _format_context(vector_documents, graph_records) -> str:
    sections = []
    vector_lines = []
    for number, document in enumerate(vector_documents, 1):
        source = document.metadata.get("source", "unknown source")
        page = document.metadata.get("page")
        citation = f"{source}" + (f", page {page + 1}" if isinstance(page, int) else "")
        vector_lines.append(f"[Vector result {number}; {citation}]\n{document.page_content}")
    if vector_lines:
        sections.append("VECTOR SEARCH\n" + "\n\n".join(vector_lines))

    graph_lines = []
    seen = set()
    for record in graph_records:
        entity = record.get("entity")
        related = record.get("related_entity")
        relation = record.get("relationship")
        if entity and related and relation:
            line = f"Relationship: {entity} — {relation} — {related}"
            if line not in seen:
                graph_lines.append(line)
                seen.add(line)
        for text_key, source_key in (("evidence", "source"), ("related_evidence", "related_source")):
            evidence = record.get(text_key)
            if evidence:
                line = f"Graph evidence ({record.get(source_key) or 'unknown source'}): {evidence}"
                if line not in seen:
                    graph_lines.append(line)
                    seen.add(line)
    if graph_lines:
        sections.append("KNOWLEDGE GRAPH (Cypher results)\n" + "\n".join(graph_lines))

    return "\n\n".join(sections) or "No relevant context was retrieved."


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/get", methods=["POST"])
def chat():
    question = request.form.get("msg", "").strip()
    if not question:
        return "Please enter a question.", 400

    vector_documents = vector_store.similarity_search(question, k=3)
    graph_records = []
    try:
        entities = extract_query_entities(question, entity_model)
        graph_records = graph_store.search(entities)
    except Exception:
        # Keep the vector path available if graph entity extraction is unavailable.
        logger.exception("Graph retrieval failed; answering from vector results only")

    context = _format_context(vector_documents, graph_records)
    answer = (answer_prompt | chat_model).invoke({"input": question, "context": context})
    return str(answer.content)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "8080")), debug=False)
