#!/usr/bin/env python3
"""
Shared utilities for the AGFORSIM extraction pipeline.

This module is the single source of truth for:
  - Vault directory constants
  - Path resolution helpers
  - YAML frontmatter parsing
  - Tool-note creation and updates
  - Language detection and function extraction

All numbered scripts import from here to avoid duplication.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Optional

# ── vault directory constants ──────────────────────────────────────────────

TOOLS_DIR = "01_Tools"
COMPONENTS_DIR = "02_Components"
SCENARIOS_DIR = "03_Scenarios"
ENSEMBLES_DIR = "04_Ensembles"
OUTPUT_DIR = "07_Output"
LOGS_DIR = "08_Logs"
INDEXES_DIR = "09_Indexes"
CONCEPTS_DIR = "10_Concepts"

# ── path helpers ───────────────────────────────────────────────────────────

def resolve_vault(cli_arg: Optional[Path] = None) -> Path:
    """Resolve the vault root path from a CLI argument or default to src/../."""
    if cli_arg is not None:
        return cli_arg.resolve()
    return Path(__file__).parent.parent.resolve()


def vault_subdir(vault: Path, which: str, create: bool = True) -> Path:
    """Return a vault subdirectory, creating it if requested."""
    d = vault / which
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


# ── frontmatter parsing ────────────────────────────────────────────────────

def parse_frontmatter(filepath: Path) -> Optional[dict]:
    """
    Extract YAML frontmatter from a markdown file.

    Returns None if the file doesn't start with '---' or has no closing '---'.
    """
    try:
        import yaml
    except ImportError:
        print("Warning: PyYAML not installed. Run: pip install pyyaml")
        return None

    try:
        content = filepath.read_text(encoding="utf-8")
        if not content.startswith("---"):
            return None
        end = content.find("\n---", 3)
        if end == -1:
            return None
        return yaml.safe_load(content[3:end])
    except Exception as e:
        print(f"Warning: could not parse {filepath}: {e}")
        return None


# ── tool-note management ───────────────────────────────────────────────────

def ensure_tool_note(
    vault: Path,
    tool_name: str,
    language: str = "",
    url: str = "",
) -> Path:
    """
    Create a tool note in the vault if it doesn't already exist.

    Returns the path to the tool note.
    """
    tools_dir = vault_subdir(vault, TOOLS_DIR)
    tool_file = tools_dir / f"{tool_name}.md"

    if not tool_file.exists():
        tool_file.write_text(f"""---
type: tool
short_id: {tool_name}
language: {language}
url: {url}
license:
accessed:
status: scanned
---

## Extractions

<!-- Links to extracted components will be added here -->

## Notes

<!-- Observations about this codebase -->
""")
        print(f"  Created tool note: {tool_file.name}")

    return tool_file


def update_tool_note(tool_file: Path, component_name: str) -> None:
    """Append a component wikilink to the tool note's Extractions section."""
    content = tool_file.read_text()
    link = f"- [[{component_name}]]"
    if link not in content:
        content = content.replace(
            "## Extractions\n",
            f"## Extractions\n\n{link}\n",
        )
        tool_file.write_text(content)


# ── secure zip extraction ──────────────────────────────────────────────────

class ZipSecurityError(Exception):
    """Raised when a zip file fails security checks."""
    pass


def safe_extract_zip(
    zip_path: Path,
    target_dir: Path,
    max_files: int = 10000,
    max_total_size: int = 500 * 1024 * 1024,  # 500 MB
    max_ratio: int = 100,  # compression ratio limit (zip bomb defense)
) -> list[Path]:
    """
    Securely extract a zip file with multiple safety checks.

    Security measures:
    - Path traversal prevention (no ../ escapes)
    - Zip bomb detection (compression ratio limit)
    - File count limit
    - Total extracted size limit
    - No symlink extraction

    Args:
        zip_path: Path to the zip file
        target_dir: Directory to extract into
        max_files: Maximum number of files allowed
        max_total_size: Maximum total extracted size in bytes
        max_ratio: Maximum compression ratio (uncompressed/compressed)

    Returns:
        List of extracted file paths

    Raises:
        ZipSecurityError: If any security check fails
    """
    zip_path = Path(zip_path).resolve()
    target_dir = Path(target_dir).resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    extracted_files: list[Path] = []

    with zipfile.ZipFile(zip_path, 'r') as zf:
        members = zf.infolist()

        # Check file count
        if len(members) > max_files:
            raise ZipSecurityError(
                f"Zip contains {len(members)} files (max {max_files})"
            )

        # Calculate totals and check for suspicious patterns
        total_uncompressed = 0
        total_compressed = sum(m.compress_size for m in members)

        for member in members:
            # Check for path traversal
            member_path = Path(member.filename)
            if member_path.is_absolute():
                raise ZipSecurityError(
                    f"Absolute path in zip: {member.filename}"
                )
            if ".." in member_path.parts:
                raise ZipSecurityError(
                    f"Path traversal detected: {member.filename}"
                )

            # Resolve and verify target stays within target_dir
            final_path = (target_dir / member.filename).resolve()
            if not str(final_path).startswith(str(target_dir)):
                raise ZipSecurityError(
                    f"Path escape detected: {member.filename}"
                )

            # Skip symlinks
            if member.is_dir():
                continue

            # Check for symlinks (external_attr encodes file type on Unix)
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:  # symlink
                print(f"  Warning: Skipping symlink {member.filename}")
                continue

            total_uncompressed += member.file_size

        # Check total size
        if total_uncompressed > max_total_size:
            raise ZipSecurityError(
                f"Total uncompressed size {total_uncompressed / 1024 / 1024:.1f} MB "
                f"exceeds limit of {max_total_size / 1024 / 1024:.1f} MB"
            )

        # Check compression ratio (zip bomb defense)
        if total_compressed > 0:
            ratio = total_uncompressed / total_compressed
            if ratio > max_ratio:
                raise ZipSecurityError(
                    f"Suspicious compression ratio {ratio:.1f}:1 (max {max_ratio}:1). "
                    f"Possible zip bomb."
                )

        # Actually extract (after all checks pass)
        for member in members:
            if member.is_dir():
                continue

            # Re-check symlink
            unix_mode = (member.external_attr >> 16) & 0o170000
            if unix_mode == 0o120000:
                continue

            final_path = (target_dir / member.filename).resolve()
            final_path.parent.mkdir(parents=True, exist_ok=True)

            with zf.open(member) as src, open(final_path, 'wb') as dst:
                dst.write(src.read())

            extracted_files.append(final_path)

    return extracted_files


def find_and_extract_zips(
    root_dir: Path,
    remove_after: bool = False,
) -> dict[Path, list[Path]]:
    """
    Find all zip files in a directory tree and extract them safely.

    Each zip is extracted into a directory with the same name (minus .zip).

    Args:
        root_dir: Directory to search for zip files
        remove_after: If True, delete zip files after successful extraction

    Returns:
        Dict mapping zip paths to lists of extracted files
    """
    root_dir = Path(root_dir).resolve()
    results: dict[Path, list[Path]] = {}

    for zip_path in root_dir.rglob("*.zip"):
        extract_dir = zip_path.with_suffix("")  # foo.zip -> foo/

        try:
            print(f"  Extracting: {zip_path.name}")
            files = safe_extract_zip(zip_path, extract_dir)
            results[zip_path] = files
            print(f"    → {len(files)} files extracted to {extract_dir.name}/")

            if remove_after:
                zip_path.unlink()
                print(f"    → Removed {zip_path.name}")

        except ZipSecurityError as e:
            print(f"  ⚠ SECURITY: Skipping {zip_path.name}: {e}")
            results[zip_path] = []

        except zipfile.BadZipFile:
            print(f"  ⚠ Corrupt zip: {zip_path.name}")
            results[zip_path] = []

    return results


# ── language detection ─────────────────────────────────────────────────────

_EXT_MAP = {
    # R
    ".r": "r", ".R": "r",
    # Python / Jupyter
    ".py": "python",
    ".ipynb": "jupyter",
    # Julia
    ".jl": "julia",
    # Fortran (all variants)
    ".f90": "fortran", ".f": "fortran", ".F90": "fortran",
    ".f95": "fortran", ".F95": "fortran",
    ".f77": "fortran", ".F77": "fortran",
    ".for": "fortran", ".FOR": "fortran",
    # C / C++
    ".c": "c", ".h": "c",
    ".cpp": "cpp", ".C": "cpp", ".H": "cpp", ".hpp": "cpp", ".cxx": "cpp",
    # Java
    ".java": "java",
    # MATLAB
    ".m": "matlab", ".mat": "matlab",
    # TypeScript / JavaScript
    ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript",
    # NetLogo
    ".nlogo": "netlogo",
}

LANG_EXTENSIONS: dict[str, list[str]] = {
    "r":          [".R", ".r"],
    "python":     [".py"],
    "jupyter":    [".ipynb"],
    "julia":      [".jl"],
    "fortran":    [".f90", ".f", ".F90", ".f95", ".F95", ".f77", ".F77", ".for", ".FOR"],
    "c":          [".c", ".h"],
    "cpp":        [".cpp", ".C", ".H", ".hpp", ".cxx"],
    "java":       [".java"],
    "matlab":     [".m"],
    "typescript": [".ts", ".tsx"],
    "javascript": [".js", ".jsx"],
    "netlogo":    [".nlogo"],
}


def detect_language(filepath: str) -> str:
    """Map a file extension to a language label."""
    return _EXT_MAP.get(Path(filepath).suffix, "unknown")


# ── function extractors ────────────────────────────────────────────────────

def _extract_r(code: str) -> list[dict]:
    """Extract R function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")
    pattern = re.compile(
        r"^(\s*)(\w+)\s*(<-|=)\s*function\s*\((.*?)\)", re.MULTILINE,
    )
    for match in pattern.finditer(code):
        name = match.group(2)
        start = code[: match.start()].count("\n") + 1
        brace_count = 0
        in_func = False
        end = start
        for i, line in enumerate(lines[start - 1:], start=start):
            brace_count += line.count("{") - line.count("}")
            if "{" in line:
                in_func = True
            if in_func and brace_count == 0:
                end = i
                break
        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": match.group(4),
        })
    return functions


def _extract_python(code: str) -> list[dict]:
    """Extract Python function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")
    pattern = re.compile(r"^(\s*)def\s+(\w+)\s*\((.*?)\).*?:", re.MULTILINE)
    for match in pattern.finditer(code):
        indent = len(match.group(1))
        name = match.group(2)
        start = code[: match.start()].count("\n") + 1
        end = start
        for i, line in enumerate(lines[start:], start=start + 1):
            if not line.strip():
                continue
            if (len(line) - len(line.lstrip())) <= indent and line.strip():
                end = i - 1
                break
            end = i
        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": match.group(3),
        })
    return functions


def _extract_julia(code: str) -> list[dict]:
    """Extract Julia function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")
    pattern = re.compile(r"^function\s+(\w+)\s*\((.*?)\)", re.MULTILINE)
    for match in pattern.finditer(code):
        name = match.group(1)
        start = code[: match.start()].count("\n") + 1
        end = start
        for i, line in enumerate(lines[start:], start=start + 1):
            if line.strip() == "end":
                end = i
                break
        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": match.group(2),
        })
    return functions


def _extract_fortran(code: str) -> list[dict]:
    """Extract Fortran subroutine and function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")

    # Match: subroutine name(args) or function name(args)
    # Fortran is case-insensitive
    pattern = re.compile(
        r"^\s*(?:pure\s+|elemental\s+|recursive\s+)*"
        r"(subroutine|function)\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE | re.IGNORECASE,
    )

    for match in pattern.finditer(code):
        kind = match.group(1).lower()  # 'subroutine' or 'function'
        name = match.group(2)
        params = match.group(3)
        start = code[: match.start()].count("\n") + 1

        # Find matching 'end subroutine' or 'end function' or just 'end'
        end = start
        end_pattern = re.compile(
            rf"^\s*end\s*(?:{kind})?(?:\s+{name})?\s*$",
            re.IGNORECASE,
        )
        for i, line in enumerate(lines[start:], start=start + 1):
            if end_pattern.match(line):
                end = i
                break

        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": params,
        })

    return functions


def _extract_java(code: str) -> list[dict]:
    """Extract Java method definitions (public, private, protected, static, etc.)."""
    functions: list[dict] = []
    lines = code.split("\n")

    # Match method declarations (not constructors - those have same name as class)
    # Handles: public static void main(...), private int calculate(...), etc.
    pattern = re.compile(
        r"^\s*((?:public|private|protected)\s+)?(?:static\s+)?(?:final\s+)?"
        r"(?:synchronized\s+)?(?:native\s+)?(?:abstract\s+)?"
        r"(\w+(?:<[^>]+>)?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
        re.MULTILINE,
    )

    for match in pattern.finditer(code):
        return_type = match.group(2)
        name = match.group(3)
        params = match.group(4)
        start = code[: match.start()].count("\n") + 1

        # Find matching closing brace (track brace depth)
        brace_count = 0
        end = start
        in_method = False
        for i, line in enumerate(lines[start - 1:], start=start):
            brace_count += line.count("{") - line.count("}")
            if "{" in line:
                in_method = True
            if in_method and brace_count == 0:
                end = i
                break

        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": params,
        })

    return functions


def _extract_matlab(code: str) -> list[dict]:
    """Extract MATLAB function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")

    # Match: function [out1, out2] = name(args) or function out = name(args) or function name(args)
    pattern = re.compile(
        r"^\s*function\s+(?:\[?[\w,\s]*\]?\s*=\s*)?(\w+)\s*\(([^)]*)\)",
        re.MULTILINE,
    )

    for match in pattern.finditer(code):
        name = match.group(1)
        params = match.group(2)
        start = code[: match.start()].count("\n") + 1

        # Find 'end' that closes this function
        # MATLAB uses 'end' for functions (in newer MATLAB, or always for nested functions)
        end = start
        depth = 1
        for i, line in enumerate(lines[start:], start=start + 1):
            stripped = line.strip().lower()
            # Count block starters
            if re.match(r'^(function|if|for|while|switch|try|parfor|spmd)\b', stripped):
                depth += 1
            # Count 'end' keywords
            if stripped == 'end' or stripped.startswith('end ') or stripped.startswith('end;'):
                depth -= 1
                if depth == 0:
                    end = i
                    break

        # If no 'end' found, go to next function or end of file
        if end == start:
            next_func = pattern.search(code, match.end())
            if next_func:
                end = code[: next_func.start()].count("\n")
            else:
                end = len(lines)

        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": params,
        })

    return functions


def _extract_typescript(code: str) -> list[dict]:
    """Extract TypeScript/JavaScript function definitions (including arrow functions)."""
    functions: list[dict] = []
    lines = code.split("\n")

    # Pattern 1: Regular function declarations
    # function name(...) { or export function name(...) {
    pattern1 = re.compile(
        r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)",
        re.MULTILINE,
    )

    # Pattern 2: Arrow functions assigned to const/let/var
    # const name = (...) => { or const name = async (...) => {
    pattern2 = re.compile(
        r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*(?::\s*[^=]+)?\s*=>",
        re.MULTILINE,
    )

    # Pattern 3: Class methods
    # methodName(...) { or async methodName(...) {
    pattern3 = re.compile(
        r"^\s*(?:public|private|protected|static|async|readonly|\s)*(\w+)\s*\(([^)]*)\)\s*(?::\s*[^{]+)?\s*\{",
        re.MULTILINE,
    )

    for match in pattern1.finditer(code):
        name = match.group(1)
        params = match.group(2)
        start = code[: match.start()].count("\n") + 1
        end = _find_brace_end(lines, start)
        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": params,
        })

    for match in pattern2.finditer(code):
        name = match.group(1)
        start = code[: match.start()].count("\n") + 1
        end = _find_brace_end(lines, start)
        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": "",
        })

    return functions


def _extract_c(code: str) -> list[dict]:
    """Extract C function definitions."""
    functions: list[dict] = []
    lines = code.split("\n")

    # Match: type name(args) { -- but not if preceded by common keywords that indicate declaration
    # Handles: int main(...), static void helper(...), etc.
    pattern = re.compile(
        r"^\s*(?:static\s+|inline\s+|extern\s+)*"
        r"(?:unsigned\s+|signed\s+|const\s+)*"
        r"(\w+(?:\s*\*)*)\s+(\w+)\s*\(([^)]*)\)\s*\{",
        re.MULTILINE,
    )

    for match in pattern.finditer(code):
        name = match.group(2)
        params = match.group(3)
        start = code[: match.start()].count("\n") + 1
        end = _find_brace_end(lines, start)

        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": params,
        })

    return functions


def _extract_netlogo(code: str) -> list[dict]:
    """Extract NetLogo procedure definitions (to ... end)."""
    functions: list[dict] = []
    lines = code.split("\n")

    # NetLogo procedures: to procedure-name or to-report procedure-name
    pattern = re.compile(
        r"^\s*(to-report|to)\s+([\w-]+)",
        re.MULTILINE | re.IGNORECASE,
    )

    for match in pattern.finditer(code):
        kind = match.group(1).lower()
        name = match.group(2)
        start = code[: match.start()].count("\n") + 1

        # Find 'end' keyword
        end = start
        for i, line in enumerate(lines[start:], start=start + 1):
            if line.strip().lower() == 'end':
                end = i
                break

        functions.append({
            "name": name,
            "start_line": start,
            "end_line": end,
            "code": "\n".join(lines[start - 1: end]),
            "params_raw": "",
            "kind": kind,  # 'to' or 'to-report'
        })

    return functions


def _extract_jupyter(code: str) -> list[dict]:
    """
    Extract functions from Jupyter notebook (.ipynb) JSON format.
    Parses the notebook JSON and extracts Python functions from code cells.
    """
    import json

    functions: list[dict] = []

    try:
        notebook = json.loads(code)
    except json.JSONDecodeError:
        return []

    cells = notebook.get("cells", [])

    for cell_idx, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", [])
        if isinstance(source, list):
            cell_code = "".join(source)
        else:
            cell_code = source

        # Extract Python functions from this cell
        cell_funcs = _extract_python(cell_code)

        # Adjust metadata to indicate cell number
        for func in cell_funcs:
            func["cell_index"] = cell_idx
            func["name"] = func["name"]  # Keep original name
            functions.append(func)

    return functions


def _find_brace_end(lines: list[str], start: int) -> int:
    """Helper: find the line where braces balance to zero."""
    brace_count = 0
    in_func = False
    for i, line in enumerate(lines[start - 1:], start=start):
        brace_count += line.count("{") - line.count("}")
        if "{" in line:
            in_func = True
        if in_func and brace_count == 0:
            return i
    return len(lines)


_EXTRACTORS = {
    "r": _extract_r,
    "python": _extract_python,
    "julia": _extract_julia,
    "fortran": _extract_fortran,
    "java": _extract_java,
    "matlab": _extract_matlab,
    "typescript": _extract_typescript,
    "javascript": _extract_typescript,  # Same syntax
    "c": _extract_c,
    "cpp": _extract_c,  # C++ uses same basic pattern
    "netlogo": _extract_netlogo,
    "jupyter": _extract_jupyter,
}


def extract_functions(code: str, language: str) -> list[dict]:
    """Route to the appropriate per-language extractor."""
    fn = _EXTRACTORS.get(language)
    return fn(code) if fn else []


# ── module self-test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    print("_shared.py loaded successfully.")
    print(f"  TOOLS_DIR = {TOOLS_DIR}")
    print(f"  COMPONENTS_DIR = {COMPONENTS_DIR}")
    print(f"  LOGS_DIR = {LOGS_DIR}")

    # Language detection tests
    test_files = [
        ("test.R", "r"), ("test.py", "python"), ("test.jl", "julia"),
        ("test.f90", "fortran"), ("test.f95", "fortran"),
        ("test.java", "java"), ("test.m", "matlab"),
        ("test.ts", "typescript"), ("test.nlogo", "netlogo"),
        ("test.c", "c"), ("test.h", "c"), ("test.C", "cpp"),
        ("test.ipynb", "jupyter"),
    ]
    print("\n  Language detection:")
    for fname, expected in test_files:
        detected = detect_language(fname)
        status = "✓" if detected == expected else f"✗ (got {detected})"
        print(f"    {fname} → {expected} {status}")

    # Quick extractor tests
    print("\n  Function extraction:")

    r_code = "biomass <- function(dbh, h) {\n  pi * dbh^2 * h\n}"
    funcs = extract_functions(r_code, "r")
    print(f"    R:          {[f['name'] for f in funcs]}")

    py_code = "def growth(x, y):\n    return x * y\n"
    funcs = extract_functions(py_code, "python")
    print(f"    Python:     {[f['name'] for f in funcs]}")

    java_code = "public static void main(String[] args) {\n    System.out.println(\"Hello\");\n}"
    funcs = extract_functions(java_code, "java")
    print(f"    Java:       {[f['name'] for f in funcs]}")

    matlab_code = "function [y] = square(x)\n    y = x^2;\nend"
    funcs = extract_functions(matlab_code, "matlab")
    print(f"    MATLAB:     {[f['name'] for f in funcs]}")

    ts_code = "function calculate(a: number, b: number): number {\n    return a + b;\n}"
    funcs = extract_functions(ts_code, "typescript")
    print(f"    TypeScript: {[f['name'] for f in funcs]}")

    nlogo_code = "to setup\n    clear-all\n    reset-ticks\nend"
    funcs = extract_functions(nlogo_code, "netlogo")
    print(f"    NetLogo:    {[f['name'] for f in funcs]}")

    fortran_code = "subroutine calc_growth(dbh, height, volume)\n    real :: dbh, height, volume\n    volume = dbh * height\nend subroutine"
    funcs = extract_functions(fortran_code, "fortran")
    print(f"    Fortran:    {[f['name'] for f in funcs]}")

    c_code = "int add(int a, int b) {\n    return a + b;\n}"
    funcs = extract_functions(c_code, "c")
    print(f"    C:          {[f['name'] for f in funcs]}")

    print("\nAll checks passed.")
