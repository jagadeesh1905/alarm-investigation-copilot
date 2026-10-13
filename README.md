\# Alarm Investigation and Procedure Guidance Copilot



A local demonstration application that combines \*\*FastAPI, Model Context Protocol (MCP), retrieval-augmented generation (RAG), ChromaDB, Sentence Transformers, and Ollama\*\* to generate evidence-grounded alarm investigation reports.



The application retrieves alarm and asset information through MCP tools, searches procedure documents for relevant evidence, and combines the results into an investigation report with citations, recommended checks, and explicit safety limitations.



> \*\*Safety notice:\*\* This project uses simulator data and synthetic procedure documents. It is a software demonstration, not a safety-rated industrial system. Never use its reports as authorization to operate, isolate, repair, or restart equipment. Always follow approved site procedures and consult qualified personnel.



\## Features



\- \*\*Alarm Management API:\*\* FastAPI endpoints with bearer-token authentication.

\- \*\*Alarm and Asset Investigation:\*\* Retrieve alarm details, search assets, inspect metadata, list alarms, and review related alarms.

\- \*\*Alarm Analytics:\*\* Summaries, trends, correlation, and illustrative priority scoring.

\- \*\*MCP Integration:\*\* Discover and invoke typed tools through an MCP client and server.

\- \*\*Retrieval-Augmented Generation:\*\* Search procedure documents using ChromaDB and Sentence Transformers embeddings.

\- \*\*Evidence and Citations:\*\* Include source documents, document identifiers, revisions, and retrieved evidence in investigation reports.

\- \*\*Local LLM:\*\* Generate reports using an Ollama-hosted model.

\- \*\*Web Interface:\*\* Submit alarm IDs and review investigation results through an HTML/JavaScript frontend.

\- \*\*Troubleshooting Support:\*\* Trace IDs, request metadata, logging, automated API tests, and an MCP smoke test.



\## Architecture





Browser (HTML/JavaScript)

&#x20;         |

&#x20;         v

&#x20;   FastAPI API

&#x20;         |

&#x20;         v

&#x20;Investigation Workflow

&#x20;         |

&#x20;    +----+----------------+

&#x20;    |                     |

&#x20;    v                     v

&#x20; MCP Client           RAG Pipeline

&#x20;    |                     |

&#x20;    v                     v

&#x20; MCP Server            ChromaDB

&#x20;    |                     |

&#x20;    v                     v

&#x20;Alarm/Asset API       Procedure Documents

&#x20;    |                     |

&#x20;    +----------+----------+

&#x20;               |

&#x20;               v

&#x20;      Investigation Context

&#x20;               |

&#x20;               v

&#x20;        Ollama Local LLM

&#x20;               |

&#x20;               v

&#x20;    Evidence-Grounded Report



\### Investigation workflow



1\. The user submits an alarm ID through the web interface.

2\. The investigation workflow discovers and invokes MCP tools to retrieve alarm and asset information from the simulator API.

3\. The RAG pipeline retrieves relevant procedure-document chunks from the local vector index.

4\. The workflow combines the retrieved information into an investigation context.

5\. The local LLM generates an investigation report, including supporting evidence, possible explanations, and recommended checks.

6\. The report preserves uncertainty where the available evidence does not establish a root cause.



\*\*Important design principle:\*\* Alarm co-occurrence does not establish causation. A possible explanation must not be presented as a confirmed root cause without supporting evidence.



\## Technology Stack



| Component | Technology |

|---|---|

| Backend API | Python, FastAPI |

| Tool integration | Model Context Protocol (MCP) |

| Retrieval | ChromaDB |

| Embeddings | Sentence Transformers |

| Language model | Ollama |

| Frontend | HTML, JavaScript |

| Testing | pytest |



\## Prerequisites



\- Python version compatible with the dependencies in `requirements.txt`.

\- Ollama installed and running locally.

\- The configured Ollama model downloaded before generating reports.

\- Internet access may be required to install Python packages or download the embedding model on first use.



\## Setup on Windows



Run the following commands in PowerShell from the project root.



\### 1. Create and activate a virtual environment





python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

python -m pip install --upgrade pip

python -m pip install -r requirements.txt





If PowerShell blocks virtual-environment activation, use an appropriate execution policy for your environment or activate the environment from a supported terminal.



\### 2. Configure environment variables



Create the local environment file if it does not already exist:





Copy-Item .env.example .env





If `.env` already exists, \*\*do not overwrite it\*\*. Review `.env.example` and update the existing configuration as needed.



Check the local configuration for the API URL, authentication token, LLM model, procedure-document path, vector-store path, and relevant timeouts.



Never commit `.env`, API tokens, or other secrets to version control.



\### 3. Prepare Ollama



Ensure Ollama is installed and running. Download the configured model if it is not already available:





ollama pull llama3.2:1b

ollama list





Use the model configured in your `.env` file if it differs from the example above.



\## Running the Application



\### 1. Start the FastAPI server



Activate the virtual environment and run:





uvicorn app.main:app --reload --port 8000





Available endpoints:



\- API documentation: http://127.0.0.1:8000/docs

\- Health check: http://127.0.0.1:8000/health



\### 2. Start the frontend



Open another PowerShell terminal, navigate to the project root, and activate the virtual environment if needed.



Run:





python -m http.server 5500 --directory frontend





Open the application in your browser:



http://127.0.0.1:5500/index.html



Use the API token configured for your local demo environment. The example token `demo-token` is intended only for local demonstration and must not be treated as production authentication.



\### 3. Run an investigation



1\. Open the frontend.

2\. Enter a supported alarm ID, such as `ALM-005` or `ALM-006`.

3\. Submit the request.

4\. Review the generated investigation report.



Depending on the available data and retrieved evidence, the report can include:



\- Alarm summary and asset context.

\- Related active alarms.

\- Retrieved procedure evidence and citations.

\- Possible explanations requiring investigation.

\- Recommended next checks.

\- Safety warnings and limitations.



The root cause remains unconfirmed unless authoritative evidence supports a conclusion.



\## MCP Tools



The MCP server exposes tools for retrieving alarm and asset information, performing selected alarm analytics, and searching procedure documents.



| Tool | Purpose |

|---|---|

| `search\_assets` | Search for assets using a query. |

| `get\_asset\_metadata` | Retrieve asset metadata. |

| `get\_alarm` | Retrieve details for a specific alarm. |

| `list\_alarms` | List alarms, including supported filters and pagination. |

| `get\_alarm\_summary` | Retrieve an alarm summary. |

| `get\_alarm\_trends` | Retrieve alarm trend information. |

| `correlate\_alarms` | Examine relationships and co-occurrence between alarms. |

| `score\_alarm\_priority` | Calculate an illustrative alarm priority score. |

| `get\_operator\_recommendations` | Retrieve operator-action recommendations. |

| `search\_procedures` | Retrieve relevant procedure-document evidence through RAG. |



The procedure-search tool uses the RAG pipeline, while the alarm and asset tools integrate with the simulator API. This allows the investigation workflow to combine operational data with document evidence.



\## RAG Pipeline



Procedure documents are stored under:





rag/documents/





The document loader supports text, Markdown, PDF, and DOCX files, subject to the implemented loader behavior.



The RAG workflow:



1\. Loads supported procedure documents.

2\. Extracts text and available document metadata.

3\. Splits content into overlapping chunks.

4\. Generates embeddings using Sentence Transformers.

5\. Stores chunks and metadata in ChromaDB.

6\. Retrieves relevant chunks for a procedure query.

7\. Returns source metadata and evidence for use in the investigation report.



The vector index is stored under:





data/chroma\_db/





The embedding configuration, document paths, and retrieval settings are controlled by the project configuration. When procedure documents change, refresh the index using the indexing command implemented in `rag\_pipeline.py`.



Only use approved and current documents when adapting this demonstration to a real operational environment.



\## Testing



Run the API regression tests:





python -m pytest tests/test\_api.py -v





Run the complete test suite:



python -m pytest -v





Run the MCP smoke test while the FastAPI server is running:





python test\_mcp\_client.py





The test suite validates implemented behavior within its test coverage. Passing tests alone do not establish production readiness or comprehensive end-to-end correctness.



\## Configuration



The `.env.example` file documents configuration for the application. Depending on the component, settings include:



\- Alarm API connection and authentication.

\- RAG document and vector-store paths.

\- Embedding backend and retrieval threshold.

\- LLM provider, model, and timeout.

\- MCP tool timeout.

\- API retries and backoff.

\- Logging and local development settings.



Keep actual credentials in `.env` or an appropriate secrets manager. Never commit secrets to the repository.



\## Limitations and Safety



\- \*\*Simulator data:\*\* Alarm and asset records are demonstration fixtures, not live industrial telemetry.

\- \*\*Synthetic procedures:\*\* Synthetic procedure documents are not approved maintenance instructions.

\- \*\*Correlation:\*\* Related or co-occurring alarms do not prove causation.

\- \*\*Priority scoring:\*\* Scores are illustrative and are not validated safety decisions.

\- \*\*Retrieval quality:\*\* Retrieved evidence may be incomplete, outdated, or irrelevant.

\- \*\*LLM output:\*\* Generated explanations can be incorrect and must be independently verified.

\- \*\*Authentication:\*\* Local development authentication is not a substitute for a production security review.

\- \*\*Operational use:\*\* All real-world actions must follow approved site procedures and applicable safety requirements.

\- \*\*Deployment:\*\* Containerized deployment and additional integration, security, and observability validation may require further implementation.



\## Project Structure



alarm-investigation-copilot/

├── app/                 # FastAPI application and simulator data

├── frontend/            # HTML/JavaScript user interface

├── rag/

│   └── documents/       # Procedure and troubleshooting fixtures

├── tests/               # Automated tests

├── data/

│   └── chroma\_db/       # Persistent vector index (generated)

├── investigation.py     # Investigation workflow and MCP client

├── llm\_service.py       # Local LLM report generation

├── mcp\_server.py        # MCP tool definitions and API integration

├── rag\_pipeline.py      # Document ingestion and retrieval

├── test\_mcp\_client.py   # MCP smoke test

├── .env.example         # Environment configuration template

├── requirements.txt     # Python dependencies

└── README.md            # Project documentation



Generated data, local environment files, virtual environments, and other machine-specific artifacts should be excluded from version control where appropriate.



\## Future Improvements



Potential next steps include:



\- Containerized startup and reproducible deployment.

\- Broader end-to-end tests across the frontend, API, MCP server, and RAG workflow.

\- More extensive security and failure-mode testing.

\- Additional monitoring and structured observability.

\- Validation against approved procedure documents and domain-expert review.



These are potential improvements, not claims that the functionality is already implemented.



\## License and Intended Use



This repository is a demonstration project for learning and assessment purposes. Confirm the applicable license and permissions for any third-party dependencies, models, and included documents before redistributing the project.



