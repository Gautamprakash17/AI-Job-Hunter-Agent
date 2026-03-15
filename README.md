# AI Job Hunter Agent

A production-style system that automatically discovers, ranks, and helps apply to relevant jobs using semantic similarity with your resume.

## Features

- **Resume parsing** — Extract structured data from PDF/TXT resumes via LLM
- **Multi-portal job discovery** — Live scraping from LinkedIn, Indeed, Naukri
- **Semantic ranking** — Rank jobs by similarity to your resume using embeddings
- **Application tracking** — Track application status in SQLite
- **LangGraph workflow** — Orchestrated pipeline: parse → discover → rank
- **FastAPI backend** — REST API for integrations
- **Streamlit dashboard** — Web UI for resume upload and workflow execution

## Project Structure

```
ai_job_hunter_agent/
├── agents/           # LLM agents (resume, discovery, ranking, application, tracking)
├── rag/              # Embeddings, Chroma vector store, retriever
├── workflows/        # LangGraph job hunter graph
├── tools/            # Browser automation, LinkedIn/Indeed/Naukri scrapers
├── database/         # SQLite models and session management
├── api/              # FastAPI backend
├── dashboard/        # Streamlit UI
├── config/           # Settings and env config
├── main.py           # Entry point (api, dashboard, workflow CLI)
└── requirements.txt
```

## Setup

```bash
cd ai_job_hunter_agent
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
playwright install chromium
```

Create a `.env` file:

```
OPENAI_API_KEY=your_key_here
```

## Usage

**Run FastAPI server:**
```bash
python main.py api
```

**Run Streamlit dashboard:**
```bash
python main.py dashboard
```

**Run workflow from CLI:**
```bash
python main.py workflow --resume data/uploads/resume.pdf --role "AI Engineer" --location "India"
```

**Optional:** Set `USE_DEMO_JOBS_ON_EMPTY=false` in `.env` to disable demo fallback when scrapers return 0 jobs.

## API Endpoints

- `GET /api/health` — Health check
- `POST /api/upload-resume` — Upload resume file
- `POST /api/run-workflow` — Run full workflow
- `GET /api/applications` — List applications
- `GET /api/jobs` — List discovered jobs
# AI-Job-Hunter-Agent
