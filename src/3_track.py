#!/usr/bin/env python3
"""
Step 3 — Track extraction progress and analyse emergent patterns.

Reads component and tool frontmatter from the vault and reports on
progress, parameter frequency, clusters, gaps, and pipeline chains.

Usage:
    python 3_track.py status   [vault]
    python 3_track.py inputs   [vault]
    python 3_track.py outputs  [vault]
    python 3_track.py clusters [vault]
    python 3_track.py gaps     [vault]
    python 3_track.py export   [vault] --output graph.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

from _shared import (
    TOOLS_DIR,
    COMPONENTS_DIR,
    OUTPUT_DIR,
    resolve_vault,
    parse_frontmatter,
)


# ── loading helpers ───────────────────────────────────────────────────────────

def load_components(vault: Path) -> list[dict]:
    """Load all component frontmatter from the vault."""
    comp_dir = vault / COMPONENTS_DIR
    if not comp_dir.exists():
        return []
    comps = []
    for f in comp_dir.rglob("*.md"):
        fm = parse_frontmatter(f)
        if fm:
            fm["_filepath"] = str(f.relative_to(vault))
            fm["_filename"] = f.stem
            comps.append(fm)
    return comps


def load_tools(vault: Path) -> list[dict]:
    """Load all tool frontmatter from the vault."""
    tools_dir = vault / TOOLS_DIR
    if not tools_dir.exists():
        return []
    tools = []
    for f in tools_dir.glob("*.md"):
        fm = parse_frontmatter(f)
        if fm:
            fm["_filepath"] = str(f.relative_to(vault))
            fm["_filename"] = f.stem
            tools.append(fm)
    return tools


def _tool_name(source_tool: str) -> str:
    """Extract tool name from wikilink format [[name]] or [[tools/name]]."""
    if not source_tool:
        return "unknown"
    # Handle [[name]] format (new)
    m = re.search(r"\[\[([^\]/]+)\]\]", str(source_tool))
    if m:
        return m.group(1)
    # Handle [[tools/name]] format (legacy)
    m = re.search(r"\[\[tools/(.+?)\]\]", str(source_tool))
    if m:
        return m.group(1)
    # Plain string
    return str(source_tool).strip() or "unknown"


def _param_names(components: list[dict], key: str) -> Counter:
    """Count parameter names across all components."""
    names: Counter = Counter()
    for c in components:
        for p in c.get(key, []) or []:
            if isinstance(p, dict):
                n = p.get("name", "").lower()
                if n:
                    names[n] += 1
    return names


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_status(vault: Path) -> None:
    """Show extraction status summary."""
    comps = load_components(vault)
    tools = load_tools(vault)

    print(f"\n{'=' * 60}")
    print("EXTRACTION STATUS")
    print(f"{'=' * 60}")
    print(f"\nTotal components: {len(comps)}")
    print(f"Total tools: {len(tools)}")

    by_tool: Counter = Counter()
    for c in comps:
        by_tool[_tool_name(c.get("source_tool", ""))] += 1
    print("\n--- Components per Tool ---")
    for tool, count in by_tool.most_common():
        print(f"  {tool}: {count}")

    by_lang: Counter = Counter(c.get("source_language", "unknown") for c in comps)
    print("\n--- By Language ---")
    for lang, count in by_lang.most_common():
        print(f"  {lang}: {count}")

    validated = sum(1 for c in comps if c.get("validated"))
    print("\n--- Validation ---")
    print(f"  Validated:   {validated}")
    print(f"  Unvalidated: {len(comps) - validated}")

    hardcoded = sum(1 for c in comps if c.get("hardcoded_constants"))
    print("\n--- Quality Flags ---")
    print(f"  Hardcoded constants: {hardcoded}")
    print(f"\n{'=' * 60}\n")


def cmd_inputs(vault: Path, top_n: int = 30) -> None:
    """Show most common input parameters."""
    names = _param_names(load_components(vault), "inputs")

    print(f"\n{'=' * 60}")
    print(f"MOST COMMON INPUTS (top {top_n})")
    print(f"{'=' * 60}")
    print("\nThese are your emergent input concepts:\n")
    for name, count in names.most_common(top_n):
        bar = "█" * min(count, 40)
        print(f"  {name:25} {count:4}  {bar}")
    print(f"\n{'=' * 60}\n")


def cmd_outputs(vault: Path, top_n: int = 30) -> None:
    """Show most common output parameters."""
    names = _param_names(load_components(vault), "outputs")

    print(f"\n{'=' * 60}")
    print(f"MOST COMMON OUTPUTS (top {top_n})")
    print(f"{'=' * 60}")
    print("\nThese are your emergent output concepts:\n")
    for name, count in names.most_common(top_n):
        bar = "█" * min(count, 40)
        print(f"  {name:25} {count:4}  {bar}")
    print(f"\n{'=' * 60}\n")


def cmd_clusters(vault: Path, min_shared: int = 2) -> None:
    """Find emergent clusters of related functions."""
    comps = load_components(vault)

    input_map: dict[str, list[str]] = defaultdict(list)
    output_map: dict[str, list[str]] = defaultdict(list)

    for c in comps:
        cname = c.get("name", "unknown")
        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                n = inp.get("name", "").lower()
                if n:
                    input_map[n].append(cname)
        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                n = out.get("name", "").lower()
                if n:
                    output_map[n].append(cname)

    print(f"\n{'=' * 60}")
    print("EMERGENT CLUSTERS")
    print(f"{'=' * 60}")

    print("\n--- Input Clusters (functions sharing same inputs) ---\n")
    for param, funcs in sorted(input_map.items(), key=lambda x: -len(x[1])):
        if len(funcs) >= min_shared:
            print(f"  [{param}] ({len(funcs)} functions)")
            for f in funcs[:10]:
                print(f"    - {f}")
            if len(funcs) > 10:
                print(f"    ... and {len(funcs) - 10} more")
            print()

    print("\n--- Output Clusters (functions producing same outputs) ---\n")
    for param, funcs in sorted(output_map.items(), key=lambda x: -len(x[1])):
        if len(funcs) >= min_shared:
            print(f"  [{param}] ({len(funcs)} functions)")
            for f in funcs[:10]:
                print(f"    - {f}")
            if len(funcs) > 10:
                print(f"    ... and {len(funcs) - 10} more")
            print()

    print("\n--- Potential Pipelines (output matches input) ---\n")
    for param in sorted(set(output_map) & set(input_map)):
        producers = output_map[param]
        consumers = input_map[param]
        if producers and consumers:
            print(f"  [{param}]")
            print(f"    Produced by: {', '.join(producers[:5])}")
            print(f"    Consumed by: {', '.join(consumers[:5])}")
            print()

    print(f"{'=' * 60}\n")


def cmd_gaps(vault: Path) -> None:
    """Identify gaps in the extraction coverage."""
    comps = load_components(vault)

    all_inputs: set[str] = set()
    all_outputs: set[str] = set()
    incomplete: list[str] = []

    for c in comps:
        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                n = inp.get("name", "").lower()
                if n:
                    all_inputs.add(n)
                if not inp.get("type"):
                    incomplete.append(c.get("name", "unknown"))
        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                n = out.get("name", "").lower()
                if n:
                    all_outputs.add(n)
                if not out.get("type"):
                    incomplete.append(c.get("name", "unknown"))

    print(f"\n{'=' * 60}")
    print("GAP ANALYSIS")
    print(f"{'=' * 60}")

    external = sorted(all_inputs - all_outputs)
    print("\n--- External Dependencies ---")
    print("(Inputs that no function produces -- require external data)\n")
    for n in external:
        print(f"  - {n}")

    terminal = sorted(all_outputs - all_inputs)
    print("\n--- Terminal Outputs ---")
    print("(Outputs that no function consumes -- final results)\n")
    for n in terminal:
        print(f"  - {n}")

    unique_incomplete = sorted(set(incomplete))
    print("\n--- Incomplete Type Information ---")
    print(f"({len(unique_incomplete)} components need type refinement)\n")
    for n in unique_incomplete[:20]:
        print(f"  - {n}")
    if len(unique_incomplete) > 20:
        print(f"  ... and {len(unique_incomplete) - 20} more")

    print(f"\n{'=' * 60}\n")


def cmd_export(vault: Path, output: Path) -> None:
    """Export a node/edge graph as JSON for D3, Cytoscape, etc."""
    comps = load_components(vault)

    nodes: list[dict] = []
    edges: list[dict] = []
    seen_params: set[str] = set()

    for c in comps:
        cname = c.get("name", "unknown")
        nodes.append({
            "id": f"comp:{cname}",
            "label": cname,
            "type": "component",
            "language": c.get("source_language"),
        })

        for inp in c.get("inputs", []) or []:
            if isinstance(inp, dict):
                pname = inp.get("name", "").lower()
                if pname:
                    pid = f"param:{pname}"
                    if pid not in seen_params:
                        nodes.append({"id": pid, "label": pname, "type": "parameter"})
                        seen_params.add(pid)
                    edges.append({"source": pid, "target": f"comp:{cname}", "type": "input"})

        for out in c.get("outputs", []) or []:
            if isinstance(out, dict):
                pname = out.get("name", "").lower()
                if pname:
                    pid = f"param:{pname}"
                    if pid not in seen_params:
                        nodes.append({"id": pid, "label": pname, "type": "parameter"})
                        seen_params.add(pid)
                    edges.append({"source": f"comp:{cname}", "target": pid, "type": "output"})

    output.write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=2))
    print(f"Exported graph data to {output}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 3: Track progress and analyse patterns",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", type=Path, default=None,
        help="Path to vault (defaults to ../)",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    sub.add_parser("status", help="Show extraction status")

    p = sub.add_parser("inputs", help="Most common input params")
    p.add_argument("--top", type=int, default=30)

    p = sub.add_parser("outputs", help="Most common output params")
    p.add_argument("--top", type=int, default=30)

    p = sub.add_parser("clusters", help="Find emergent clusters")
    p.add_argument("--min", type=int, default=2)

    sub.add_parser("gaps", help="Identify gaps")

    p = sub.add_parser("export", help="Export graph data as JSON")
    p.add_argument("--output", type=Path, default=None)

    args = parser.parse_args()
    vault = resolve_vault(args.vault)

    if args.command == "status":
        cmd_status(vault)
    elif args.command == "inputs":
        cmd_inputs(vault, args.top)
    elif args.command == "outputs":
        cmd_outputs(vault, args.top)
    elif args.command == "clusters":
        cmd_clusters(vault, getattr(args, "min", 2))
    elif args.command == "gaps":
        cmd_gaps(vault)
    elif args.command == "export":
        output = args.output or (vault / OUTPUT_DIR / "graph.json")
        output.parent.mkdir(parents=True, exist_ok=True)
        cmd_export(vault, output)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
