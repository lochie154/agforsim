#!/usr/bin/env python3
"""
Scan codebase for functions.

Applies skip heuristics to filter out tests, utilities, I/O, plotting.
Outputs list of domain functions for extraction.

Usage:
    python 1_scan.py ~/repos/sortie --tool sortie
    python 1_scan.py ~/repos/apsim --tool apsim --lang python
"""

import argparse
import re
from pathlib import Path

# TODO:
# - [ ] Accept codebase path + tool name
# - [ ] Detect language from file extensions
# - [ ] Apply skip patterns (test, util, io, plot)
# - [ ] Output function list with file:line references
# - [ ] Create/update tools/{tool}.md
# - [ ] Count functions per file
# - [ ] Estimate extraction effort

SKIP_PATHS = ["test", "tests", "__test", "spec", "mock", "fixture", 
              "setup", "config", "util", "helper", "io", "plot", "viz"]

SKIP_FUNCS = ["test_", "_test", "print_", "plot_", "read_", "write_",
              "load_", "save_", "get_", "set_", "is_", "has_"]

EXTENSIONS = {
    "r": [".R", ".r"],
    "python": [".py"],
    "julia": [".jl"],
}


def should_skip_path(path: Path) -> bool:
    """Check if path should be skipped."""
    path_lower = str(path).lower()
    return any(skip in path_lower for skip in SKIP_PATHS)


def should_skip_func(name: str) -> bool:
    """Check if function should be skipped."""
    name_lower = name.lower()
    return any(name_lower.startswith(skip) for skip in SKIP_FUNCS)


def find_functions_r(code: str) -> list[tuple[str, int]]:
    """Find R function definitions."""
    pattern = re.compile(r'^(\w+)\s*(<-|=)\s*function\s*\(', re.MULTILINE)
    results = []
    for match in pattern.finditer(code):
        name = match.group(1)
        line = code[:match.start()].count('\n') + 1
        results.append((name, line))
    return results


def find_functions_python(code: str) -> list[tuple[str, int]]:
    """Find Python function definitions."""
    pattern = re.compile(r'^def\s+(\w+)\s*\(', re.MULTILINE)
    results = []
    for match in pattern.finditer(code):
        name = match.group(1)
        line = code[:match.start()].count('\n') + 1
        results.append((name, line))
    return results


def find_functions_julia(code: str) -> list[tuple[str, int]]:
    """Find Julia function definitions."""
    pattern = re.compile(r'^function\s+(\w+)\s*\(', re.MULTILINE)
    results = []
    for match in pattern.finditer(code):
        name = match.group(1)
        line = code[:match.start()].count('\n') + 1
        results.append((name, line))
    return results


def scan_codebase(codebase: Path, lang: str = None) -> dict[str, list]:
    """Scan codebase for functions."""
    results = {}
    
    # Determine extensions to search
    if lang:
        exts = EXTENSIONS.get(lang, [])
    else:
        exts = [e for exts in EXTENSIONS.values() for e in exts]
    
    for ext in exts:
        for filepath in codebase.rglob(f"*{ext}"):
            if should_skip_path(filepath):
                continue
            
            try:
                code = filepath.read_text(encoding="utf-8", errors="ignore")
            except:
                continue
            
            # Detect language and find functions
            if ext.lower() in [".r"]:
                funcs = find_functions_r(code)
            elif ext == ".py":
                funcs = find_functions_python(code)
            elif ext == ".jl":
                funcs = find_functions_julia(code)
            else:
                continue
            
            # Filter functions
            funcs = [(n, l) for n, l in funcs if not should_skip_func(n)]
            
            if funcs:
                rel_path = str(filepath.relative_to(codebase))
                results[rel_path] = funcs
    
    return results


def main():
    parser = argparse.ArgumentParser(description="Scan codebase for functions")
    parser.add_argument("codebase", type=Path, help="Path to codebase")
    parser.add_argument("--tool", required=True, help="Tool name")
    parser.add_argument("--lang", choices=["r", "python", "julia"], help="Language filter")
    parser.add_argument("--vault", type=Path, default=Path(".."), help="Vault path")
    
    args = parser.parse_args()
    
    print(f"\nScanning {args.codebase}...")
    results = scan_codebase(args.codebase, args.lang)
    
    total_funcs = sum(len(f) for f in results.values())
    print(f"\nFound {total_funcs} functions in {len(results)} files\n")
    
    for filepath, funcs in sorted(results.items()):
        print(f"{filepath}:")
        for name, line in funcs:
            print(f"  L{line}: {name}")
        print()
    
    # TODO: Create/update tools/{tool}.md
    tools_dir = args.vault / "tools"
    tools_dir.mkdir(parents=True, exist_ok=True)
    tool_file = tools_dir / f"{args.tool}.md"
    
    if not tool_file.exists():
        tool_file.write_text(f"""---
name: {args.tool}
url: 
language: {args.lang or 'mixed'}
scanned: true
---

## Scan Results

{total_funcs} functions in {len(results)} files

## Extractions

<!-- Add links as you extract -->

## Notes

""")
        print(f"Created {tool_file}")


if __name__ == "__main__":
    main()
