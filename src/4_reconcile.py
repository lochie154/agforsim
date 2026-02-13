#!/usr/bin/env python3
"""
Step 4 — Reconcile aliases and normalize parameter names.

Uses difflib to find similar parameter names across components and suggests
canonical names. Interactive mode lets you accept, rename, or skip each group.

Usage:
    python 4_reconcile.py suggest [--threshold 0.8]
    python 4_reconcile.py rename dbh_cm dbh [--apply]
    python 4_reconcile.py create-index biomass
    python 4_reconcile.py interactive
"""

from __future__ import annotations

import argparse
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

from _shared import (
    COMPONENTS_DIR,
    INDEXES_DIR,
    resolve_vault,
    parse_frontmatter,
)


# ── parameter collection ──────────────────────────────────────────────────────

def collect_param_names(vault: Path) -> dict[str, list[str]]:
    """
    Collect all parameter names from component frontmatter.

    Returns: {param_name_lower: [list of original spellings]}
    """
    comp_dir = vault / COMPONENTS_DIR
    if not comp_dir.exists():
        return {}

    # Map: lowercase_name -> [(original_name, filepath), ...]
    params: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for f in comp_dir.rglob("*.md"):
        fm = parse_frontmatter(f)
        if not fm:
            continue
        filepath = str(f.relative_to(vault))

        for key in ("inputs", "outputs"):
            for p in fm.get(key, []) or []:
                if isinstance(p, dict):
                    name = p.get("name", "")
                    if name:
                        params[name.lower()].append((name, filepath))

    return params


def find_alias_groups(
    params: dict[str, list[tuple[str, str]]],
    threshold: float = 0.8,
) -> list[list[str]]:
    """
    Group parameter names by similarity using difflib.

    Groups are formed when:
    - Case-insensitive exact match
    - Substring match (one is contained in the other)
    - SequenceMatcher ratio >= threshold
    """
    names = list(params.keys())
    if not names:
        return []

    # Union-find for grouping
    parent: dict[str, str] = {n: n for n in names}

    def find(x: str) -> str:
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a: str, b: str) -> None:
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pa] = pb

    # Compare all pairs
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            # Skip if already in same group
            if find(a) == find(b):
                continue

            # Substring match
            if a in b or b in a:
                union(a, b)
                continue

            # Underscore-normalized match
            a_norm = a.replace("_", "")
            b_norm = b.replace("_", "")
            if a_norm == b_norm:
                union(a, b)
                continue

            # Similarity match
            ratio = SequenceMatcher(None, a, b).ratio()
            if ratio >= threshold:
                union(a, b)

    # Build groups
    groups: dict[str, list[str]] = defaultdict(list)
    for n in names:
        groups[find(n)].append(n)

    # Return only groups with multiple members
    return [sorted(g) for g in groups.values() if len(g) > 1]


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_suggest(vault: Path, threshold: float = 0.8) -> None:
    """Suggest likely parameter aliases."""
    params = collect_param_names(vault)
    groups = find_alias_groups(params, threshold)

    if not groups:
        print("\nNo alias groups found.")
        print("Either all parameters are unique or you have very few components.")
        return

    print(f"\n{'=' * 60}")
    print(f"ALIAS SUGGESTIONS (threshold={threshold})")
    print(f"{'=' * 60}")
    print(f"\nFound {len(groups)} potential alias groups:\n")

    for i, group in enumerate(groups, 1):
        # Suggest canonical name (shortest, or most common)
        usage_counts = {n: len(params[n]) for n in group}
        canonical = max(group, key=lambda n: (usage_counts[n], -len(n)))

        print(f"  {i}. {group}")
        print(f"     → Suggested canonical: '{canonical}'")
        print(f"     Usage: {', '.join(f'{n}({usage_counts[n]})' for n in group)}")
        print()

    print("Use 'python 4_reconcile.py interactive' to review interactively.")
    print(f"{'=' * 60}\n")


def cmd_interactive(vault: Path, threshold: float = 0.8) -> None:
    """Interactive alias reconciliation."""
    params = collect_param_names(vault)
    groups = find_alias_groups(params, threshold)

    if not groups:
        print("\nNo alias groups found. Nothing to reconcile.")
        return

    print(f"\n{'=' * 60}")
    print("INTERACTIVE ALIAS RECONCILIATION")
    print(f"{'=' * 60}")
    print(f"\nFound {len(groups)} groups to review.\n")
    print("For each group, choose:")
    print("  [a]ccept canonical - rename all variants to suggested name")
    print("  [r]ename - specify a different canonical name")
    print("  [s]kip - leave this group unchanged")
    print("  [q]uit - stop reviewing")
    print()

    changes: list[tuple[str, str]] = []  # (old, new) pairs

    for i, group in enumerate(groups, 1):
        usage_counts = {n: len(params[n]) for n in group}
        canonical = max(group, key=lambda n: (usage_counts[n], -len(n)))

        print(f"\n--- Group {i}/{len(groups)} ---")
        print(f"  Variants: {group}")
        print(f"  Suggested: '{canonical}'")
        print(f"  Usage: {', '.join(f'{n}({usage_counts[n]})' for n in group)}")

        while True:
            choice = input("\n  [a]ccept / [r]ename / [s]kip / [q]uit: ").strip().lower()

            if choice == "a":
                for name in group:
                    if name != canonical:
                        changes.append((name, canonical))
                print(f"  → Will rename {len(group) - 1} variants to '{canonical}'")
                break
            elif choice == "r":
                new_name = input("  Enter new canonical name: ").strip()
                if new_name:
                    for name in group:
                        if name != new_name:
                            changes.append((name, new_name))
                    print(f"  → Will rename all to '{new_name}'")
                break
            elif choice == "s":
                print("  → Skipped")
                break
            elif choice == "q":
                print("\nStopping review.")
                break
        else:
            continue

        if choice == "q":
            break

    if not changes:
        print("\nNo changes to apply.")
        return

    print(f"\n{'=' * 60}")
    print(f"SUMMARY: {len(changes)} renames to apply")
    print(f"{'=' * 60}")
    for old, new in changes:
        print(f"  {old} → {new}")

    confirm = input("\nApply these changes? [y/N]: ").strip().lower()
    if confirm == "y":
        for old, new in changes:
            _apply_rename(vault, old, new)
        print("\nChanges applied.")
    else:
        print("\nChanges discarded.")


def _apply_rename(vault: Path, old: str, new: str) -> int:
    """Apply a rename across all component files. Returns count of files modified."""
    comp_dir = vault / COMPONENTS_DIR
    if not comp_dir.exists():
        return 0

    count = 0
    for f in comp_dir.rglob("*.md"):
        content = f.read_text(encoding="utf-8")

        # Replace in YAML frontmatter (name: old → name: new)
        # Handle both quoted and unquoted values
        new_content = re.sub(
            rf'(name:\s*)["\']?{re.escape(old)}["\']?',
            rf'\g<1>{new}',
            content,
        )

        if new_content != content:
            f.write_text(new_content, encoding="utf-8")
            count += 1
            print(f"    Updated: {f.name}")

    return count


def cmd_rename(vault: Path, old: str, new: str, apply: bool) -> None:
    """Rename parameter across all components."""
    comp_dir = vault / COMPONENTS_DIR
    if not comp_dir.exists():
        print("No components directory found.")
        return

    # Collect files that would be modified
    matches: list[Path] = []
    for f in comp_dir.rglob("*.md"):
        content = f.read_text(encoding="utf-8")
        if re.search(rf'name:\s*["\']?{re.escape(old)}["\']?', content):
            matches.append(f)

    if not matches:
        print(f"No components contain parameter '{old}'.")
        return

    print(f"\nFound {len(matches)} files containing '{old}':")
    for f in matches[:10]:
        print(f"  - {f.name}")
    if len(matches) > 10:
        print(f"  ... and {len(matches) - 10} more")

    if apply:
        count = _apply_rename(vault, old, new)
        print(f"\nRenamed '{old}' → '{new}' in {count} files.")
    else:
        print(f"\nUse --apply to rename '{old}' → '{new}' in these files.")


def cmd_create_index(vault: Path, concept: str) -> None:
    """Create index note for a concept cluster."""
    indexes_dir = vault / INDEXES_DIR
    indexes_dir.mkdir(parents=True, exist_ok=True)

    index_file = indexes_dir / f"{concept}.md"

    # Find components that use this concept
    params = collect_param_names(vault)
    usages = params.get(concept.lower(), [])

    component_links = []
    for original_name, filepath in usages:
        # Extract component name from filepath
        comp_name = Path(filepath).stem
        component_links.append(f"- [[{comp_name}]]")

    links_section = "\n".join(component_links) if component_links else "<!-- No components found -->"

    content = f"""---
concept: {concept}
type: index
aliases:
  - {concept}
---

## Components Using '{concept}'

{links_section}

## Notes

<!-- Add notes about this concept -->
"""
    index_file.write_text(content, encoding="utf-8")
    print(f"Created index: {index_file}")
    print(f"  - Found {len(usages)} component usages")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 4: Reconcile aliases and normalize parameter names",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", type=Path, default=None,
        help="Path to vault (defaults to ../)",
    )

    sub = parser.add_subparsers(dest="command", help="Command")

    p = sub.add_parser("suggest", help="Suggest likely aliases")
    p.add_argument("--threshold", type=float, default=0.8, help="Similarity threshold")

    p = sub.add_parser("interactive", help="Interactive alias reconciliation")
    p.add_argument("--threshold", type=float, default=0.8, help="Similarity threshold")

    p = sub.add_parser("rename", help="Rename parameter across components")
    p.add_argument("old", help="Old parameter name")
    p.add_argument("new", help="New parameter name")
    p.add_argument("--apply", action="store_true", help="Apply the rename")

    p = sub.add_parser("create-index", help="Create index note for a concept")
    p.add_argument("concept", help="Concept name")

    args = parser.parse_args()
    vault = resolve_vault(args.vault)

    if args.command == "suggest":
        cmd_suggest(vault, args.threshold)
    elif args.command == "interactive":
        cmd_interactive(vault, args.threshold)
    elif args.command == "rename":
        cmd_rename(vault, args.old, args.new, args.apply)
    elif args.command == "create-index":
        cmd_create_index(vault, args.concept)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
