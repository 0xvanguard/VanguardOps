.PHONY: help install dev test test-cov lint format check run worker compose-up compose-down compose-logs migrate revision

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-22s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime + dev dependencies
	pip install -r requirements.txt

dev: ## Run the API locally with hot reload
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

worker: ## Run a Celery worker
	celery -A app.workers.celery_app worker --loglevel=info

test: ## Run the fast test suite (no Docker required)
	pytest

test-integration: ## Run integration tests against ephemeral Postgres/Redis (requires Docker)
	pytest -m integration -v

test-all: ## Run unit + integration tests
	pytest -m '' -v

test-cov: ## Run tests with coverage report
	pytest --cov=app --cov-report=term-missing --cov-report=html

lint: ## Static analysis (ruff)
	ruff check .

format: ## Auto-format the codebase (ruff format)
	ruff format .
	ruff check --fix .

check: lint test ## Run linters + tests

compose-up: ## Start the full stack with docker compose
	docker compose up -d --build

compose-down: ## Stop the stack and remove containers
	docker compose down

compose-logs: ## Tail logs of the stack
	docker compose logs -f --tail=100

migrate: ## Apply database migrations
	alembic upgrade head

revision: ## Create a new auto-generated migration. Usage: make revision m="message"
	alembic revision --autogenerate -m "$(m)"
