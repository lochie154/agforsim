#!/usr/bin/env python3
"""
Resolve Concepts from Existing Components

Scans all component files in 02_Components/ and:
1. Extracts inputs, outputs, and assumptions from YAML frontmatter
2. Creates missing concept notes in 10_Concepts/
3. Updates component frontmatter to use wikilinks to concepts

Usage:
    python scripts/resolve_concepts.py [--dry-run]

Options:
    --dry-run    Show what would be done without making changes
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from _shared import COMPONENTS_DIR, CONCEPTS_DIR


def slugify(name: str) -> str:
    """Convert a concept name to a valid filename slug."""
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[\s-]+', '_', slug)
    return slug.strip('_')


def parse_frontmatter(content: str) -> tuple[dict, str, int, int]:
    """
    Parse YAML frontmatter from markdown content.

    Returns:
        (frontmatter_dict, body, fm_start_line, fm_end_line)
    """
    lines = content.split('\n')

    if not lines or lines[0].strip() != '---':
        return {}, content, 0, 0

    # Find closing ---
    fm_end = None
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == '---':
            fm_end = i
            break

    if fm_end is None:
        return {}, content, 0, 0

    # Simple YAML parsing for our structure
    fm_lines = lines[1:fm_end]
    body = '\n'.join(lines[fm_end + 1:])

    fm = {}
    current_key = None
    current_list = None

    for line in fm_lines:
        # Skip empty lines
        if not line.strip():
            continue

        # Check for list item
        if line.startswith('  - '):
            item = line[4:].strip()
            if current_list is not None:
                # Check if it's a dict-style item (name: value)
                if item.startswith('name:'):
                    # Old format: - name: foo
                    name_val = item[5:].strip()
                    current_list.append({'name': name_val, 'type': None, 'unit': None})
                elif item.startswith('"[['):
                    # Already wikilink format
                    current_list.append(item)
                else:
                    # Simple string item (assumptions)
                    current_list.append(item)
        elif line.startswith('    '):
            # Sub-property of list item (type:, unit:)
            # Skip these - we'll regenerate them
            pass
        elif ':' in line and not line.startswith(' '):
            # Top-level key
            key, val = line.split(':', 1)
            key = key.strip()
            val = val.strip()

            if val == '':
                # Start of a list
                current_key = key
                current_list = []
                fm[key] = current_list
            else:
                # Simple key-value
                fm[key] = val
                current_key = None
                current_list = None

    return fm, body, 0, fm_end


def extract_concepts_from_component(fm: dict) -> tuple[list[str], list[str], list[str]]:
    """
    Extract input/output/assumption names from frontmatter.

    Handles both old format (name: foo) and new format ([[slug|name]])
    """
    inputs = []
    outputs = []
    assumes = []

    for item in fm.get('inputs', []):
        if isinstance(item, dict):
            name = item.get('name', '')
            if name:
                inputs.append(name)
        elif isinstance(item, str):
            # Already wikilink format: "[[slug|name]]"
            match = re.search(r'\[\[([^|]+)\|([^\]]+)\]\]', item)
            if match:
                inputs.append(match.group(2))
            else:
                inputs.append(item)

    for item in fm.get('outputs', []):
        if isinstance(item, dict):
            name = item.get('name', '')
            if name:
                outputs.append(name)
        elif isinstance(item, str):
            match = re.search(r'\[\[([^|]+)\|([^\]]+)\]\]', item)
            if match:
                outputs.append(match.group(2))
            else:
                outputs.append(item)

    for item in fm.get('assumes', []):
        if isinstance(item, str):
            match = re.search(r'\[\[([^|]+)\|([^\]]+)\]\]', item)
            if match:
                assumes.append(match.group(2))
            else:
                assumes.append(item)

    return inputs, outputs, assumes


def ensure_concept_note(concepts_dir: Path, concept_name: str, concept_type: str, dry_run: bool) -> bool:
    """
    Create a concept note if it doesn't exist.

    Returns True if created, False if already exists.
    """
    slug = slugify(concept_name)
    concept_path = concepts_dir / f"{slug}.md"

    if concept_path.exists():
        return False

    if dry_run:
        print(f"  [DRY-RUN] Would create: {concept_path.name}")
        return True

    md_lines = [
        "---",
        f"name: {concept_name}",
        f"type: {concept_type}",
        "aliases: []",
        "unit: null",
        "domain: null",
        "---",
        "",
        f"# {concept_name}",
        "",
        "## Description",
        "_TODO: describe this concept_",
        "",
        "## Used By",
        "_Auto-populated by graph queries_",
        "",
    ]
    concept_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  Created: {concept_path.name}")
    return True


def rebuild_frontmatter(fm: dict, inputs: list[str], outputs: list[str], assumes: list[str]) -> str:
    """Rebuild frontmatter YAML with wikilinks."""
    lines = ["---"]

    # Preserve existing scalar fields
    for key in ['name', 'source_tool', 'source_file', 'source_lines', 'source_language', 'validated']:
        if key in fm:
            val = fm[key]
            if isinstance(val, str) and (val.startswith('"') or key == 'source_tool'):
                lines.append(f"{key}: {val}")
            else:
                lines.append(f"{key}: {val}")

    # Add inputs with wikilinks
    lines.append("inputs:")
    for inp in inputs:
        slug = slugify(inp)
        lines.append(f'  - "[[{slug}|{inp}]]"')

    # Add outputs with wikilinks
    lines.append("outputs:")
    for out in outputs:
        slug = slugify(out)
        lines.append(f'  - "[[{slug}|{out}]]"')

    # Add assumptions with wikilinks (if any)
    if assumes:
        lines.append("assumes:")
        for assumption in assumes:
            slug = slugify(assumption)
            lines.append(f'  - "[[{slug}|{assumption}]]"')

    lines.append("---")
    return "\n".join(lines)


def process_component(comp_path: Path, concepts_dir: Path, dry_run: bool) -> tuple[int, bool]:
    """
    Process a single component file.

    Returns (concepts_created, component_updated)
    """
    content = comp_path.read_text(encoding="utf-8")
    fm, body, _, _ = parse_frontmatter(content)

    if not fm:
        print(f"  Skipping {comp_path.name}: no frontmatter")
        return 0, False

    inputs, outputs, assumes = extract_concepts_from_component(fm)

    # Create concept notes
    created = 0
    for inp in inputs:
        if ensure_concept_note(concepts_dir, inp, "input", dry_run):
            created += 1
    for out in outputs:
        if ensure_concept_note(concepts_dir, out, "output", dry_run):
            created += 1
    for assumption in assumes:
        if ensure_concept_note(concepts_dir, assumption, "assumption", dry_run):
            created += 1

    # Check if component needs updating (old format without wikilinks)
    needs_update = False
    for item in fm.get('inputs', []):
        if isinstance(item, dict):
            needs_update = True
            break
    if not needs_update:
        for item in fm.get('outputs', []):
            if isinstance(item, dict):
                needs_update = True
                break
    if not needs_update:
        for item in fm.get('assumes', []):
            if isinstance(item, str) and not item.startswith('"[['):
                needs_update = True
                break

    if needs_update:
        new_fm = rebuild_frontmatter(fm, inputs, outputs, assumes)
        new_content = new_fm + "\n" + body

        if dry_run:
            print(f"  [DRY-RUN] Would update: {comp_path.name}")
        else:
            comp_path.write_text(new_content, encoding="utf-8")
            print(f"  Updated: {comp_path.name}")

    return created, needs_update


def main():
    parser = argparse.ArgumentParser(description="Resolve concepts from existing components")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without making changes")
    args = parser.parse_args()

    # Find vault root
    vault = Path(__file__).parent.parent
    components_dir = vault / COMPONENTS_DIR
    concepts_dir = vault / CONCEPTS_DIR

    if not components_dir.exists():
        print(f"Error: Components directory not found: {components_dir}")
        return 1

    # Ensure concepts directory exists
    concepts_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 60}")
    print("  RESOLVE CONCEPTS FROM COMPONENTS")
    print(f"{'=' * 60}")
    print(f"  Components: {components_dir}")
    print(f"  Concepts:   {concepts_dir}")
    if args.dry_run:
        print("  Mode:       DRY RUN (no changes)")
    print(f"{'=' * 60}\n")

    # Process all component files
    comp_files = sorted(components_dir.glob("*.md"))
    comp_files = [f for f in comp_files if f.name != "README.md"]

    total_concepts = 0
    total_updated = 0

    for comp_path in comp_files:
        print(f"\nProcessing: {comp_path.name}")
        created, updated = process_component(comp_path, concepts_dir, args.dry_run)
        total_concepts += created
        if updated:
            total_updated += 1

    print(f"\n{'=' * 60}")
    print("  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Components processed: {len(comp_files)}")
    print(f"  Concepts created:     {total_concepts}")
    print(f"  Components updated:   {total_updated}")
    print(f"{'=' * 60}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
