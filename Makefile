.PHONY: install test lint repl gui run doctor up down clean chui-install chui-dry-run chui-check os-dry-run os-image os-image-test

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
	shellcheck -x -P SCRIPTDIR --severity=warning os/*.sh os/install/*.sh os/bin/* os/image/build.sh os/image/test/boot-smoke.sh os/image/mkosi.postinst.chroot

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

os-dry-run:    ## the Linux OS layer's install plan for this machine (docs/OS.md); changes nothing
	./os/install.sh --dry-run

os-image:      ## the bootable bashOS disk image (mkosi; --docker from macOS)
	./os/image/build.sh $(if $(filter Linux,$(shell uname -s)),,--docker)

os-image-test: ## boot it in QEMU with a seed drive and check it like its person would
	./os/image/test/boot-smoke.sh $(if $(filter Linux,$(shell uname -s)),,--docker)

clean:
	rm -rf $(VENV) dist build .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
