# Local Knowledge Graph Medical Chatbot

A locally run Flask chatbot that reads medical reference PDFs, extracts entities and relationships with Groq, stores the graph in Neo4j, searches document embeddings in Pinecone, and combines both sources to answer questions.

The Flask web server listens on `127.0.0.1` only. Groq and Pinecone are external services; Neo4j can run locally. This is a medical information demo, not a diagnosis or emergency service.

## Run it locally

Use Python 3.10 or newer. Install and configure the project from PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` with your Pinecone and Groq API keys and your Neo4j local connection details. Never commit `.env`. Start a local Neo4j database, then put PDFs into `data/` and build the graph and vector indexes:

```powershell
python store_index.py
```

Start the app:

```powershell
python app.py
```

Open `http://127.0.0.1:8080` on the same computer. The local web server is not exposed to other devices on your network.

Indexing calls Groq once for each text chunk and can take time on large PDF collections. Run it again when you add or change source PDFs.

## Documentation

See [APP_DOCUMENTATION.md](APP_DOCUMENTATION.md) for the architecture, graph schema, retrieval details, environment variables, indexing steps, local troubleshooting, and evaluation limitations.

## Evaluation

`evaluate_rag.py` is a Pinecone-only baseline prompt evaluation. Its phrase-based scores are screening measures, not clinical correctness judgments, and it does not evaluate the production graph retrieval path.

## Privacy

Questions and retrieved source text are sent to Groq. Avoid submitting personal health information. The chat app has no accounts or rate limiting.
