#!/usr/bin/env python3
"""
build_indexes.py

Scans the content directories (01_Tools, 02_Components, 03_Scenarios,
04_Ensembles) and writes an index markdown file for each into 09_Indexes.

Each index lists every .md file in the directory (excluding README.md)
as an Obsidian wikilink.

Usage:
    python scripts/build_indexes.py          # run from vault root
    python scripts/build_indexes.py /path/to/vault  # explicit vault path
"""

import sys
from pathlib import Path

# Map source directories to their index filenames and headings.
DIRS = {
    "01_Tools":      ("index-tools.md",      "Index: Tools"),
    "02_Components": ("index-components.md",  "Index: Components"),
    "03_Scenarios":  ("index-scenarios.md",   "Index: Scenarios"),
    "04_Ensembles":  ("index-ensembles.md",   "Index: Ensembles"),
    "10_Concepts":   ("index-concepts.md",    "Index: Concepts"),
}


def collect_entries(source_dir: Path) -> list[str]:
    """Return sorted list of .md filenames (without extension), excluding README."""
    entries = []
    for f in source_dir.iterdir():
        if f.is_file() and f.suffix == ".md" and f.name.lower() != "readme.md":
            entries.append(f.stem)
    entries.sort(key=str.lower)
    return entries


def build_index(heading: str, entries: list[str]) -> str:
    """Build the full markdown content for an index file."""
    lines = []
    if not entries:
        lines.append("_No entries yet._")
    else:
        for name in entries:
            lines.append(f"[[{name}]]")
    lines.append("")  # trailing newline
    return "\n".join(lines)


def main():
    if len(sys.argv) > 1:
        vault = Path(sys.argv[1])
    else:
        vault = Path.cwd()

    index_dir = vault / "09_Indexes"
    if not index_dir.is_dir():
        print(f"Error: {index_dir} does not exist.", file=sys.stderr)
        sys.exit(1)

    for dir_name, (index_file, heading) in DIRS.items():
        source = vault / dir_name
        if not source.is_dir():
            print(f"Warning: {source} not found, skipping.", file=sys.stderr)
            continue

        entries = collect_entries(source)
        content = build_index(heading, entries)

        out_path = index_dir / index_file
        out_path.write_text(content)
        print(f"{out_path.name}: {len(entries)} entries")


if __name__ == "__main__":
    main()
