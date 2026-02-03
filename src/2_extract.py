#!/usr/bin/env python3
"""
Extract function metadata to component markdown.

Usage:
    python 2_extract.py ~/repos/sortie --tool sortie --file src/allometry.R
    python 2_extract.py ~/repos/sortie --tool sortie --file src/allometry.R --func biomass_calc
    python 2_extract.py ~/repos/sortie --tool sortie --file src/allometry.R --auto
"""

import argparse
import re
from pathlib import Path

# TODO:
# - [ ] Parse function signature (inputs)
# - [ ] Detect return values (outputs)
# - [ ] Copy original code
# - [ ] Flag hardcoded constants
# - [ ] List internal dependencies
# - [ ] Write to components/{name}.md
# - [ ] Interactive mode for units/constraints
# - [ ] Batch mode with --auto flag
# - [ ] Update tools/{tool}.md with extraction link


def extract_function_r(code: str, func_name: str) -> dict | None:
    """Extract R function details."""
    pattern = re.compile(
        rf'^{func_name}\s*(<-|=)\s*function\s*\(([^)]*)\)',
        re.MULTILINE
    )
    match = pattern.search(code)
    if not match:
        return None
    
    start = match.start()
    start_line = code[:start].count('\n') + 1
    
    # Find function body (brace matching)
    brace_start = code.find('{', match.end())
    if brace_start == -1:
        return None
    
    depth = 1
    pos = brace_start + 1
    while depth > 0 and pos < len(code):
        if code[pos] == '{':
            depth += 1
        elif code[pos] == '}':
            depth -= 1
        pos += 1
    
    end_line = code[:pos].count('\n') + 1
    func_code = code[start:pos]
    
    # Parse parameters
    params_raw = match.group(2)
    params = []
    for p in params_raw.split(','):
        p = p.strip()
        if not p:
            continue
        if '=' in p:
            name = p.split('=')[0].strip()
        else:
            name = p
        params.append({"name": name, "type": None, "unit": None})
    
    return {
        "name": func_name,
        "start_line": start_line,
        "end_line": end_line,
        "code": func_code,
        "params": params,
    }


def detect_hardcoded_constants(code: str) -> bool:
    """Check for likely hardcoded constants."""
    nums = re.findall(r'(?<![a-zA-Z_])\d+\.?\d*(?![a-zA-Z_])', code)
    trivial = {'0', '1', '2', '0.0', '1.0', '2.0', '0.5'}
    significant = [n for n in nums if n not in trivial]
    return len(significant) > 2


def find_function_calls(code: str) -> list[str]:
    """Find function calls in code."""
    pattern = re.compile(r'(?<![a-zA-Z_])([a-zA-Z_][a-zA-Z0-9_]*)\s*\(')
    builtins = {'function', 'if', 'for', 'while', 'return', 'c', 'list', 
                'print', 'cat', 'paste', 'length', 'sum', 'mean'}
    calls = pattern.findall(code)
    return list(set(c for c in calls if c.lower() not in builtins))


def generate_component_md(func: dict, tool: str, filepath: str, lang: str) -> str:
    """Generate component markdown."""
    inputs_yaml = ""
    for p in func["params"]:
        inputs_yaml += f"""  - name: {p['name']}
    type: null
    unit: null
"""
    
    return f"""---
name: {func['name']}
source_tool: "[[tools/{tool}]]"
source_language: {lang}
source_file: {filepath}
source_lines: {func['start_line']}-{func['end_line']}

inputs:
{inputs_yaml}
outputs:
  - name: result
    type: null
    unit: null

internal_dependencies: {find_function_calls(func['code'])}
hardcoded_constants: {str(detect_hardcoded_constants(func['code'])).lower()}
mathematical_form: null
spatial_scale: null
temporal_scale: null
---

## Original Code

```{lang}
{func['code']}
```

## Pseudocode

```
# TODO: Write pseudocode
```

## Notes

<!-- Add observations, assumptions, gaps -->
"""


def main():
    parser = argparse.ArgumentParser(description="Extract function to component")
    parser.add_argument("codebase", type=Path)
    parser.add_argument("--tool", required=True)
    parser.add_argument("--file", required=True, help="Relative path to source file")
    parser.add_argument("--func", help="Specific function to extract")
    parser.add_argument("--auto", action="store_true", help="Skip interactive prompts")
    parser.add_argument("--vault", type=Path, default=Path(".."))
    
    args = parser.parse_args()
    
    filepath = args.codebase / args.file
    code = filepath.read_text(encoding="utf-8", errors="ignore")
    
    # Detect language
    ext = filepath.suffix.lower()
    lang = "r" if ext in [".r"] else "python" if ext == ".py" else "julia"
    
    # Find functions
    if lang == "r":
        pattern = re.compile(r'^(\w+)\s*(<-|=)\s*function\s*\(', re.MULTILINE)
    elif lang == "python":
        pattern = re.compile(r'^def\s+(\w+)\s*\(', re.MULTILINE)
    else:
        pattern = re.compile(r'^function\s+(\w+)\s*\(', re.MULTILINE)
    
    func_names = [m.group(1) for m in pattern.finditer(code)]
    
    if args.func:
        func_names = [n for n in func_names if n == args.func]
    
    components_dir = args.vault / "components"
    components_dir.mkdir(parents=True, exist_ok=True)
    
    for name in func_names:
        if not args.auto:
            resp = input(f"\nExtract {name}? [y/n/q]: ").strip().lower()
            if resp == 'q':
                break
            if resp != 'y':
                continue
        
        if lang == "r":
            func = extract_function_r(code, name)
        else:
            # TODO: Implement for other languages
            print(f"  Skipping {name} (language not fully supported)")
            continue
        
        if not func:
            print(f"  Could not extract {name}")
            continue
        
        md = generate_component_md(func, args.tool, args.file, lang)
        
        out_path = components_dir / f"{name}.md"
        if out_path.exists():
            out_path = components_dir / f"{name}_{args.tool}.md"
        
        out_path.write_text(md)
        print(f"  Wrote {out_path}")


if __name__ == "__main__":
    main()
