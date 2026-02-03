#!/usr/bin/env python3
"""
Generate Python component stubs from markdown.

Usage:
    python 5_implement.py biomass_from_dbh
    python 5_implement.py --all --category growth
"""

import argparse
import re
from pathlib import Path

# TODO:
# - [ ] Parse component frontmatter
# - [ ] Generate Component subclass skeleton
# - [ ] Map inputs to Parameter objects
# - [ ] Insert original code as comment
# - [ ] Insert pseudocode as docstring
# - [ ] Write to src/agforsim/components/{category}/
# - [ ] Auto-detect category from component location


def parse_frontmatter(filepath: Path) -> dict | None:
    """Parse YAML frontmatter."""
    try:
        content = filepath.read_text()
        if not content.startswith("---"):
            return None
        end = content.find("\n---\n", 3)
        if end == -1:
            return None
        import yaml
        fm = yaml.safe_load(content[3:end])
        
        # Also extract code blocks
        code_match = re.search(r'## Original Code\s+```\w*\n(.+?)```', content, re.DOTALL)
        if code_match:
            fm["_original_code"] = code_match.group(1).strip()
        
        return fm
    except:
        return None


def generate_stub(fm: dict) -> str:
    """Generate Python component stub."""
    name = fm.get("name", "unknown")
    tool = re.search(r'\[\[tools/(.+?)\]\]', str(fm.get("source_tool", "")))
    tool = tool.group(1) if tool else "unknown"
    
    # Generate input schema
    inputs_code = ""
    for inp in fm.get("inputs", []) or []:
        if isinstance(inp, dict):
            n = inp.get("name", "x")
            inputs_code += f'            "{n}": Parameter("{n}", float),\n'
    
    # Generate output schema
    outputs_code = ""
    for out in fm.get("outputs", []) or []:
        if isinstance(out, dict):
            n = out.get("name", "result")
            outputs_code += f'            "{n}": Parameter("{n}", float),\n'
    
    original = fm.get("_original_code", "# No original code found")
    
    return f'''"""
{name} - extracted from {tool}

PROVENANCE:
- Source: {fm.get("source_file", "unknown")}
- Lines: {fm.get("source_lines", "unknown")}
- Language: {fm.get("source_language", "unknown")}
"""

from agforsim.core.component import Component, ComponentMeta
from agforsim.core.parameter import Parameter
from agforsim.core.registry import registry


@registry.component("growth")  # TODO: correct category
class {name.title().replace("_", "")}(Component):
    """
    TODO: Add description
    
    Original code:
    ```
{original}
    ```
    """
    
    meta = ComponentMeta(
        name="{name}",
        source_tool="{tool}",
        source_file="{fm.get("source_file", "")}",
        source_lines="{fm.get("source_lines", "")}",
        source_language="{fm.get("source_language", "")}",
    )
    
    @property
    def input_schema(self):
        return {{
{inputs_code}        }}
    
    @property
    def output_schema(self):
        return {{
{outputs_code}        }}
    
    def run(self, inputs: dict) -> dict:
        """
        TODO: Implement from original code
        """
        # TODO: translate original code
        raise NotImplementedError()
'''


def main():
    parser = argparse.ArgumentParser(description="Generate component stubs")
    parser.add_argument("name", nargs="?", help="Component name")
    parser.add_argument("--all", action="store_true", help="Generate all")
    parser.add_argument("--vault", type=Path, default=Path(".."))
    parser.add_argument("--output", type=Path, help="Output directory")
    
    args = parser.parse_args()
    
    comp_dir = args.vault / "components"
    out_dir = args.output or (args.vault / "src" / "agforsim" / "components" / "growth")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    if args.name:
        # Find specific component
        matches = list(comp_dir.rglob(f"{args.name}*.md"))
        if not matches:
            print(f"Component not found: {args.name}")
            return
        
        for match in matches:
            fm = parse_frontmatter(match)
            if fm:
                stub = generate_stub(fm)
                out_file = out_dir / f"{fm.get('name', 'unknown')}.py"
                out_file.write_text(stub)
                print(f"Wrote {out_file}")
    
    elif args.all:
        for f in comp_dir.rglob("*.md"):
            fm = parse_frontmatter(f)
            if fm and fm.get("name"):
                stub = generate_stub(fm)
                out_file = out_dir / f"{fm['name']}.py"
                out_file.write_text(stub)
                print(f"Wrote {out_file}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
