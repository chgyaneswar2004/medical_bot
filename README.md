# Knowledge Graph Medical Chatbot

A Flask medical-reference chatbot using hybrid retrieval augmented generation. It extracts entities and relationships from PDF source material into Neo4j, retrieves related facts with Cypher, combines those results with Pinecone vector search, and generates an answer with Groq.

## Quick start

1. Install Python 3.10 and create a virtual environment.
2. Install dependencies and prepare local configuration:

   ```bash
   pip install -r requirements.txt
   ```

   Copy `.env.example` to `.env`, then fill in valid Pinecone, Groq, and Neo4j credentials. Never commit `.env`.

3. Put source PDFs in `data/` and build the graph and vector indexes:

   ```bash
   python store_index.py
   ```

4. Start the web app and open `http://127.0.0.1:8080`:

   ```bash
   python app.py
   ```

Indexing calls the Groq model for entity and relationship extraction from every text chunk, so its runtime and API usage depend on the amount of PDF content.

## Documentation

See [APP_DOCUMENTATION.md](APP_DOCUMENTATION.md) for the architecture, graph schema, retrieval flow, configuration, local run instructions, evaluation notes, Docker deployment, AWS/GitHub Actions setup, and troubleshooting.

## Evaluation

`evaluate_rag.py` contains a small Pinecone-only baseline prompt evaluation. Its phrase-based hit@3 and grounding scores are screening metrics, not clinical correctness measurements. The main app uses both Neo4j and Pinecone.

## Safety and privacy

This is a medical information demo, not a diagnostic or emergency service. The app has no authentication or rate limiting. Questions and retrieved text are sent to Groq; avoid submitting personal health information.
