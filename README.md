# 🧟 Zombie SaaS Consolidator

**Google AI Builder Cup 2026 Submission**

An autonomous, multi-agent orchestration platform that detects redundant ("zombie") SaaS subscriptions and orchestrates safe migrations — built entirely on the Google Cloud ecosystem.

## Architecture

Built with **Google Agent Development Kit (ADK)**, the system uses three specialized AI agents coordinated by a root orchestrator:

```
zombie_saas_coordinator (Root Orchestrator — Gemini Pro)
├── auditor_agent (Gemini Flash) — Detection & proposals
├── architect_agent (Gemini Pro)  — Semantic validation
└── integrator_agent (Gemini Flash) — Dependency scanning
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **AI Orchestration** | Google ADK (`google-adk`) |
| **LLMs** | Gemini 2.0 Pro + Flash (Vertex AI) |
| **Compute** | Google Cloud Run |
| **Auth** | Firebase Authentication |
| **Document DB** | Firebase Firestore |
| **Relational DB** | Google Cloud SQL (PostgreSQL) |
| **Frontend** | Firebase Hosting |
| **Secrets** | Google Secret Manager |
| **Scheduling** | Google Cloud Scheduler |
| **Audit** | Google Cloud Audit Logs |

## Quick Start

```bash
# 1. Install dependencies
pip install -e ".[dev]"

# 2. Copy env template
cp .env.example .env

# 3. Run the ADK local dev UI (Root Coordinator with delegating sub-agents)
adk web adk_app

# 4. Or run directly in terminal
adk run zombie_saas_coordinator
```

## Deployment

```bash
# Deploy to Cloud Run
adk deploy cloud_run \
  --project=zombie-saas-coordinator \
  --region=asia-south1 \
  --service-name=zombie-coordinator
```

## Project Structure

```
zombie_saas_coordinator/
├── __init__.py                 # Exports root_agent for ADK CLI
├── agent.py                    # Root orchestrator agent
├── main.py                     # FastAPI entry point (Cloud Run)
├── agents/
│   ├── auditor/                # US-1, US-2, US-3, US-4
│   │   ├── agent.py            # Agent definition
│   │   └── tools.py            # Tool functions
│   ├── architect/              # US-6, US-7, US-8, US-9
│   │   ├── agent.py
│   │   └── tools.py
│   └── integrator/             # US-10
│       ├── agent.py
│       └── tools.py
├── api/                        # Cloud Run HTTP endpoints
├── shared/
│   ├── db/                     # Firestore + Cloud SQL clients
│   ├── models/                 # Pydantic data models
│   ├── auth/                   # Firebase Auth + HMAC
│   └── integrations/           # Trello, Asana, Zapier, Make, Slack
└── tests/                      # pytest (test_US{N}_*.py)
```

## Documentation

- [PRD](docs/../PRD.md) — Product Requirements Document
- [Architecture](docs/architecture.md) — System architecture
- [Tech Specs](docs/techspecs/) — Per-story technical specifications (TS-1 through TS-10)

## Contributing

Each team member works on their assigned user story. Before implementing:

1. Read the tech spec: `docs/techspecs/TS-{N}.md`
2. Implement the `TODO` stubs in the corresponding `tools.py`
3. Write tests in `tests/test_US{N}_*.py`
4. Run `ruff check .` before pushing
