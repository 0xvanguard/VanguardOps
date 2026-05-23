# VanguardOps 🛡️

VanguardOps is an Enterprise-grade IT Support Automation & DevSecOps Operations platform. It centralizes asset management, intelligent ticket routing, and autonomous workflow execution with a fully auditable activity timeline.

## Core Capabilities
- **Intelligent Triage:** Auto-calculation of Priority and SLA based on incident severity and category.
- **Asynchronous Workflows:** Celery + Redis integration to securely run background operations (e.g. Ping traces, Password resets).
- **Immutable Audit Trail:** Activity Log capturing the exact lifecycle of tickets and workflows.
- **Operational Dashboard:** Glassmorphism UI built-in to monitor real-time NOC metrics.

## Tech Stack
- **API:** FastAPI, Pydantic v2
- **Database:** PostgreSQL (SQLAlchemy ORM)
- **Async Engine:** Celery & Redis
- **Frontend:** Vanilla JS + CSS3 (Glassmorphism)

## Quick Start (Docker Compose)
We provide a production-like local deployment using Docker Compose.

```bash
# 1. Build and start the entire cluster (API, Worker, Postgres, Redis)
docker-compose up --build -d

# 2. Access the platform
# Operational Dashboard: http://localhost:8000/
# Swagger UI / API Docs: http://localhost:8000/docs
```

## Architecture Layers
- `app/api/`: Routing, validation and auth.
- `app/services/`: Core business logic (SLA, Priority, Assignment, Workflow orchestrator).
- `app/workers/`: Celery task wrappers and remote script executors.
- `app/crud/` & `app/models/`: Persistence layer.
