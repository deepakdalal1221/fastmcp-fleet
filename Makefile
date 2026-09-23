.PHONY: help sync fmt lint typecheck test test-unit test-integration test-contract run-fetch run-gateway create clean

help:
	@echo "sync            Install/refresh deps with uv"
	@echo "fmt             Format with ruff"
	@echo "lint            Lint with ruff"
	@echo "typecheck       Type-check with mypy"
	@echo "test            Run all tests"
	@echo "test-unit       Run unit tests only"
	@echo "test-contract   Run contract tests only"
	@echo "run-fetch       Run the fetch pilot server"
	@echo "run-gateway     Run the aggregation gateway"
	@echo "create NAME=x   Scaffold a new server"

sync:
	uv sync --all-extras

fmt:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff check .

typecheck:
	uv run mypy packages/mcp_common gateway

test:
	uv run pytest

test-unit:
	uv run pytest -m unit

test-integration:
	uv run pytest -m integration

test-contract:
	uv run pytest -m contract

run-fetch:
	uv run python -m servers.fetch

run-gateway:
	uv run mcp-gateway

create:
	@if [ -z "$(NAME)" ]; then echo "Usage: make create NAME=<server-name>"; exit 1; fi
	uv run mcp-create --name $(NAME)

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +

# ============================================================================
# Sequential compose orchestration
# ============================================================================
COMPOSE ?= docker compose -f deployment/compose/docker-compose.yml
SLEEP_BETWEEN ?= 1

.PHONY: up up-sequential up-parallel down ps logs

## up: start all services one by one (aliased to up-sequential)
up: up-sequential

## up-sequential: bring up every service one at a time (fetch first, gateway last)
up-sequential:
	@echo "Starting services sequentially..."
	@svcs=$$($(COMPOSE) config --services | grep -v '^gateway$$' | sort); \
	for svc in $$svcs; do \
		echo "-> up $$svc"; \
		$(COMPOSE) up -d --no-deps $$svc; \
		sleep $(SLEEP_BETWEEN); \
	done; \
	echo "-> up gateway"; \
	$(COMPOSE) up -d --no-deps gateway
	@echo "All services up. $(COMPOSE) ps"

## up-parallel: original parallel behavior (all services at once)
up-parallel:
	$(COMPOSE) up -d

## down: stop and remove all services
down:
	$(COMPOSE) down

## ps: list running compose services
ps:
	$(COMPOSE) ps

## logs: tail gateway logs
logs:
	$(COMPOSE) logs -f gateway
