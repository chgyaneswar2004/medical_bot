"""Build the Pinecone vector index and Neo4j knowledge graph from PDFs."""

import os

from dotenv import load_dotenv
from langchain_groq import ChatGroq
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

from src.graph_rag import Neo4jGraphStore, extract_graph_data, stable_chunk_id
from src.helper import (
    download_hugging_face_embeddings,
    filter_to_minimal_docs,
    load_pdf_file,
    text_split,
)


def main() -> None:
    load_dotenv()
    required = ("PINECONE_API_KEY", "GROQ_API_KEY", "NEO4J_URI",
                "NEO4J_USERNAME", "NEO4J_PASSWORD")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise SystemExit("Missing configuration: " + ", ".join(missing))

    documents = filter_to_minimal_docs(load_pdf_file(data="data/"))
    if not documents:
        raise SystemExit("No PDF pages found. Add PDF files to data/ and rerun.")

    chunks = text_split(documents)
    for number, chunk in enumerate(chunks):
        chunk.metadata["chunk_number"] = number
        chunk.metadata["chunk_id"] = stable_chunk_id(chunk, number)

    model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    extraction_model = ChatGroq(
        model=model_name,
        model_kwargs={"response_format": {"type": "json_object"}},
    )
    embeddings = download_hugging_face_embeddings()

    pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "medical-chatbot")
    pinecone = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    if not pinecone.has_index(pinecone_index_name):
        pinecone.create_index(
            name=pinecone_index_name,
            dimension=384,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=os.getenv("PINECONE_CLOUD", "aws"),
                region=os.getenv("PINECONE_REGION", "us-east-1"),
            ),
        )

    graph_store = Neo4jGraphStore(
        uri=os.environ["NEO4J_URI"],
        username=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
        database=os.getenv("NEO4J_DATABASE", "neo4j"),
    )
    try:
        for number, chunk in enumerate(chunks, 1):
            graph_data = extract_graph_data(chunk.page_content, extraction_model)
            graph_store.store_chunk(
                chunk_id=chunk.metadata["chunk_id"],
                text=chunk.page_content,
                source=str(chunk.metadata.get("source", "unknown")),
                page=str(chunk.metadata.get("page", "")),
                graph_data=graph_data,
            )
            if number % 25 == 0 or number == len(chunks):
                print(f"Stored graph data for {number}/{len(chunks)} chunks")
    finally:
        graph_store.close()

    PineconeVectorStore.from_documents(
        documents=chunks,
        index_name=pinecone_index_name,
        embedding=embeddings,
        ids=[chunk.metadata["chunk_id"] for chunk in chunks],
    )
    print(f"Indexed {len(chunks)} chunks in Pinecone and Neo4j.")


if __name__ == "__main__":
    main()
