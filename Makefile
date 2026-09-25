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


.PHONY: dev
## dev: run the whole fleet in a single Python process on :9000 (offline mode)
dev:
	MCP_OFFLINE=1 uv run python -m gateway.all_in_one

.PHONY: demo
## demo: scripted multi-server agent trajectory (github → jira → slack)
demo:
	@./scripts/demo.sh

dashboard:
	uv run python -m gateway.dashboard

# ============================================================================
# One-command offline mock fleet (all 175 servers in 1 container on :9000)
# ============================================================================
IMAGE_MONO ?= mcp-fleet:local
CONTAINER_MONO ?= mcp-fleet

.PHONY: start stop restart logs-mono rebuild mono-build mono-run

start: mono-build mono-run

mono-build:
	docker build -f docker/Dockerfile.mono -t $(IMAGE_MONO) .

mono-run:
	@mkdir -p state
	@docker rm -f $(CONTAINER_MONO) 2>/dev/null || true
	docker run -d --name $(CONTAINER_MONO) \
		-p 9000:9000 \
		-e MCP_OFFLINE=1 \
		-v $(PWD)/state:/state \
		$(IMAGE_MONO)
	@echo ""
	@echo "Fleet up on http://localhost:9000/mcp"
	@echo "  logs:  make logs-mono"
	@echo "  stop:  make stop"

stop:
	docker rm -f $(CONTAINER_MONO) 2>/dev/null || true

restart: stop mono-run

logs-mono:
	docker logs -f $(CONTAINER_MONO)

rebuild: stop mono-build mono-run
