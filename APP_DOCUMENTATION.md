# Local Knowledge Graph Medical Chatbot — Documentation

## 1. Purpose and scope

This project runs a Flask medical-reference chatbot on the local computer. It extracts entities and relationships from PDFs into a Neo4j knowledge graph, searches source passages in Pinecone, and uses Groq to generate answers from both retrieval paths.

The web server binds to `127.0.0.1`, so it can be opened only from the same computer. Groq and Pinecone are cloud APIs; Neo4j is configured for a local server by default. This app provides general reference information, not diagnosis or emergency care.

## 2. Architecture

```text
PDFs in data/
     |
     v
PDF pages -> text chunks -> Hugging Face embeddings -> Pinecone vector index
                    |
                    +-> Groq entity/relation extraction -> local Neo4j graph

Question -> Groq entity extraction -> Cypher query -> Neo4j graph evidence
    |
    +-----> semantic similarity search ------------> Pinecone passages
                                                  |
                         graph + vector context ---+
                                  |
                                  v
                        Groq answer -> local Flask UI
```

Neo4j stores concepts and their relationships. Pinecone finds passages by semantic similarity. The app passes both results as context to Groq; it does not calculate a combined ranking score.

## 3. Request flow

1. `GET /` renders the chat interface.
2. The browser posts a question as form field `msg` to `POST /get`.
3. Groq extracts named entities from the question in JSON mode.
4. The app passes those entity names to a fixed, parameterized Cypher query. The model does not write or execute Cypher.
5. Pinecone returns the top three semantically similar text chunks.
6. The app combines graph relationships and their linked source chunks with the Pinecone passages.
7. Groq answers from the combined context. If graph extraction or graph lookup fails, the app logs the issue and continues with vector context alone.

## 4. Graph schema

```text
(Chunk {id, text, source, page})-[:MENTIONS]->(Entity {key, name, type})
(Entity)-[:RELATED_TO {type}]->(Entity)
```

- `Chunk` holds source text and its PDF source/page.
- `Entity` stores a normalized lookup key, display name, and category.
- `MENTIONS` links a chunk to each entity extracted from it.
- `RELATED_TO` connects entities; its `type` property records the extracted relationship.

The Cypher query matches normalized entity names, then returns adjacent concepts, relationship labels, and source chunks. Query values are passed as parameters.

## 5. Project files

| Path | Responsibility |
| --- | --- |
| `app.py` | Local Flask server, service initialization, graph/vector retrieval, answer generation, and routes. |
| `src/graph_rag.py` | Groq JSON extraction, stable chunk IDs, Neo4j writes, and Cypher search. |
| `src/helper.py` | PDF loading, source/page metadata, chunking, and local embeddings. |
| `src/prompt.py` | Answer instructions and evaluation prompt variants. |
| `store_index.py` | Indexes PDF chunks in Neo4j and Pinecone. |
| `data/` | PDF sources; the current source file is `Medical_book.pdf`. |
| `templates/chat.html` | Chat page and browser request handling. |
| `static/style.css` | Chat styling. |
| `evaluate_rag.py` | Pinecone-only baseline evaluation script. |
| `requirements.txt` | Python dependencies for local execution and indexing. |
| `.env.example` | Template of local configuration variable names. |
| `README.md` | Quick-start instructions. |

## 6. Services and environment variables

The project uses:

- **Groq** for entity extraction and answer generation.
- **Pinecone** for vector storage and semantic search.
- **Neo4j** for the graph database, configured at `bolt://localhost:7687` by default.
- **Hugging Face `sentence-transformers/all-MiniLM-L6-v2`** for 384-dimensional embeddings computed on the local machine.
- **Flask** for the local web UI.

Copy `.env.example` to `.env` and fill in your values. Keep `.env` private and out of Git.

| Variable | Required | Description |
| --- | --- | --- |
| `PINECONE_API_KEY` | Yes | Pinecone API key. |
| `PINECONE_INDEX_NAME` | No | Index name, defaults to `medical-chatbot`. |
| `PINECONE_CLOUD` | No | Cloud used when creating a new index, defaults to `aws`. |
| `PINECONE_REGION` | No | Region used when creating a new index, defaults to `us-east-1`. |
| `GROQ_API_KEY` | Yes | Groq API key. |
| `GROQ_MODEL` | No | Model name, defaults to `openai/gpt-oss-120b`. |
| `NEO4J_URI` | Yes | Local Neo4j connection URI; default `bolt://localhost:7687`. |
| `NEO4J_USERNAME` | Yes | Neo4j username. |
| `NEO4J_PASSWORD` | Yes | Neo4j password. |
| `NEO4J_DATABASE` | No | Database name, defaults to `neo4j`. |
| `PORT` | No | Local Flask port, defaults to `8080`. |

Neo4j must be running locally before indexing or starting the app. The user running the app must be allowed to create the `Entity.key` index. Pinecone and Groq still require internet access and valid credentials.

## 7. Build the knowledge base

Place PDFs in `data/`, configure the values in `.env`, and run:

```powershell
python store_index.py
```

The indexer loads PDF pages, retains source and page metadata, splits text into 1,000-character chunks with 100-character overlap, and computes embeddings. For every chunk, it asks Groq to return entities and relationships as JSON, writes the graph data to Neo4j, and upserts the chunk vector to Pinecone using a stable ID.

Indexing calls Groq once per chunk, so a large book may take a while and use API quota. If interrupted, rerunning skips chunks already committed to Neo4j and continues with the remaining chunks; after graph extraction completes, it upserts the full vector set using stable IDs. Changed chunks get new IDs; the script does not remove old chunks from either database. If replacing/removing PDFs, remove stale graph/vector records deliberately before rebuilding.

## 8. Start the local application

On Windows PowerShell, from the project root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env, start Neo4j, and add PDFs under data/.
python store_index.py
python app.py
```

On macOS/Linux, activate with `source .venv/bin/activate` and copy the template with `cp .env.example .env`.

Open `http://127.0.0.1:8080` on the same computer. The Flask server is explicitly bound to the loopback interface.

## 9. HTTP routes

### `GET /`

Returns the rendered chat page.

### `POST /get`

Accepts form data containing a non-empty `msg` field and returns a plain text answer. Empty input receives HTTP 400. Chat history is not saved and there are no user accounts.

## 10. Evaluation

`evaluate_rag.py` compares three answer prompts with Pinecone-only retrieval. It does not exercise Neo4j or the production hybrid retrieval flow. Phrase-based hit@3 and grounding scores are preliminary automatic checks, not human relevance labels or clinical correctness scores.

## 11. Troubleshooting

Useful local checks:

```powershell
python --version
python -c "import neo4j; print('Neo4j driver installed')"
python -c "import os; from dotenv import load_dotenv; load_dotenv(); print('Neo4j URI configured:', bool(os.getenv('NEO4J_URI')))"
```

- **App exits during startup:** check that all required environment variables are present, Neo4j is running, and the Pinecone index exists.
- **Neo4j connection refused:** confirm the local database is started and `NEO4J_URI` points to its Bolt endpoint.
- **Graph is empty:** add PDFs under `data/` and run `python store_index.py`; inspect its progress/errors.
- **Slow startup or out-of-memory:** the embedding model loads into local memory at startup. Close other memory-heavy apps or use a computer with more RAM.
- **Answers omit graph facts:** confirm graph indexing completed and that the question mentions concepts recognized during extraction.
- **`/get` returns an error:** check internet access, Groq/Pinecone credentials, Neo4j availability, and the terminal output.

## 12. Limitations

- The app has no authentication or rate limiting; however, the local-only server is reachable only from the host computer.
- Questions and retrieved text are sent to Groq. Do not submit personal health information.
- Entity/relationship extraction may omit or mislabel facts. Review the source passages before relying on graph results.
- The graph uses generic `RELATED_TO` relationships rather than a validated medical ontology.
- The evaluation script covers the Pinecone baseline only.
- The interface loads some assets from external CDNs, so the browser needs internet access for those assets.

## 13. Common changes

- **Change answer behavior:** edit `src/prompt.py`.
- **Change entity extraction behavior or Cypher:** edit `src/graph_rag.py`.
- **Change number of vector results:** edit `similarity_search(..., k=3)` in `app.py`.
- **Change chunking or embedding model:** edit `src/helper.py`; rebuild the Pinecone index consistently if the embedding dimensions change.
- **Add or replace medical source PDFs:** update `data/` and run the graph/vector indexer.
- **Change the UI:** edit `templates/chat.html` and `static/style.css`.
