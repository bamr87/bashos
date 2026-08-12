.PHONY: install test lint repl run doctor up down clean

VENV := .venv

install:
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install --quiet --upgrade pip
	$(VENV)/bin/pip install --quiet -e ".[dev]"

test:
	$(VENV)/bin/pytest -q

lint:
	$(VENV)/bin/ruff check .
	shellcheck bin/bashos

repl:
	$(VENV)/bin/bashos

doctor:
	$(VENV)/bin/bashos doctor

up:       ## phoenix + langgraph-dev services
	docker compose up -d

down:
	docker compose down

clean:
	rm -rf $(VENV) dist build .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
