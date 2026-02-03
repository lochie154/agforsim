#!/usr/bin/env python3
"""
Track extraction progress and analyze emergent clusters.

Usage:
    python 3_track.py status
    python 3_track.py inputs
    python 3_track.py outputs  
    python 3_track.py pipelines
    python 3_track.py gaps
"""

import argparse
import re
from pathlib import Path
from collections import Counter, defaultdict

# TODO:
# - [ ] Count components per tool
# - [ ] Frequency analysis of input names
# - [ ] Frequency analysis of output names
# - [ ] Find shared dependencies
# - [ ] Identify potential pipelines (output→input matches)
# - [ ] List components missing types/units
# - [ ] Export cluster report to indexes/


def parse_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter from markdown."""
    try:
        content = filepath.read_text()
        if not content.startswith("---"):
            return None
        end = content.find("\n---\n", 3)
        if end == -1:
            return None
        
        import yaml
        return yaml.safe_load(content[3:end])
    except:
        return None


def load_components(vault: Path) -> list[dict]:
    """Load all component frontmatter."""
    components = []
    comp_dir = vault / "components"
    if not comp_dir.exists():
        return []
    
    for f in comp_dir.rglob("*.md"):
        fm = parse_frontmatter(f)
        if fm:
            fm["_file"] = str(f.relative_to(vault))
            components.append(fm)
    return components


def cmd_status(vault: Path):
    """Show extraction status."""
    comps = load_components(vault)
    
    print(f"\n{'='*50}")
    print("EXTRACTION STATUS")
    print(f"{'='*50}")
    print(f"\nTotal components: {len(comps)}")
    
    by_tool = Counter()
    for c in comps:
        tool = re.search(r'\[\[tools/(.+?)\]\]', str(c.get("source_tool", "")))
        by_tool[tool.group(1) if tool else "unknown"] += 1
    
    print("\nPer tool:")
    for tool, count in by_tool.most_common():
        print(f"  {tool}: {count}")


def cmd_inputs(vault: Path):
    """Show most common inputs."""
    comps = load_components(vault)
    names = Counter()
    
    for c in comps:
        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                names[inp.get("name", "").lower()] += 1
    
    print(f"\n{'='*50}")
    print("MOST COMMON INPUTS (emergent concepts)")
    print(f"{'='*50}\n")
    
    for name, count in names.most_common(30):
        bar = "█" * min(count, 30)
        print(f"  {name:25} {count:3}  {bar}")


def cmd_outputs(vault: Path):
    """Show most common outputs."""
    comps = load_components(vault)
    names = Counter()
    
    for c in comps:
        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                names[out.get("name", "").lower()] += 1
    
    print(f"\n{'='*50}")
    print("MOST COMMON OUTPUTS")
    print(f"{'='*50}\n")
    
    for name, count in names.most_common(30):
        bar = "█" * min(count, 30)
        print(f"  {name:25} {count:3}  {bar}")


def cmd_pipelines(vault: Path):
    """Find potential pipelines (output→input chains)."""
    comps = load_components(vault)
    
    inputs_map = defaultdict(list)
    outputs_map = defaultdict(list)
    
    for c in comps:
        name = c.get("name", "unknown")
        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                inputs_map[inp.get("name", "").lower()].append(name)
        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                outputs_map[out.get("name", "").lower()].append(name)
    
    print(f"\n{'='*50}")
    print("POTENTIAL PIPELINES")
    print(f"{'='*50}\n")
    
    for param in set(inputs_map.keys()) & set(outputs_map.keys()):
        producers = outputs_map[param]
        consumers = inputs_map[param]
        print(f"  [{param}]")
        print(f"    Produced by: {', '.join(producers[:5])}")
        print(f"    Consumed by: {', '.join(consumers[:5])}")
        print()


def cmd_gaps(vault: Path):
    """Identify gaps."""
    comps = load_components(vault)
    
    all_inputs = set()
    all_outputs = set()
    missing_units = []
    
    for c in comps:
        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                all_inputs.add(inp.get("name", "").lower())
                if not inp.get("unit"):
                    missing_units.append(c.get("name"))
        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                all_outputs.add(out.get("name", "").lower())
    
    print(f"\n{'='*50}")
    print("GAP ANALYSIS")
    print(f"{'='*50}")
    
    external = all_inputs - all_outputs
    print(f"\nExternal dependencies (inputs with no producer):")
    for name in sorted(external)[:20]:
        print(f"  - {name}")
    
    terminal = all_outputs - all_inputs
    print(f"\nTerminal outputs (outputs not consumed):")
    for name in sorted(terminal)[:20]:
        print(f"  - {name}")
    
    print(f"\nComponents missing units: {len(set(missing_units))}")


def main():
    parser = argparse.ArgumentParser(description="Track extraction progress")
    parser.add_argument("command", choices=["status", "inputs", "outputs", "pipelines", "gaps"])
    parser.add_argument("--vault", type=Path, default=Path(".."))
    
    args = parser.parse_args()
    
    if args.command == "status":
        cmd_status(args.vault)
    elif args.command == "inputs":
        cmd_inputs(args.vault)
    elif args.command == "outputs":
        cmd_outputs(args.vault)
    elif args.command == "pipelines":
        cmd_pipelines(args.vault)
    elif args.command == "gaps":
        cmd_gaps(args.vault)


if __name__ == "__main__":
    main()
