# Knowledge Graph Medical Chatbot — Project Documentation

## 1. Purpose

This project is a Flask medical-reference chatbot built with a hybrid retrieval augmented generation architecture. It reads PDF material, extracts entities and relationships with Groq, stores the resulting knowledge graph in Neo4j, stores text embeddings in Pinecone, and combines graph and vector evidence when answering a question.

The app is an educational/reference demo. It is not a diagnostic or emergency service and should not replace advice from a qualified clinician.

## 2. Architecture at a glance

```text
PDF files in data/
       |
       v
PDF loading -> text chunks -> Hugging Face embeddings -> Pinecone vector index
                    |
                    +-> Groq entity/relation extraction -> Neo4j knowledge graph

User question -> Groq entity extraction -> parameterized Cypher query -> Neo4j graph evidence
       |
       +----------> embedding similarity search ---------------------> Pinecone passages
                                                                       |
                            graph evidence + vector passages ----------+
                                                |
                                                v
                                     Groq answer generation -> Flask chat UI
```

Neo4j and Pinecone have separate jobs. Neo4j represents concepts and their connections; Pinecone finds text passages by semantic similarity. The app concatenates both retrieval results into one context for Groq. It does not currently merge or rerank the two result lists with a numeric hybrid score.

## 3. Request and answer flow

1. `GET /` renders the chat UI.
2. The browser posts a question in form field `msg` to `POST /get`.
3. Groq extracts named medical concepts from the question as JSON.
4. The app passes those normalized names as parameters to a fixed Cypher query. The model does not generate executable Cypher.
5. The app runs Pinecone similarity search for the top three passages.
6. Graph relationships and their source chunk evidence are combined with the vector passages.
7. Groq generates a concise response based on the supplied context and returns plain text to the browser.

If graph entity extraction or retrieval fails during a request, the app logs the failure and attempts to answer using vector passages alone. If the vector database or final Groq call fails, the request returns an application error.

## 4. Knowledge graph model

The graph currently uses two node types and two relationship types:

```text
(Chunk {id, text, source, page})-[:MENTIONS]->(Entity {key, name, type})
(Entity)-[:RELATED_TO {type}]->(Entity)
```

- **Chunk** stores a source text segment and its source path/page.
- **Entity** stores a normalized key, display name, and category/type.
- **MENTIONS** links evidence chunks to the concepts they mention.
- **RELATED_TO** stores a relationship label as a property, such as a medical association extracted from the source.

Graph lookups match question entities, then use Cypher to return adjacent entities, relationships, and linked source chunks. Cypher values are parameterized. Entity labels and relationship labels are fixed in code; extracted strings are stored as property values.

## 5. Project files

| Path | Responsibility |
| --- | --- |
| `app.py` | Flask routes, service initialization, Neo4j and Pinecone retrieval, and answer generation. |
| `src/graph_rag.py` | Groq JSON extraction, stable chunk IDs, Neo4j connection, graph writes, and parameterized Cypher retrieval. |
| `src/helper.py` | PDF loading, source/page metadata preservation, text splitting, and Hugging Face embeddings. |
| `src/prompt.py` | Answer instructions and prompt variants used by the baseline evaluation script. |
| `store_index.py` | Ingests PDF chunks into the Neo4j graph and Pinecone vector index. |
| `data/` | PDF sources for indexing. The current local source file is `Medical_book.pdf`. |
| `templates/chat.html` | Chat page and browser-side request code. |
| `static/style.css` | Chat UI styling. |
| `evaluate_rag.py` | Small Pinecone-only baseline prompt evaluation script. |
| `requirements.txt` | Pinned Python packages. |
| `.env.example` | Safe template of required local configuration variable names. |
| `Dockerfile` | Builds the runtime image and starts Gunicorn. |
| `.github/workflows/cicd.yaml` | Builds/pushes the image to ECR and deploys it from the EC2 self-hosted runner. |
| `README.md` | Short project overview and quick start. |

## 6. Services and configuration

### Required services

- **Groq**: entity extraction, question entity extraction, and final answer generation.
- **Pinecone**: semantic search over source chunks.
- **Neo4j**: persistent entity and relationship graph.
- **Hugging Face sentence-transformers**: local text embeddings using `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions).

### Environment variables

Copy `.env.example` to `.env` for local development and fill in your own values. Do not paste secrets into source files or documentation, commit `.env`, or bake credentials into the Docker image.

| Variable | Required | Description |
| --- | --- | --- |
| `PINECONE_API_KEY` | Yes | Pinecone API credential. |
| `PINECONE_INDEX_NAME` | No | Vector index name; defaults to `medical-chatbot`. |
| `PINECONE_CLOUD` | No | Cloud for a newly created Pinecone index; defaults to `aws`. |
| `PINECONE_REGION` | No | Region for a newly created index; defaults to `us-east-1`. |
| `GROQ_API_KEY` | Yes | Groq API credential. |
| `GROQ_MODEL` | No | Chat and extraction model; defaults to `openai/gpt-oss-120b`. |
| `NEO4J_URI` | Yes | Neo4j connection URI, such as a TLS Aura URI. |
| `NEO4J_USERNAME` | Yes | Neo4j database user. |
| `NEO4J_PASSWORD` | Yes | Neo4j database password. |
| `NEO4J_DATABASE` | No | Neo4j database name; defaults to `neo4j`. |
| `PORT` | No | Local Flask listening port; defaults to `8080`. |

The Pinecone serverless region (`us-east-1` by default) is independent of the AWS region used for the ECR/EC2 deployment (`ap-southeast-2` in the current setup).

### Local Neo4j

Use a reachable Neo4j database, such as Neo4j Aura or a local Neo4j server. For Aura, use its supplied connection URI, user, and password. The machine running the app/indexer must be allowed to reach the database over the network. The app creates an index on `Entity.key` at startup when the database user has permission.

## 7. Build the graph and vector indexes

Put source PDFs under `data/`, configure all required local environment variables, install dependencies, then run:

```bash
python store_index.py
```

The indexing process:

1. Loads PDF pages from `data/` and retains their source and page metadata.
2. Splits text into 1,000-character chunks with 100-character overlap.
3. Creates 384-dimensional embeddings using `all-MiniLM-L6-v2`.
4. Calls Groq in JSON mode to extract entities and relationships from each chunk.
5. Writes chunk, entity, mention, and relationship records to Neo4j.
6. Writes chunk vectors to Pinecone with stable IDs.

Groq is called for each chunk, so indexing a large book can take time and consume API usage. The graph writes use `MERGE` and vector upserts use stable IDs, making reruns for unchanged content idempotent. If source text changes, the changed chunks receive new IDs; this script does not delete obsolete chunks from either database. Plan a deliberate cleanup/rebuild if replacing or removing source files.

The indexer does not run automatically when the web app starts. Populate both databases before launching the app.

## 8. Run locally

Use Python 3.10 or newer in a virtual environment. From the project root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add valid credentials before continuing.
python store_index.py
python app.py
```

Open `http://127.0.0.1:8080`. In macOS/Linux, activate with `source .venv/bin/activate` and copy the environment template with `cp .env.example .env`.

Run `python store_index.py` again only when you need to ingest new or changed PDF material. It performs external API calls.

## 9. HTTP interface

### `GET /`

Renders `templates/chat.html`.

### `POST /get`

Expects form data with a non-empty `msg` field. Returns the generated answer as plain text. Empty messages return HTTP 400. There is no authentication, conversation memory, or chat history persistence.

## 10. Evaluation

`evaluate_rag.py` evaluates the legacy Pinecone-only retrieval path and compares the prompt variants in `src/prompt.py`. It does not exercise Neo4j or the production hybrid retrieval path. Its phrase-based hit@3 and grounding proxy are automatic screening measures, not human relevance ratings or clinical correctness judgments. Treat any saved scores as historical baseline results until the evaluation is updated for graph-plus-vector retrieval and reviewed by people.

## 11. Docker runtime

The Docker image uses Python 3.10 slim, installs pinned dependencies, and starts one Gunicorn worker on container port `8080` with a 120-second timeout. The Docker build excludes `.env` and PDF data; the runtime uses environment variables to access Groq, Pinecone, and Neo4j.

Example local run after building:

```bash
docker build -t medical-chatbot .
docker run --rm -p 8080:8080 \
  --env-file .env \
  medical-chatbot
```

Do not use `--env-file .env` in a shared shell transcript or on a machine where the file contains credentials you do not intend to expose.

## 12. AWS and GitHub Actions deployment

The workflow runs on pushes to `main`:

1. A GitHub-hosted runner builds the Docker image and pushes it to the ECR repository.
2. A self-hosted GitHub Actions runner on EC2 logs in to ECR using its instance role, pulls the image, replaces the `medical-chatbot` container, and publishes port `8080` as EC2 port `80`.
3. The container starts with `--restart unless-stopped`, so Docker restarts it after an EC2 reboot.

### GitHub repository secrets

Set these under **Settings → Secrets and variables → Actions → Repository secrets**:

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION` (current deployment region: `ap-southeast-2`)
- `ECR_REPO` (repository name only, e.g. `medicalbot`)
- `PINECONE_API_KEY`
- `GROQ_API_KEY`
- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`

The workflow sets `NEO4J_DATABASE`, `GROQ_MODEL`, and the Pinecone index name as non-secret environment settings. Do not add `OPENAI_API_KEY`; this project calls Groq.

The EC2 instance role needs ECR read access. The IAM credentials used by the build job need access to push to the target ECR repository. The self-hosted runner service account needs permission to run Docker commands. The EC2 security group needs inbound TCP port `80` from the desired client networks. SSH port `22` is for administration and should be limited to trusted source IP addresses. The web app currently serves HTTP; it is not configured for HTTPS or a domain name.

The self-hosted runner should be installed as a systemd service so it reconnects after EC2 restarts. GitHub **Settings → Actions → Runners** should show it online/idle before a deployment can run.

## 13. Startup, memory, and troubleshooting

The embedding model loads locally during app startup, and connections to both databases are initialized when Gunicorn imports the Flask app. This can use substantial RAM, particularly on a small EC2 instance. Prior logs from the project showed Gunicorn workers being killed and timing out while the instance had almost no free memory. Those errors indicate memory pressure; LangChain deprecation warnings were separate.

Useful EC2 commands:

```bash
free -h
docker ps -a
docker logs --tail 100 medical-chatbot
sudo systemctl list-units 'actions.runner*' --all
```

Troubleshooting order:

1. Confirm the latest GitHub Actions run succeeded and the self-hosted runner is online.
2. In the EC2 terminal, confirm `medical-chatbot` is running and read its logs.
3. Confirm the instance security group permits TCP port `80` from your client.
4. Open the instance's current public IP using `http://`, not `https://`.
5. Check `free -h`; resize the EC2 instance if memory is exhausted or Gunicorn workers are killed.
6. Confirm the Neo4j URI and network allowlist permit connections from the EC2 instance, and check the Neo4j database is available.
7. Confirm the required GitHub secrets are configured. Never paste their values into logs or chat.

## 14. Known limitations and follow-up work

- The app is unauthenticated and has no rate limiting; an internet-exposed endpoint can consume Groq quota.
- Questions and retrieved source material are sent to Groq. Do not submit personal health information unless the deployment has been assessed and approved for that use.
- Groq extraction can omit or mislabel relationships. Graph results should be treated as retrieval hints and grounded against source chunks.
- The schema stores extracted relations as generic `RELATED_TO` edges with a `type` property; it does not enforce domain-specific medical ontologies.
- The evaluation script currently measures only the Pinecone baseline and should be extended before comparing hybrid retrieval changes.
- The UI relies on external CDN assets.
- The deployment uses the mutable `latest` ECR tag; commit-specific image tags would improve traceability and rollback.

## 15. Change guide

- **Change model:** set `GROQ_MODEL` in local configuration and the workflow's runtime environment.
- **Change extraction instructions:** edit `EXTRACTION_SYSTEM_PROMPT` or `QUERY_ENTITY_PROMPT` in `src/graph_rag.py`.
- **Change graph schema or Cypher:** edit `Neo4jGraphStore` in `src/graph_rag.py`.
- **Change vector retrieval count:** edit `similarity_search(..., k=3)` in `app.py`.
- **Change chunk size/overlap or embeddings:** edit `src/helper.py`; reindex consistently if the embedding model or vector dimension changes.
- **Add PDF content:** put PDFs in `data/` and rerun `python store_index.py`.
- **Change answer style:** edit `src/prompt.py`.
- **Change the web interface:** edit `templates/chat.html` and `static/style.css`.
- **Change deployment:** edit `Dockerfile` or `.github/workflows/cicd.yaml`.
