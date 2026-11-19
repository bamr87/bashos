# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0](https://github.com/bamr87/bashos/compare/bashos-v0.1.0...bashos-v1.0.0) (2026-11-18)


### ⚠ BREAKING CHANGES

* the desktop becomes the default surface; the line REPL retires

### Features

* add banner ASCII art to render module ([2d8b211](https://github.com/bamr87/bashos/commit/2d8b211e9f82c7f4c2f5a194ac9b6367a2a6c50d))
* **amrchy:** bashOS boots as Amrchy plus the bashOS layer ([0f37de5](https://github.com/bamr87/bashos/commit/0f37de522bae69f887c8d8c2908f76aa0b37d8da))
* **amrchy:** fold bamr87/amrchy in as a squashed subtree ([b9cdbdc](https://github.com/bamr87/bashos/commit/b9cdbdc852cb2cea5fac2ff167ea15e31f23025f))
* **amrchy:** layers — a product's own setup runs last in the installer ([11cef12](https://github.com/bamr87/bashos/commit/11cef1217eccb65ecda860ebc852e92a4d2032e2))
* **chui:** merge bamr87/chui into bashOS; install/configure it with `bashos chui` ([#31](https://github.com/bamr87/bashos/issues/31)) ([38bc1cc](https://github.com/bamr87/bashos/commit/38bc1cca4f76f35838bc4caacaf1f0fedb6ac1ba))
* **engine:** OpenCode is a managed dependency, always on its latest verified release ([bff01b4](https://github.com/bamr87/bashos/commit/bff01b4aa3f4368510ac9db6084087d006e055c3))
* **engine:** OpenCode is a managed dependency, always on its latest verified release ([ee810b8](https://github.com/bamr87/bashos/commit/ee810b855be345c5130a0ab980379a7e3ba3379a))
* **engine:** speak OpenCode 2 alongside OpenCode 1 ([94417f6](https://github.com/bamr87/bashos/commit/94417f6f537b08c550d18ff15e2ad8da5898f053))
* **engine:** speak OpenCode 2 alongside OpenCode 1 ([c8363e3](https://github.com/bamr87/bashos/commit/c8363e3e1ee912776b39e6e0148fea5681a497a7)), closes [#71](https://github.com/bamr87/bashos/issues/71)
* **engine:** verify drives the OpenCode 2 session routes a turn uses ([b6c4f00](https://github.com/bamr87/bashos/commit/b6c4f002d49e486cf0173afb87985c1f53e9e286))
* **gui:** desktop front end on the same kernel (`bashos gui`) ([4a7eaac](https://github.com/bamr87/bashos/commit/4a7eaac2704b5694feca806290bd1186a3b37dc1))
* **gui:** desktop front end on the same kernel, with the OS-shell Phase 0 (`bashos gui`) ([1863189](https://github.com/bamr87/bashos/commit/18631896a7a77e76620d5119e45d75f1c57ca4b1))
* **gui:** implement the OS-shell Phase 0 — side by side, on the same scenes ([930ed27](https://github.com/bamr87/bashos/commit/930ed27c841d65cd5b2e29aa56ca24bb25dbb3da))
* **gui:** the desktop — floating windows, icons, a taskbar, shareable layouts ([6bc075d](https://github.com/bamr87/bashos/commit/6bc075d0a007b3f491369ac8b14688c340220392))
* **gui:** the desktop — floating windows, icons, a taskbar, shareable layouts ([d918f5d](https://github.com/bamr87/bashos/commit/d918f5d1c336c3ce27e6bed597da9790fd5f47a5))
* heuristic classifier, session memory, and confirm-then-run exec ([3f36b29](https://github.com/bamr87/bashos/commit/3f36b29693db37f954821644921089613920b294))
* **one-os:** fold one-usb into bashos as one-os ([2aa273c](https://github.com/bamr87/bashos/commit/2aa273cf9aa1e6fce35557e9a1a8a3574ddaaf29))
* **one-os:** fold one-usb into bashos as one-os ([de59d1a](https://github.com/bamr87/bashos/commit/de59d1a26ad92c6e4e6f2b8f783b0b35d95fc9fe))
* **one-os:** machine profiles — check a custom PC's chips against a system's kernel ([584cf9c](https://github.com/bamr87/bashos/commit/584cf9ccd8d2fa0458bb9a9f8a91a799cc4df5d0))
* **one-os:** remote sessions — drive a machine and run Claude Code on it over SSH ([5428848](https://github.com/bamr87/bashos/commit/5428848ed108142c5ff93d1892dd5d4cf2c5a733))
* **one-os:** the X870E desktop replaces forge as bashOS's machine ([067b557](https://github.com/bamr87/bashos/commit/067b5572267570b8f18a79c757d77557f4845545))
* **opencode:** make the OpenCode engine the core of bashOS, on Claude Code OAuth ([#9](https://github.com/bamr87/bashos/issues/9)) ([c9ac3d1](https://github.com/bamr87/bashos/commit/c9ac3d18f7d6127ff529485c8e95d4497d969c40))
* opt-in interactive approvals — the bashos-interactive profile (default off) ([326a3cf](https://github.com/bamr87/bashos/commit/326a3cfac6d2aef23f06fe4f399d5a7aaa34dd79))
* opt-in interactive approvals — the bashos-interactive profile (default off) ([556b19e](https://github.com/bamr87/bashos/commit/556b19e424a80e5030cf6f891b1d32851ceecb60))
* **os:** Amrchy (Arch) is a base the OS layer installs on ([a5f70c1](https://github.com/bamr87/bashos/commit/a5f70c11c376e86cfefe02a4f98b432d513deaba))
* **os:** bashOS as the operating system — an Omarchy-style Debian 13 layer and a bootable mkosi image ([c8e256a](https://github.com/bamr87/bashos/commit/c8e256a9aa20e682b415c7d26d19e733d15e0457))
* **os:** bashos os amrchy — keep amrchy/ in step with bamr87/amrchy ([282f956](https://github.com/bamr87/bashos/commit/282f956009b76ca5ba7f472e503c11bcc6e085af))
* **os:** the bashOS ISO — Amrchy with the bashOS layer, installed unattended ([477d969](https://github.com/bamr87/bashos/commit/477d9698fe4b33a099e650ced6f75c0c6fea3814))
* **os:** turn the monitor and drive the kiosk remotely over VNC ([ae3e7c5](https://github.com/bamr87/bashos/commit/ae3e7c5e9954d7eb3a6c160feb0580e6c0deba55))
* **os:** turn the monitor and drive the kiosk remotely over VNC ([0c38696](https://github.com/bamr87/bashos/commit/0c38696044297cfede6d5a1fc85df1b70d30d12b))
* **remote:** the forge pattern — health floor, /health + /dash, and ssh remote layer with monitor mirroring ([79a0c09](https://github.com/bamr87/bashos/commit/79a0c091191fca5ba89813f6c5638d54099abeb4))
* shared event bus, reusable engine sessions, and text-delta streaming ([5327d3a](https://github.com/bamr87/bashos/commit/5327d3ab7b4b8e042805f50514fb11286b451e13))
* the AI Console — full REPL parity in a desktop window ([ff31c71](https://github.com/bamr87/bashos/commit/ff31c711900ddce64667f9786b2d48310f59b6d8))
* the bashOS desktop skeleton — Textual app behind `bashos desktop` ([d9b3734](https://github.com/bamr87/bashos/commit/d9b37344e3b01149be61e023fbfdf7b1c1f325ac))
* the desktop app suite — health, engine inspector, commands, trace, OpenCode ([39f7fe4](https://github.com/bamr87/bashos/commit/39f7fe4870ece0aafe6f2a6c2f74bebc7fa8cc2a))
* the desktop becomes the default surface; the line REPL retires ([3795317](https://github.com/bamr87/bashos/commit/37953170863d25a6f2b159211851c0d30cfd5d83))
* typed engine events and error taxonomy beside the legacy string path ([790e6d1](https://github.com/bamr87/bashos/commit/790e6d14a5e9ed94aee48b2a1deb6c4160bba191))


### Bug Fixes

* **ci:** wait for OpenCode's platform package before the engine canary fetches ([8b220e1](https://github.com/bamr87/bashos/commit/8b220e1762ae8e3e75e37a888cbda8823baa287b))
* **ci:** wait for OpenCode's platform package before the engine canary fetches ([aee5663](https://github.com/bamr87/bashos/commit/aee566356ff74b499d6e403a81f6b7435250e103))
* **cli:** opencode auth names the wiring of the engine bashOS would start ([86ae7ed](https://github.com/bamr87/bashos/commit/86ae7ed66fbcd3717ffa67c26c4f9eb6036f1970))
* **desktop:** record ShellRunner outcome so the !cmd test stops racing RichLog ([5dadbda](https://github.com/bamr87/bashos/commit/5dadbdaaf929ad878793ea8ff3b18778e3a8c507))
* **desktop:** record ShellRunner outcome so the !cmd test stops racing RichLog ([b14dc3a](https://github.com/bamr87/bashos/commit/b14dc3a63e970b2897d4f996c441c92bd4e53041))
* **one-os:** a stick without a SteamOS image says so, and CI goes without ([77d039f](https://github.com/bamr87/bashos/commit/77d039fbd28f92cda913a796f913a1142ad2140d))
* **one-os:** repin netboot.xyz to its 2026-11-13 build ([48435e1](https://github.com/bamr87/bashos/commit/48435e145b7b19cd482dd3d0f120181821dceffc))
* **one-os:** the harness waits out udev, and keeps sockets short ([b607a0e](https://github.com/bamr87/bashos/commit/b607a0ebcb77cbc6ce4bfb891e8f79b1e6c99dbf))
* **one-os:** UEFI test VMs connect their NIC, and CI's guests reach the apt cache ([11ae0aa](https://github.com/bamr87/bashos/commit/11ae0aa75ca9101a3aaef2cd60d2b419e6651ccd))
* **os:** a Node outside PATH satisfies the nodejs guard ([360bc3c](https://github.com/bamr87/bashos/commit/360bc3c91cd5e2b94a8f3d5591889833d90a8bb7))
* **os:** a Node outside PATH satisfies the nodejs guard ([6306bcc](https://github.com/bamr87/bashos/commit/6306bcc262c5a121bb406bed9282a55e35bfe95c))
* **os:** harness config errors exit 78 and never restart-loop ([922b760](https://github.com/bamr87/bashos/commit/922b760ed4be3c24b085dca2cdbb47898b430d99))
* **os:** keep /opt/bashos world-readable; a no-op deploy reports unchanged ([bec76ae](https://github.com/bamr87/bashos/commit/bec76ae051f4bd76117a1ec581b652559f2f11c8))
* **os:** network-online needs one wired link; the boot test drives the kiosk ([227639a](https://github.com/bamr87/bashos/commit/227639a08537f946527b4a89b11457aebb4148f0))
* **os:** provision without $HOME; its output on the journal and console ([01ad19c](https://github.com/bamr87/bashos/commit/01ad19cb52f05f80bc8349569b75041a86c7faaa))
* **os:** the image ships login and passwd; the boot test fits small hosts ([49c35b6](https://github.com/bamr87/bashos/commit/49c35b6c2573b7c0b45c5ef56c87aefadd0b16c3))
* **os:** turn every output in one wlr-randr call ([c977253](https://github.com/bamr87/bashos/commit/c977253dd815b2d4ce31ca916af414fb2491a4e3))
* **os:** what the kiosk starts never holds cage's client pipe ([60697f2](https://github.com/bamr87/bashos/commit/60697f252b7da595773f3eaed414ecd3c0c517ce))
* **policy:** no allowlisted probe can run another command ([0c6adff](https://github.com/bamr87/bashos/commit/0c6adff119a3e4cb61e4eccbe20d3f22d22ddd5c))
* **policy:** no allowlisted probe can run another command ([bd9baad](https://github.com/bamr87/bashos/commit/bd9baad225603bd4618446dd7b184d0d2d2507cb))
* **release:** run the publish jobs on a manual re-publish ([5466c97](https://github.com/bamr87/bashos/commit/5466c9708c79003e2fde16dcc597a7f56c7016fb))


### Documentation

* add feature catalog, constitution and amendments; link PRD ([#44](https://github.com/bamr87/bashos/issues/44)) ([c8364d1](https://github.com/bamr87/bashos/commit/c8364d1a08d2a4ff800346d5f03692336311f9fc))
* **adr:** 0003 — bashOS by BASH Consulting is a fork of Omarchy, kept current by an AI upstream sync ([18e5ab8](https://github.com/bamr87/bashos/commit/18e5ab8ff7bb7e442ac56e0b6582bec8657d6609))
* **adr:** 0003 — bashOS by BASH Consulting is a fork of Omarchy, kept current by an AI-assisted upstream sync ([2f3a4dc](https://github.com/bamr87/bashos/commit/2f3a4dcf4f28b85ae0463ca06570b6d742b5bb5c))
* **agents:** add AGENTS.md as the canonical agent contract ([#35](https://github.com/bamr87/bashos/issues/35)) ([7d2134b](https://github.com/bamr87/bashos/commit/7d2134b026b77cb4b4cb154acd6ca48c2892c0fe))
* bashOS boots as Amrchy plus the bashOS layer (ADR 0005, amendment 0002) ([de73075](https://github.com/bamr87/bashos/commit/de7307581f00c6bf4e67fbc5d1787ef46da522a3))
* **changelog:** add CHANGELOG.md in Keep a Changelog format ([#33](https://github.com/bamr87/bashos/issues/33)) ([9d4ba27](https://github.com/bamr87/bashos/commit/9d4ba2782ed6dcfa22b9787f5dba69cced632839))
* **contributing:** name the markdown-oneline gate ([b643051](https://github.com/bamr87/bashos/commit/b6430519c015bb84f024141502a7cc2a4d3b5ea2))
* **engine:** the managed engine, the contract, and OpenCode 2 ([bcc8d98](https://github.com/bamr87/bashos/commit/bcc8d98f23ade4ed2b75172346837e36b38c7213))
* **gui:** tour the desktop with real captures, and a capture tool to keep it honest ([05e77b0](https://github.com/bamr87/bashos/commit/05e77b0be1fd01d8c81cf04a917f81b250f51cac))
* harmonize documentation to the fleet docs framework ([#45](https://github.com/bamr87/bashos/issues/45)) ([9d3a586](https://github.com/bamr87/bashos/commit/9d3a586a32f756acc2a76d1375c07ac09dd472c6))
* **readme:** align README with the portfolio standard ([#32](https://github.com/bamr87/bashos/issues/32)) ([2cdabd1](https://github.com/bamr87/bashos/commit/2cdabd1500cd387d768aaeaf494613613c9d1f39))
* **security:** add SECURITY.md with private vulnerability reporting policy ([cfed4ae](https://github.com/bamr87/bashos/commit/cfed4aefa45fd96f183abf2edb335a8f1837efba))
* **security:** add SECURITY.md with private vulnerability reporting policy ([1ea33d1](https://github.com/bamr87/bashos/commit/1ea33d146b7e08f7561763bc74c14306154e5dfa)), closes [#51](https://github.com/bamr87/bashos/issues/51)
* the bashOS ISO built and installed unattended in CI ([19ab2bc](https://github.com/bamr87/bashos/commit/19ab2bc38120edaa9ce24d57b8ec105dcb68a880))
* the Omarchy 4.5 run also brought the harness up ([f6a851e](https://github.com/bamr87/bashos/commit/f6a851e5f69c9ce1b6ae0bf863513cc97360e1bf))
* **tools:** list the vendored unwrap-prose.py ([8347c32](https://github.com/bamr87/bashos/commit/8347c32c1b68b68d9812a33790ea0928a96238f2))
* unwrap DESKTOP-TOUR.md after merging main ([0c5c862](https://github.com/bamr87/bashos/commit/0c5c862eeaeb214193977e8f2ffbd8ac1ae32b4e))
* unwrap one-os skill for the markdown-oneline gate ([8c46e7c](https://github.com/bamr87/bashos/commit/8c46e7c5ff4f7b6e446174e9e0f4ad13667f86b6))

## [Unreleased]

### Added

- `CHANGELOG.md`, in Keep a Changelog format.

### Changed

Merged to `main` since v0.1.0:

- 2026-10-17: docs(readme): align README with the portfolio standard ([#32](https://github.com/bamr87/bashos/pull/32))
- 2026-10-16: chore(deps): update rich requirement from &gt;=13.9 to &gt;=15.0.0 ([#28](https://github.com/bamr87/bashos/pull/28))
- 2026-10-16: chore(deps-dev): update pytest-asyncio requirement ([#29](https://github.com/bamr87/bashos/pull/29))
- 2026-10-16: chore(repo): add fleet .editorconfig (UPS-REPO-17) ([#30](https://github.com/bamr87/bashos/pull/30))
- 2026-10-15: chore(deps): update pydantic requirement from &gt;=2.9 to &gt;=2.13.5 ([#25](https://github.com/bamr87/bashos/pull/25))
- 2026-10-15: chore(deps-dev): update openinference-instrumentation-langchain requirement from &gt;=0.1.76 to &gt;=0.1.78 ([#27](https://github.com/bamr87/bashos/pull/27))
- 2026-10-06: test(desktop): poll for the shell window's exit line instead of a single pause ([#24](https://github.com/bamr87/bashos/pull/24))
- 2026-10-04: test(cli): match --exec in plain text so CI's forced colour doesn't break it ([#23](https://github.com/bamr87/bashos/pull/23))
- 2026-10-03: chore(deps-dev): update openinference-instrumentation-langchain requirement ([#19](https://github.com/bamr87/bashos/pull/19))
- 2026-10-03: chore(deps): update langchain-anthropic requirement ([#18](https://github.com/bamr87/bashos/pull/18))
- 2026-10-03: chore(deps): update typer requirement from &gt;=0.15 to &gt;=0.27.1 ([#16](https://github.com/bamr87/bashos/pull/16))
- 2026-10-03: chore(deps): update httpx requirement from &gt;=0.27 to &gt;=0.28.1 ([#15](https://github.com/bamr87/bashos/pull/15))
- 2026-09-20: feat: add banner ASCII art to render module
- 2026-09-19: Refactor documentation and code structure for Phase 0 implementation
- 2026-09-19: feat: opt-in interactive approvals — the bashos-interactive profile (default off) (×2)
- …and 18 earlier changes.

## [0.1.0] - 2026-08-11

- 2026-08-11: bashOS v0.1.0: terminal-first AI runtime on a LangGraph kernel

[Unreleased]: https://github.com/bamr87/bashos/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/bamr87/bashos/releases/tag/v0.1.0
