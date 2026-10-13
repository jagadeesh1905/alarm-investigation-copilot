
# Alarm Investigation and Procedure Guidance Copilot

A local demonstration application that combines an Alarm Management API, Model Context Protocol (MCP) tools, retrieval-augmented generation (RAG), and a local large language model to produce evidence-grounded alarm investigation reports.

**Important:** This project uses simulator data and synthetic procedure documents. It is a software demonstration, not a safety-rated industrial system. Never use its reports as authorization to operate, isolate, repair, or restart equipment.

## Features

- FastAPI alarm-management API with bearer-token authentication.
- Asset metadata, alarm details, active-alarm listing, summaries, trends, priority scoring, operator recommendations, and alarm correlation.
- MCP server exposing typed tools for alarm and asset investigation.
- MCP client integration for discovering and calling tools.
- Document retrieval using ChromaDB and Sentence Transformers embeddings.
- Procedure evidence with document IDs, revisions, source information, and citations.
- Local LLM report generation through Ollama.
- HTML/JavaScript frontend for submitting an alarm ID and reviewing investigation results.
- Trace IDs and API request metadata for troubleshooting.
- Automated API tests and an MCP smoke-test script.

## Architecture


Browser (HTML/JavaScript)
          |
          v
     FastAPI API
          |
          v
 Investigation workflow
          |
          +----------------------+
          |                      |
          v                      v
    MCP client              RAG pipeline
          |                      |
          v                      v
     MCP server              ChromaDB
          |                      |
          v                      v
  Alarm/asset API        Procedure documents
          |
          v
  Investigation context
          |
          v
   Ollama local LLM
          |
          v
 Evidence-grounded report


The MCP tools retrieve alarm and asset information from the simulator API. The RAG pipeline retrieves relevant procedure-document chunks. The investigation workflow combines these inputs to generate a report with evidence citations and safety limitations.

## Prerequisites

- Python 3.12 or a compatible Python version.
- Ollama installed and running locally.
- The configured Ollama model downloaded before generating reports.
- Internet access may be needed to install Python packages or download the embedding model on first use.

## Setup on Windows

Run the following commands from the project root in PowerShell:


python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env


If `.env` already exists, do not overwrite it. Review `.env.example` and update your existing configuration if necessary.

Check that Ollama is available and download the configured model if required:


ollama pull llama3.2:1b
ollama list


Review `.env` locally to ensure the API URL, token, model, document path, and vector-store path match your setup. Do not commit `.env` or share secret values.

## Start the application

### 1. Start the FastAPI server

Activate the virtual environment and run:


uvicorn app.main:app --reload --port 8000


API documentation:

- Swagger UI: http://127.0.0.1:8000/docs
- Health endpoint: http://127.0.0.1:8000/health

### 2. Open the frontend

Serve the project directory with a local static file server from the project root:


python -m http.server 5500 --directory frontend


Open:

http://127.0.0.1:5500/index.html 

Use the API token configured for your local demo environment. The default example token is `demo-token`; change it before exposing the API beyond your local machine.

### 3. Run an investigation

Enter an alarm ID such as `ALM-006` or `ALM-005` in the frontend and submit the request.

The report includes:

1. Alarm summary.
2. Asset context.
3. Related active alarms.
4. Retrieved procedure evidence.
5. Possible explanations to investigate.
6. Recommended next checks.
7. Safety and limitations.

The root cause must remain unconfirmed unless supported by authoritative evidence. Synthetic procedure documents are demonstration fixtures, not approved operating procedures.

## RAG documents

The procedure documents are stored under `rag/documents/`. Supported formats depend on the implemented document loader and currently include text, Markdown, PDF, and DOCX.

The embedding model and persistent vector-store location are configured through environment variables. Rebuild or refresh the vector index using the indexing command implemented in `rag_pipeline.py` when procedure documents change.

## Testing

Run the API regression tests:


python -m pytest tests/test_api.py -v

Run the complete test suite:


python -m pytest -v


Run the MCP smoke test while the FastAPI server is running:


python test_mcp_client.py



These tests do not, by themselves, establish production readiness or complete end-to-end test coverage.

## Configuration

The `.env.example` file documents the environment variables used for:

- Alarm API connection and authentication.
- RAG document and vector-store locations.
- Embedding backend and retrieval threshold.
- LLM provider, model, and timeout.
- MCP tool timeout.
- API retry configuration.
- Logging.

Keep real secrets in `.env` or an appropriate secrets manager. Never commit credentials.

## Limitations and safety

- Alarm and asset records are fictional simulator fixtures.
- Procedure documents marked synthetic are not approved maintenance guidance.
- Alarm correlation indicates co-occurrence, not causation.
- Priority scores are illustrative and are not validated safety decisions.
- Retrieved evidence may be incomplete or irrelevant; verify it before drawing conclusions.
- Local model output can be incorrect. Review recommendations against authoritative records and approved site procedures.
- Authentication and local development settings are not a substitute for a production security review.
- Docker deployment, broader integration coverage, and additional observability may require further implementation and validation.

## Project structure


app/                 FastAPI application and simulator data
frontend/            HTML/JavaScript user interface
rag/documents/       Procedure and troubleshooting fixtures
tests/               API regression tests
investigation.py     Investigation workflow and MCP client integration
llm_service.py       Local LLM report generation
mcp_server.py        MCP tool definitions and API integration
rag_pipeline.py      Document ingestion and retrieval
test_mcp_client.py   MCP smoke test
.env.example         Environment configuration template
requirements.txt     Python dependencies

