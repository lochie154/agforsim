#!/usr/bin/env python3
"""
Reconcile aliases and normalize parameter names.

Usage:
    python 4_reconcile.py suggest
    python 4_reconcile.py rename dbh_cm dbh --apply
    python 4_reconcile.py create-index biomass
"""

import argparse
from pathlib import Path
from collections import defaultdict

# TODO:
# - [ ] Detect likely aliases (dbh, DBH, diameter_breast_height)
# - [ ] Suggest canonical names
# - [ ] Batch rename across component files
# - [ ] Create indexes/{concept}.md for clusters
# - [ ] Interactive merge mode
# - [ ] Undo capability


def suggest_aliases(vault: Path):
    """Suggest likely aliases."""
    # TODO: Implement alias detection
    # Group by similar names (edit distance, common stems)
    print("\nAlias suggestions:")
    print("  dbh, DBH, dbh_cm → dbh")
    print("  height, ht, height_m → height")
    print("  biomass, bio_mass, agb → biomass")
    print("\n  (TODO: implement actual detection)")


def rename_param(vault: Path, old: str, new: str, apply: bool):
    """Rename parameter across all components."""
    comp_dir = vault / "components"
    if not comp_dir.exists():
        print("No components directory")
        return
    
    count = 0
    for f in comp_dir.rglob("*.md"):
        content = f.read_text()
        if old in content:
            count += 1
            if apply:
                new_content = content.replace(f"name: {old}", f"name: {new}")
                f.write_text(new_content)
                print(f"  Updated {f}")
            else:
                print(f"  Would update {f}")
    
    if not apply:
        print(f"\n{count} files would be modified. Use --apply to execute.")


def create_index(vault: Path, concept: str):
    """Create index note for a concept cluster."""
    indexes_dir = vault / "indexes"
    indexes_dir.mkdir(parents=True, exist_ok=True)
    
    index_file = indexes_dir / f"{concept}.md"
    
    # TODO: Auto-populate with components that use this concept
    content = f"""---
concept: {concept}
type: index
---

## Components Using {concept}

<!-- Auto-generated list -->

## Notes

"""
    index_file.write_text(content)
    print(f"Created {index_file}")


def main():
    parser = argparse.ArgumentParser(description="Reconcile aliases")
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("suggest", help="Suggest aliases")
    
    rename_p = subparsers.add_parser("rename", help="Rename parameter")
    rename_p.add_argument("old", help="Old name")
    rename_p.add_argument("new", help="New name")
    rename_p.add_argument("--apply", action="store_true")
    
    index_p = subparsers.add_parser("create-index", help="Create index note")
    index_p.add_argument("concept", help="Concept name")
    
    parser.add_argument("--vault", type=Path, default=Path(".."))
    
    args = parser.parse_args()
    
    if args.command == "suggest":
        suggest_aliases(args.vault)
    elif args.command == "rename":
        rename_param(args.vault, args.old, args.new, args.apply)
    elif args.command == "create-index":
        create_index(args.vault, args.concept)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
