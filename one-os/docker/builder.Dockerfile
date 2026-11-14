# Pinned Debian builder: live-build, QEMU + firmware, exFAT, harness deps.
# Multi-arch: `make lightos` runs it as linux/amd64 (live-build must match the
# target arch); everything else runs native (Ventoy ships aarch64 tools, and
# qemu-system-x86_64 runs under TCG on arm64 hosts).
FROM debian:trixie-20251020-slim

ENV DEBIAN_FRONTEND=noninteractive LC_ALL=C.UTF-8 PIP_BREAK_SYSTEM_PACKAGES=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      live-build debootstrap squashfs-tools xorriso mtools isolinux syslinux-common \
      qemu-system-x86 qemu-utils ovmf seabios ipxe-qemu \
      exfatprogs exfat-fuse dosfstools e2fsprogs parted gdisk fdisk util-linux udev kmod \
      rsync curl ca-certificates jq git make xz-utils zstd file procps \
      python3 python3-yaml python3-jinja2 python3-pytest python3-jsonschema \
      shellcheck tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

# ruff for `make lint` (pinned).
RUN apt-get update && apt-get install -y --no-install-recommends python3-pip \
    && pip3 install --no-cache-dir ruff==0.14.3 \
    && apt-get purge -y python3-pip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# OCR preprocessing for harness/oneos_harness/screen.py.
RUN apt-get update && apt-get install -y --no-install-recommends python3-pil \
    && rm -rf /var/lib/apt/lists/*

# Network boot (iPXE loaders served over TFTP) and docs rendering for the stick.
# bzip2/lbzip2: stick-add-steamos.sh unpacks Valve's .img.bz2 recovery image.
RUN apt-get update && apt-get install -y --no-install-recommends ipxe python3-markdown bzip2 lbzip2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
