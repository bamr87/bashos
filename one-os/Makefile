# one-os — entry point for everything (PLAN §5).
#
# On Linux with the tools installed, targets run natively (sudo where needed).
# Elsewhere (macOS), or with USE_DOCKER=1, they run inside docker/builder.Dockerfile.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BUILDER_IMAGE ?= oneos-builder:latest
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Linux)
USE_DOCKER ?= 0
else
USE_DOCKER ?= 1
endif

DOCKER_RUN = docker run --rm --privileged -v /dev:/dev -v "$(CURDIR)":/work -w /work \
	-e CI -e FETCH_LARGE -e PYTEST_ADDOPTS -e ONEOS_ACCEL -e ONEOS_TIMEOUT_SCALE -e ONEOS_KEEP \
	-e ONEOS_OVERLAY -e ONEOS_MIRROR -e IMAGE_SIZE -e ONEOS_IMAGE
ifeq ($(USE_DOCKER),1)
RUN       = $(DOCKER_RUN) $(BUILDER_IMAGE)
RUN_AMD64 = $(DOCKER_RUN) --platform linux/amd64 oneos-builder:amd64
BUILDER_DEP = builder
else
RUN       =
RUN_AMD64 = sudo -E
BUILDER_DEP =
endif

PYTEST = python3 -m pytest -c harness/pyproject.toml --rootdir harness
IMAGE  = build/one-os-test.img

.PHONY: help builder fetch lightos payload image card-image card-boot netboot netboot-server pxe-server pxe-start pxe-stop pxe-restart pxe-status pxe-logs steamos-fetch steamos-capture wizard run vm docs-screenshots test test-full test-image lint flash shell bump clean distclean

help: ## Show targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

builder: ## Build the builder container image(s)
	docker build -f docker/builder.Dockerfile -t $(BUILDER_IMAGE) docker
ifneq ($(UNAME_S)-$(shell uname -m),Linux-x86_64)
	docker build --platform linux/amd64 -f docker/builder.Dockerfile -t oneos-builder:amd64 docker
endif

fetch: $(BUILDER_DEP) ## Download + verify everything in manifest.yaml → cache/
	$(RUN) scripts/fetch.sh

lightos: $(BUILDER_DEP) ## Build the home-base ISO → build/oneos-lightos.iso
	$(RUN_AMD64) scripts/build-lightos.sh

payload: $(BUILDER_DEP) ## Stage the P1 file tree → build/payload/
	$(RUN) scripts/stage-payload.sh

image: $(BUILDER_DEP) ## Sparse 16 GB test image with Ventoy + payload
	$(RUN) $(if $(filter 0,$(USE_DOCKER)),sudo -E) scripts/build-test-image.sh

test: $(BUILDER_DEP) ## Fast test suite (T00–T51 minus nightly)
	$(RUN) $(if $(filter 0,$(USE_DOCKER)),sudo -E) $(PYTEST) -m "not nightly" $(ARGS)

test-full: $(BUILDER_DEP) ## Full matrix incl. nightly tests
	$(RUN) $(if $(filter 0,$(USE_DOCKER)),sudo -E) $(PYTEST) $(ARGS)

test-image: $(BUILDER_DEP) ## Only T00 (no VM)
	$(RUN) $(if $(filter 0,$(USE_DOCKER)),sudo -E) $(PYTEST) harness/tests/test_00_image.py $(ARGS)

lint: $(BUILDER_DEP) ## shellcheck, ruff, manifest schema, no <PIN>s
	$(RUN) scripts/lint.sh

CARD_IMAGE = build/one-os-card.img

card-image: $(BUILDER_DEP) ## macOS: image sized exactly to a device: make card-image DISK=diskN
	@test -n "$(DISK)" || { echo "usage: make card-image DISK=diskN (see 'diskutil list')" >&2; exit 1; }
	$(RUN) env IMAGE=/work/$(CARD_IMAGE) IMAGE_SIZE=$$(diskutil info -plist $(DISK) | plutil -extract TotalSize raw -o - -) \
		scripts/build-test-image.sh

flash: ## Write a real stick: Linux: make flash DEV=/dev/sdX · macOS: make flash DISK=diskN (guarded, no sudo)
ifeq ($(UNAME_S),Darwin)
	@test -n "$(DISK)" || { echo "usage: make flash DISK=diskN" >&2; exit 1; }
	scripts/flash-macos.sh $(DISK) $(FLASH_ARGS)
else ifeq ($(UNAME_S),Linux)
	@test -n "$(DEV)" || { echo "usage: make flash DEV=/dev/sdX" >&2; exit 1; }
	scripts/flash.sh $(DEV) $(FLASH_ARGS)
else
	@echo "flash supports Linux and macOS" >&2; exit 1
endif

card-boot: ## Boot a flashed device in QEMU without writing to it: sudo make card-boot DISK=diskN
	@test -n "$(DISK)" || { echo "usage: sudo make card-boot DISK=diskN" >&2; exit 1; }
	python3 scripts/card-boot.py $(DISK)

netboot: $(BUILDER_DEP) ## Extract the home base for network boot → build/netboot/
	$(RUN) scripts/build-netboot.sh

netboot-server: ## Network boot server, HTTP only (VMs / iPXE): make netboot-server
	python3 netboot/server.py

pxe-server: ## Network boot server + ProxyDHCP/TFTP for real PCs: make pxe-server IFACE=en0
	python3 netboot/server.py --pxe $(if $(IFACE),--iface $(IFACE))

pxe-start: ## PXE server in the background (follows address changes): make pxe-start [IFACE=en0]
	scripts/pxe.sh start $(IFACE)

pxe-stop: ## Stop the background PXE server
	scripts/pxe.sh stop

pxe-restart: ## Restart the background PXE server (picks up server.py changes)
	scripts/pxe.sh restart $(IFACE)

pxe-status: ## PXE server: address, menu URL, recent PCs
	scripts/pxe.sh status

pxe-logs: ## PXE server event log (make pxe-logs ARGS=-f to follow)
	scripts/pxe.sh logs $(ARGS)

steamos-fetch: ## Download Valve's latest SteamOS image into cache/steamos/ (~3.4 GB)
	scripts/fetch-steamos.sh

steamos-capture: ## Capture a bootable SteamOS stick as a deployable image: make steamos-capture DISK=diskN
	@test -n "$(DISK)" || { echo "usage: make steamos-capture DISK=diskN (read-only)" >&2; exit 1; }
	python3 scripts/capture-steamos.py $(DISK)

wizard: ## Open the flash wizard (build → choose device → flash → boot-test) in your browser
	scripts/oneos-wizard

run: ## Boot the stick in a window as VM 'run': make run [VMARGS="--profile bios --fresh"]
	scripts/oneos-vm start run --window $(VMARGS)

vm: ## Drive VMs: make vm ARGS="exec run -- uname -a" (see scripts/oneos-vm --help)
	scripts/oneos-vm $(ARGS)

docs-screenshots: ## Regenerate docs/images/ from real VMs and the wizard (~15 min)
	python3 docs/tools/capture_vm.py
	node docs/tools/capture_wizard.mjs

bump: $(BUILDER_DEP) ## Propose new pins (prints a manifest diff; humans review)
	$(RUN) scripts/bump.sh

shell: $(BUILDER_DEP) ## Interactive shell in the builder
	docker run --rm -it --privileged -v /dev:/dev -v "$(CURDIR)":/work -w /work $(BUILDER_IMAGE) bash

clean: ## Remove build outputs (keeps cache/)
	rm -rf build/payload build/*.img build/test-runs build/payload.SHA256SUMS

distclean: clean ## Remove build/ and cache/
	rm -rf build cache
