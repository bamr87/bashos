.PHONY: install test lint repl gui run doctor up down clean chui-install chui-dry-run chui-check

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
	shellcheck -x -P SCRIPTDIR --severity=warning chui/*.sh chui/config/home.sh chui/config/terminal/macos-font.sh

repl:
	$(VENV)/bin/bashos

gui:      ## the desktop window (browser fallback without the [gui] extra)
	$(VENV)/bin/bashos gui

doctor:
	$(VENV)/bin/bashos doctor

up:       ## phoenix + langgraph-dev services
	docker compose up -d

down:
	docker compose down

chui-install:  ## macOS terminal environment (chui/README.md); no venv needed
	./chui/install.sh

chui-dry-run:
	./chui/install.sh --dry-run

chui-check:
	./chui/check.sh

clean:
	rm -rf $(VENV) dist build .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
