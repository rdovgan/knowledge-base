# CAKB — Codebase Analysis & Knowledge Base

**RAG pipeline for Java project analysis**: source code parsing, domain grouping, wiki generation, LLM enrichment, vector indexing, and a search API.

The project is designed to be **reusable for any Java project**.

---

## Architecture

```
Java Source Code (sources/)
        │
        ▼
┌─────────────────────────────────────────────┐
│  RAG Pipeline  (run_rag.py)                 │
│                                             │
│  1. Parse    → java_parser.py               │
│  2. Group    → domain_grouper.py            │
│  3. Markdown → markdown_writer.py           │
│  4. Enrich   → enricher.py   (LLM)         │
│  4.5 Flows   → flow_generator.py (LLM)     │
│  5. Index    → indexer.py    (ChromaDB)     │
│                                             │
│  state → data/parsed/, data/domains/        │
│  wiki  → rag/  (git submodule)              │
│  index → data/vectorstore/                  │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│  Dashboard API  (dashboard.py)   :8090      │
│                                             │
│  GET  /              — Web UI               │
│  POST /api/query     — Semantic search      │
│  POST /api/ask       — RAG: search + LLM   │
│  GET  /api/status    — Pipeline status      │
│  GET  /api/history   — Request history      │
│  GET  /api/stats     — Usage stats          │
└─────────────────────────────────────────────┘
```

There is also a **CrewAI pipeline** (`pipeline/`, `run_pipeline.py`) — an alternative approach using AI agents for exploration and wiki generation.

---

## Project Structure

```
cakb/
├── .env                        # API keys (ZAI_API_KEY, etc.)
├── .env.example                # Example configuration
├── .gitignore
├── .gitmodules                 # rag/ — git submodule with wiki
├── cakb-api.service            # systemd unit for Dashboard API
│
├── dashboard.py                # FastAPI server — search, RAG queries, UI
├── db.py                       # SQLite — API request history
├── generate_entity_table_map.py # Utility: Java entity → DB table mapping
│
├── run_rag.py                  # ⭐ Main RAG pipeline runner
├── rag_pipeline/               # RAG pipeline modules
│   ├── java_parser.py          #   Parse Java code (classes, methods, annotations)
│   ├── domain_grouper.py       #   Group classes by domain
│   ├── markdown_writer.py      #   Generate wiki pages (.md)
│   ├── enricher.py             #   LLM enrichment of domains (descriptions, links)
│   ├── flow_generator.py       #   LLM generation of cross-domain flow docs
│   ├── indexer.py              #   Index wiki into ChromaDB vectorstore
│   └── models.py               #   Data models (ParsedClass, Domain, etc.)
│
├── run_pipeline.py             # CrewAI pipeline runner (agent-based approach)
├── pipeline/                   # CrewAI pipeline modules
│   ├── orchestrator.py         #   Orchestrator: explore → generate → review
│   ├── decomposer.py           #   Split large modules into domains
│   ├── pipeline_state.py       #   State manager (JSON file)
│   ├── crews/
│   │   ├── explorer_crew.py    #   Agent: scan code, determine wiki pages
│   │   └── wiki_crew.py        #   Agent: generate and review wiki
│   └── models/
│       └── domain.py           #   Data models (Domain, WikiPage, ModulePlan)
│
├── config/
│   └── modules.yaml            # Module list for CrewAI pipeline
│
├── scripts/
│   ├── run_pipeline.sh         # Bash wrapper for run_rag.py
│   └── status.sh               # Status script (monitoring)
│
├── sources/                    # ← Java sources (not in git, place them here)
├── rag/                        # Git submodule — generated wiki (markdown)
├── data/                       # Runtime data (not in git)
│   ├── parsed/parsed.json      #   Parsed Java code result
│   ├── domains/domains.json    #   Grouped domains
│   ├── vectorstore/            #   ChromaDB index
│   └── api_history.db          #   API request history
└── logs/                       # Pipeline and API logs
```

---

## Installation

### 1. Clone

```bash
git clone <repo-url> cakb
cd cakb
git submodule update --init --recursive
```

### 2. Python Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn chromadb sentence-transformers openai pydantic PyYAML markdown-it-py
```

For the CrewAI pipeline, additionally:

```bash
pip install crewai crewai-tools
```

### 3. Configuration

Create a `.env` file in the project root:

```env
# Required for enrichment and RAG responses
ZAI_API_KEY=your_api_key_here

# Optional (have default values)
LLM_BASE_URL=https://api.z.ai/api/coding/paas/v4
LLM_MODEL=glm-5-turbo
LLM_FALLBACK_MODEL=glm-4.7
INDEX_MAX_RETRIES=3
```

### 4. Prepare Source Code

Place the Java project in the `sources/` directory:

```bash
mkdir -p sources
# For example:
ln -s /path/to/your/java/project sources/my-project
```

The `sources/` directory should contain subdirectories with `.java` files. Each subdirectory = one module:

```
sources/
├── module-a/
│   └── com/example/...
├── module-b/
│   └── com/example/...
└── ...
```

---

## Usage

### RAG Pipeline (`run_rag.py`)

This is the main pipeline. All steps are **idempotent** — re-running skips already completed steps.

```bash
# Full pipeline (steps 1-5)
python3 run_rag.py all

# Individual steps:
python3 run_rag.py parse       # 1. Parse Java → parsed.json
python3 run_rag.py group       # 2. Group → domains.json
python3 run_rag.py markdown    # 3. Generate wiki (.md files in rag/)
python3 run_rag.py enrich      # 4. LLM enrichment (domain descriptions)
python3 run_rag.py flows       # 4.5. Cross-domain flow documents (LLM)
python3 run_rag.py index       # 5. Index wiki → ChromaDB vectorstore
```

#### Useful Options

```bash
# Check current status
python3 run_rag.py status

# Query the vector store (without API server)
python3 run_rag.py query "how does reservation creation work?"

# Parse a single module
python3 run_rag.py parse --module redis

# Enrichment with limit (for testing)
python3 run_rag.py enrich --limit 5

# Force — rerun a step even if already completed
python3 run_rag.py all --force
python3 run_rag.py index --force    # full reindex

# Number of search results
python3 run_rag.py query "text" --top-k 10
```

#### Bash Wrapper

```bash
./scripts/run_pipeline.sh              # all
./scripts/run_pipeline.sh --status     # status
./scripts/run_pipeline.sh --force      # full restart
./scripts/run_pipeline.sh --reset      # delete data and start from scratch
./scripts/run_pipeline.sh --enrich     # enrichment only
./scripts/run_pipeline.sh --index      # indexing only
./scripts/run_pipeline.sh --stop       # stop a running pipeline
```

### CrewAI Pipeline (`run_pipeline.py`)

An alternative approach with AI agents. Automatically explores code, plans wiki pages, generates and reviews them.

```bash
# Run (continuous, until all modules are processed)
python3 run_pipeline.py

# Start from scratch
python3 run_pipeline.py --reset
```

Module configuration: `config/modules.yaml`

```yaml
modules:
  - name: my-module
    path: sources/my-module
    priority: 1
    description: "Module description"
    enabled: true
```

### Dashboard API (`dashboard.py`)

FastAPI server with a web UI for search and monitoring.

```bash
# Run manually
python3 dashboard.py

# Or via systemd
sudo systemctl start cakb-api
sudo systemctl enable cakb-api   # autostart
```

The server is available at `http://localhost:8090`.

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Dashboard UI |
| `POST` | `/api/query` | Semantic search over wiki (`{"query": "..."}`) |
| `GET` | `/api/query?q=...` | Same via GET |
| `POST` | `/api/ask` | RAG: search + LLM answer (`{"query": "..."}`) |
| `GET` | `/api/ask?q=...` | Same via GET |
| `GET` | `/api/status` | Pipeline status |
| `GET` | `/api/status-rag` | ChromaDB index statistics |
| `GET` | `/api/history` | Request history (paginated) |
| `GET` | `/api/history/{id}` | Details of a specific request |
| `GET` | `/api/stats` | Aggregated usage statistics |

Supports `?format=md` to get responses in Markdown format.

### Utility: Entity → Table Map

Generates a mapping of Java entity classes → MySQL tables by analyzing MyBatis mapper XMLs.

```bash
# All modules
python3 generate_entity_table_map.py

# Single module
python3 generate_entity_table_map.py --module dataaccesslayer
```

Output:
- `rag/entity-table-map.md` — document for RAG
- `data/entity_table_map.json` — machine-readable JSON

---

## Cron Scheduling

For regular index updates:

```cron
# Daily at 3:00 AM — full pipeline
0 3 * * * cd /home/r.dovgan/cakb && python3 run_rag.py all >> logs/cron.log 2>&1
```

---

## Data Overview

| Path | What | Git |
|------|------|-----|
| `data/parsed/parsed.json` | Parsed Java code (classes, methods, annotations) | ❌ ignored |
| `data/domains/domains.json` | Grouped domains with classes | ❌ ignored |
| `data/vectorstore/` | ChromaDB vector index | ❌ ignored |
| `data/api_history.db` | SQLite with API request history | ❌ ignored |
| `data/entity_table_map.json` | Entity→Table mapping | ❌ ignored |
| `rag/` | Generated wiki (markdown) | ✅ git submodule |
| `logs/` | Pipeline and API logs | ❌ ignored |

---

## Adapting for a New Project

1. Place Java sources in `sources/` (each module in a separate folder)
2. Create `.env` with your API key
3. Run `python3 run_rag.py all`
4. Result: wiki in `rag/`, vector index in `data/vectorstore/`
5. Run `python3 dashboard.py` for the search API

For the CrewAI pipeline: update `config/modules.yaml` with your project's module list.
