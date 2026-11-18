# bashOS tools

> Repository scripts for bashOS — the desktop capture, the documentation generators and the Markdown prose fixer; nothing here ships to users.

| Where | What |
| --- | --- |
| [`capture_desktop.py`](capture_desktop.py) | Capture the bashOS desktop: the stills and GIFs in docs/DESKTOP-TOUR.md |
| [`docs_index.py`](docs_index.py) | Generate the `docs/README.md` index from each document's summary line (vendored byte-identical from the bamr87 hub; change it there) |
| [`gen_commands_table.py`](gen_commands_table.py) | Generate the README commands table from `.claude/commands/*.md` frontmatter (`--write`, `--check`) |
| [`unwrap-prose.py`](unwrap-prose.py) | Join soft-wrapped Markdown prose so each paragraph is one line; the `markdown-oneline` gate runs it (vendored byte-identical from the bamr87 hub; change it there) |
