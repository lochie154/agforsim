#!/usr/bin/env python3
"""
Step 2 — Extract function metadata to component markdown.

Interactive extraction with human review. Shows the actual code and lets you
label inputs, outputs, and other metadata. Each component is saved immediately
as a checkpoint. Re-running skips already-extracted components.

Usage:
    python 2_extract.py from-scan ~/vault/08_Logs/scan_*.json  # Process scan results
    python 2_extract.py paste --vault ~/vault                   # Paste code interactively
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from _shared import (
    TOOLS_DIR, COMPONENTS_DIR, LOGS_DIR,
    resolve_vault, vault_subdir, ensure_tool_note, update_tool_note,
    detect_language, extract_functions, parse_frontmatter,
)


# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class Parameter:
    """A function input or output parameter."""
    name: str
    type: Optional[str] = None
    unit: Optional[str] = None
    description: Optional[str] = None

    def to_yaml(self, indent: int = 2) -> str:
        sp = " " * indent
        lines = [f"{sp}- name: {self.name}"]
        lines.append(f"{sp}  type: {self.type or 'null'}")
        lines.append(f"{sp}  unit: {self.unit or 'null'}")
        if self.description:
            lines.append(f'{sp}  description: "{self.description}"')
        return "\n".join(lines)


@dataclass
class Component:
    """Extracted function metadata."""
    name: str
    source_tool: str
    source_file: str
    source_lines: str
    source_language: str
    original_code: str
    inputs: list[Parameter] = field(default_factory=list)
    outputs: list[Parameter] = field(default_factory=list)
    pseudocode: str = ""
    notes: str = ""

    def to_markdown(self) -> str:
        """Generate Obsidian-compatible markdown."""
        lines = ["---"]
        lines.append(f"name: {self.name}")
        lines.append(f'source_tool: "[[{self.source_tool}]]"')
        lines.append(f"source_file: {self.source_file}")
        lines.append(f"source_lines: {self.source_lines}")
        lines.append(f"source_language: {self.source_language}")
        lines.append("validated: false")

        lines.append("inputs:")
        for p in self.inputs:
            lines.append(p.to_yaml())
        lines.append("outputs:")
        for p in self.outputs:
            lines.append(p.to_yaml())
        lines.append("---")
        lines.append("")
        lines.append(f"# {self.name}")
        lines.append("")
        lines.append("## Pseudocode")
        lines.append(self.pseudocode or "_TODO: describe algorithm_")
        lines.append("")
        lines.append("## Original Code")
        lines.append(f"```{self.source_language}")
        lines.append(self.original_code)
        lines.append("```")
        if self.notes:
            lines.append("")
            lines.append("## Notes")
            lines.append(self.notes)
        return "\n".join(lines)


# ── helpers ────────────────────────────────────────────────────────────────────

def _parse_params_from_code(params_raw: str) -> list[Parameter]:
    """Parse parameter string into Parameter objects."""
    if not params_raw.strip():
        return []
    params = []
    for part in re.split(r",\s*(?![^()]*\))", params_raw):
        part = part.strip()
        if not part or part == "self":
            continue
        name = re.split(r"[=:]", part)[0].strip()
        if name:
            params.append(Parameter(name=name))
    return params


def _get_existing_components(vault: Path) -> set[str]:
    """Get names of already-extracted components."""
    comp_dir = vault / COMPONENTS_DIR
    if not comp_dir.exists():
        return set()
    return {f.stem for f in comp_dir.glob("*.md") if f.name != "README.md"}


def write_component(vault: Path, comp: Component) -> Path:
    """Write component markdown to vault."""
    comp_dir = vault_subdir(vault, COMPONENTS_DIR)
    out_path = comp_dir / f"{comp.name}.md"
    out_path.write_text(comp.to_markdown(), encoding="utf-8")
    return out_path


# ── display helpers ────────────────────────────────────────────────────────────

def _display_code(code: str, language: str, max_lines: int = 50) -> None:
    """Display code with line numbers and syntax hint."""
    # Strip leading/trailing whitespace to avoid empty lines
    code = code.strip() if code else ""
    if not code:
        print(f"\n  ⚠ No code available\n")
        return

    lines = code.split("\n")
    print(f"\n{'─' * 70}")
    print(f"  CODE ({language}, {len(lines)} lines)")
    print(f"{'─' * 70}")

    line_width = 90  # Characters per display line
    for i, line in enumerate(lines[:max_lines], 1):
        # First chunk with line number
        if len(line) <= line_width:
            print(f"  {i:3}│ {line}")
        else:
            # Wrap long lines
            print(f"  {i:3}│ {line[:line_width]}")
            line_rest = line[line_width:]
            while line_rest:
                print(f"      │ {line_rest[:line_width]}")
                line_rest = line_rest[line_width:]

    if len(lines) > max_lines:
        print(f"  ... ({len(lines) - max_lines} more lines)")
    print(f"{'─' * 70}\n")


def _prompt_params(prompt: str, defaults: list[Parameter]) -> list[Parameter]:
    """Prompt user to edit parameter list."""
    default_str = ", ".join(p.name for p in defaults)
    print(f"  {prompt}")
    print(f"  Default: {default_str or '(none)'}")
    user_input = input("  Enter params (comma-separated, or press Enter for default): ").strip()

    if not user_input:
        return defaults

    return [Parameter(name=n.strip()) for n in user_input.split(",") if n.strip()]


def _prompt_single(prompt: str, default: str = "") -> str:
    """Prompt for a single value with default."""
    if default:
        user_input = input(f"  {prompt} [{default}]: ").strip()
        return user_input or default
    else:
        return input(f"  {prompt}: ").strip()


# ── interactive extraction ─────────────────────────────────────────────────────

def interactive_extract(
    func: dict,
    tool: str,
    filepath: str,
    language: str,
    vault: Path,
) -> Optional[Component]:
    """
    Interactive extraction of a single function.
    Shows code and prompts for inputs/outputs/metadata.
    Returns Component if extracted, None if skipped.
    """
    name = func.get("name", "unknown")
    code = func.get("code", func.get("code_preview", ""))
    params_raw = func.get("params_raw", "")
    start_line = func.get("start_line", "?")
    end_line = func.get("end_line", "?")

    # Show the function info
    print(f"\n{'=' * 70}")
    print(f"  FUNCTION: {name}")
    print(f"  File: {filepath} (lines {start_line}-{end_line})")
    print(f"{'=' * 70}")

    # Display the actual code
    _display_code(code, language)

    # Prompt for action
    print("  Options:")
    print("    [e] Extract with review")
    print("    [a] Auto-extract (use defaults)")
    print("    [s] Skip this function")
    print("    [q] Quit extraction")

    choice = input("\n  Choice [e/a/s/q]: ").strip().lower()

    if choice in ("s", "skip"):
        print("  → Skipped")
        return None
    elif choice in ("q", "quit"):
        raise KeyboardInterrupt("User quit")
    elif choice in ("a", "auto"):
        # Auto-extract with defaults
        inputs = _parse_params_from_code(params_raw)
        outputs = [Parameter(name="result")]
        pseudocode = ""
        notes = ""
    else:
        # Interactive review
        print(f"\n  {'─' * 50}")
        print("  REVIEW METADATA")
        print(f"  {'─' * 50}")

        # Inputs
        default_inputs = _parse_params_from_code(params_raw)
        inputs = _prompt_params("INPUTS:", default_inputs)

        # Outputs
        outputs = _prompt_params("OUTPUTS:", [Parameter(name="result")])

        # Pseudocode
        pseudocode = _prompt_single("Pseudocode (one-line description)", "")

        # Notes
        notes = _prompt_single("Notes (optional)", "")

    # Create component
    comp = Component(
        name=name,
        source_tool=tool,
        source_file=filepath,
        source_lines=f"{start_line}-{end_line}",
        source_language=language,
        original_code=code,
        inputs=inputs,
        outputs=outputs,
        pseudocode=pseudocode,
        notes=notes,
    )

    # Save immediately (checkpoint)
    out_path = write_component(vault, comp)
    tool_file = ensure_tool_note(vault, tool, language=language)
    update_tool_note(tool_file, name)

    print(f"\n  ✓ Saved: {out_path.name}")

    return comp


# ── from-scan mode ─────────────────────────────────────────────────────────────

def cmd_from_scan(scan_path: Path, vault: Path, auto: bool = False) -> int:
    """
    Extract functions from a scan JSON with interactive review.

    Only processes 'extract' verdict functions. 'human_review' functions
    are left for separate review via 'main.py review-pending'.

    Shows each function's code and prompts for inputs/outputs.
    Skips already-extracted components (resume support).
    """
    scan_data = json.loads(scan_path.read_text())
    tool = scan_data.get("tool", "unknown")
    codebase = scan_data.get("codebase", "")

    # Get functions to extract (only 'extract' verdict, not 'human_review')
    all_funcs = [f for f in scan_data.get("functions", [])
                 if f.get("verdict") == "extract"]

    # Count human_review for info
    review_count = sum(1 for f in scan_data.get("functions", [])
                       if f.get("verdict") == "human_review")

    if not all_funcs:
        if review_count > 0:
            print(f"  No auto-extract functions. {review_count} pending human review.")
            print(f"  Run: python main.py review-pending")
        else:
            print("  No functions to extract.")
        return 0

    # Check for already-extracted components
    existing = _get_existing_components(vault)
    remaining = [f for f in all_funcs if f.get("name") not in existing]
    skipped = len(all_funcs) - len(remaining)

    print(f"\n{'=' * 70}")
    print(f"  EXTRACTION: {tool}")
    print(f"{'=' * 70}")
    print(f"  Auto-extract functions: {len(all_funcs)}")
    print(f"  Already extracted: {skipped}")
    print(f"  Remaining: {len(remaining)}")
    if review_count > 0:
        print(f"  Pending human review: {review_count} (run 'main.py review-pending')")

    if not remaining:
        print("\n  All auto-extract functions done.")
        return 0

    if skipped > 0:
        print(f"\n  Resuming from checkpoint...")

    print(f"{'=' * 70}\n")

    extracted = 0

    try:
        for i, func in enumerate(remaining, 1):
            name = func.get("name", "unknown")
            filepath = func.get("filepath", "")
            language = func.get("language", "unknown")

            if auto:
                # Auto mode: extract with defaults
                code = func.get("code", func.get("code_preview", ""))
                params_raw = func.get("params_raw", "")

                comp = Component(
                    name=name,
                    source_tool=tool,
                    source_file=filepath,
                    source_lines=f"{func.get('start_line', '?')}-{func.get('end_line', '?')}",
                    source_language=language,
                    original_code=code,
                    inputs=_parse_params_from_code(params_raw),
                    outputs=[Parameter(name="result")],
                )

                out_path = write_component(vault, comp)
                tool_file = ensure_tool_note(vault, tool, language=language)
                update_tool_note(tool_file, name)
                extracted += 1
                print(f"    ✓ {out_path.name}")
            else:
                # Interactive mode
                comp = interactive_extract(func, tool, filepath, language, vault)
                if comp:
                    extracted += 1

    except KeyboardInterrupt:
        print(f"\n\n  Interrupted. Progress saved ({extracted} extracted this session).")
        print(f"  Re-run to continue from checkpoint.")
        return 0

    print(f"\n{'=' * 70}")
    print(f"  EXTRACTION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Extracted this session: {extracted}")
    print(f"  Total in vault: {len(_get_existing_components(vault))}")
    print(f"{'=' * 70}\n")

    return 0


# ── paste mode ─────────────────────────────────────────────────────────────────

def cmd_paste(vault: Path) -> int:
    """Paste code and extract interactively."""
    print("\nPaste your code (end with Ctrl+D or two empty lines):\n")
    lines = []
    empty_count = 0
    try:
        while True:
            line = input()
            if not line:
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
            lines.append(line)
    except EOFError:
        pass

    if not lines:
        print("No code provided.")
        return 1

    code = "\n".join(lines)

    # Detect language
    if "<-" in code or "function(" in code:
        language = "r"
    elif "def " in code:
        language = "python"
    elif "function " in code and "end" in code:
        language = "julia"
    else:
        language = input("Language (r/python/julia): ").strip().lower() or "unknown"

    # Display code
    _display_code(code, language)

    # Extract functions
    funcs = extract_functions(code, language)
    if not funcs:
        print("No functions detected. Creating single component.")
        name = input("Function name: ").strip() or "snippet"
        funcs = [{
            "name": name,
            "start_line": 1,
            "end_line": len(lines),
            "code": code,
            "params_raw": "",
        }]

    tool = input("Tool/source name: ").strip() or "manual"

    for func in funcs:
        comp = interactive_extract(func, tool, "pasted", language, vault)

    return 0


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract functions to Obsidian component notes with interactive review",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--vault", type=Path, default=None,
        help="Path to vault (defaults to ../)",
    )

    sub = parser.add_subparsers(dest="mode", help="Extraction mode")

    # from-scan mode
    p = sub.add_parser("from-scan", help="Extract from scan JSON (recommended)")
    p.add_argument("scan_path", type=Path, help="Path to scan JSON file")
    p.add_argument("--auto", action="store_true", help="Skip interactive review")

    # paste mode
    sub.add_parser("paste", help="Paste code interactively")

    args = parser.parse_args()
    vault = resolve_vault(args.vault)

    if args.mode == "from-scan":
        return cmd_from_scan(args.scan_path, vault, auto=args.auto)
    elif args.mode == "paste":
        return cmd_paste(vault)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
