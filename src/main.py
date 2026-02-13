#!/usr/bin/env python3
"""
AGFORSIM Workflow Orchestrator

Drives the full extraction → implementation → ensemble pipeline by
calling each numbered script in sequence. Tracks persistent state
(current focus, completed scans, extraction counts) so you can pick
up where you left off between sessions.

Usage:
    python main.py                        # show status + suggest next
    python main.py status                 # detailed progress report
    python main.py focus biomass          # set / change current focus
    python main.py next                   # suggest next step

    # Batch processing (recommended for multiple codebases)
    python main.py batch codebases.txt    # process multiple codebases
    python main.py review                 # interactive review workflow

    # Individual pipeline stages
    python main.py scan   ~/repos/sortie --tool sortie
    python main.py extract ~/repos/sortie --tool sortie --file src/growth.R
    python main.py extract --from-scan    # extract from most recent scan
    python main.py track                  # status / inputs / outputs / clusters / gaps
    python main.py reconcile              # suggest aliases
    python main.py implement              # generate stubs for all components
    python main.py report results.json    # generate analysis report

    # Full automated pipeline for one codebase
    python main.py run ~/repos/sortie --tool sortie
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from _shared import (
    TOOLS_DIR,
    COMPONENTS_DIR,
    CONCEPTS_DIR,
    LOGS_DIR,
    OUTPUT_DIR,
    resolve_vault,
)


# ── paths ─────────────────────────────────────────────────────────────────────

SRC_DIR = Path(__file__).parent.resolve()
VAULT_DEFAULT = SRC_DIR.parent


def _state_file(vault: Path) -> Path:
    return vault / LOGS_DIR / "workflow_state.json"


# ── state persistence ─────────────────────────────────────────────────────────

def _default_state() -> dict:
    return {
        "current_focus": None,  # Fixed: was `biomass` (unquoted)
        "completed_focuses": [],
        "scans": [],             # [{tool, codebase, timestamp, scan_file}, ...]
        "extractions": [],       # [{tool, file, mode, timestamp, count}, ...]
        "components_extracted": 0,
        "last_step": None,       # e.g. "scan", "extract", "track", ...
    }


def load_state(vault: Path) -> dict:
    """Load workflow state from disk, creating defaults if missing."""
    state_file = _state_file(vault)
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            # Back-fill any missing keys from defaults
            for k, v in _default_state().items():
                state.setdefault(k, v)
            return state
        except (json.JSONDecodeError, KeyError):
            pass
    return _default_state()


def save_state(vault: Path, state: dict) -> None:
    """Persist workflow state."""
    state_file = _state_file(vault)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(state, indent=2, default=str))


# ── helper: run a sibling script ──────────────────────────────────────────────

def _run_script(script: str, args: list[str]) -> int:
    """Run a sibling script as a subprocess, inheriting stdin/stdout/stderr."""
    script_path = SRC_DIR / script
    cmd = [sys.executable, str(script_path)] + args
    print(f"\n{'─' * 60}")
    print(f"  Running: {' '.join(cmd)}")
    print(f"{'─' * 60}\n")
    result = subprocess.run(cmd)
    return result.returncode


def _count_vault_files(vault: Path, subdir: str, exclude_readme: bool = True) -> int:
    """Count markdown files in a vault subdirectory."""
    d = vault / subdir
    if not d.exists():
        return 0
    count = len(list(d.rglob("*.md")))
    if exclude_readme and (d / "README.md").exists():
        count -= 1
    return count


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_status(vault: Path) -> None:
    """Print a detailed progress report."""
    state = load_state(vault)

    print(f"\n{'=' * 60}")
    print("  AGFORSIM WORKFLOW STATUS")
    print(f"{'=' * 60}")

    focus = state.get("current_focus")
    print(f"\n  Current focus:       {focus or '(none — set one with: main.py focus <name>)'}")
    print(f"  Completed focuses:   {', '.join(state['completed_focuses']) or '(none)'}")
    print(f"  Components extracted: {state['components_extracted']}")
    print(f"  Last step completed: {state.get('last_step') or '(none)'}")

    # Count actual vault artefacts
    n_components = _count_vault_files(vault, COMPONENTS_DIR)
    n_tools = _count_vault_files(vault, TOOLS_DIR)

    print(f"\n  Vault artefacts:")
    print(f"    Tool notes:        {n_tools}")
    print(f"    Component notes:   {n_components}")

    # Recent scans
    scans = state.get("scans", [])
    if scans:
        print(f"\n  Recent scans ({len(scans)} total):")
        for s in scans[-5:]:
            print(f"    {s.get('timestamp', '?')[:19]}  {s.get('tool', '?')}  "
                  f"({s.get('codebase', '?')})")

    # Recent extractions
    extractions = state.get("extractions", [])
    if extractions:
        print(f"\n  Recent extractions ({len(extractions)} total):")
        for e in extractions[-5:]:
            print(f"    {e.get('timestamp', '?')[:19]}  {e.get('tool', '?')}  "
                  f"{e.get('file', '?')}  ({e.get('count', 0)} functions)")

    print(f"\n{'=' * 60}\n")


def cmd_focus(vault: Path, name: str) -> None:
    """Set or change the current research focus."""
    state = load_state(vault)
    old = state.get("current_focus")
    state["current_focus"] = name
    save_state(vault, state)

    if old and old != name:
        print(f"\n  Focus changed: {old} → {name}")
    else:
        print(f"\n  Focus set to: {name}")

    print(f"\n  Next steps for '{name}':")
    print(f"    1. Create codebases.txt with paths to relevant codebases")
    print(f"    2. Run: python main.py batch codebases.txt")
    print(f"    3. Or single codebase: python main.py run <codebase> --tool <name>\n")


def cmd_next(vault: Path) -> None:
    """Suggest the most useful next action based on current state."""
    state = load_state(vault)
    actual_comps = _count_vault_files(vault, COMPONENTS_DIR)
    scans = state.get("scans", [])

    print(f"\n{'─' * 60}")
    print("  SUGGESTED NEXT STEP")
    print(f"{'─' * 60}")

    if not scans:
        print("\n  → No codebases scanned yet.")
        print("    Create a file with GitHub URLs (one per line) and run:")
        print("    python main.py batch repos.txt")
        print("\n  Or for a single codebase:")
        print("    python main.py run ~/repos/<codebase> --tool <name>\n")
    elif actual_comps < 5:
        print(f"\n  → {actual_comps} component(s) extracted. Need ≥5 for meaningful analysis.")
        print("    Continue with: python main.py batch repos.txt")
        print("    Or review:     python main.py review\n")
    else:
        print(f"\n  → {actual_comps} components extracted — ready for analysis!")
        print("    1. Review:    python main.py review")
        print("    2. Implement: python main.py implement")
        print("    3. Track:     python main.py track\n")

    print(f"{'─' * 60}\n")


def cmd_done(vault: Path) -> None:
    """Mark the current focus as completed and prompt for the next one."""
    state = load_state(vault)
    focus = state.get("current_focus")
    if not focus:
        print("\n  No focus is set — nothing to complete.\n")
        return

    state["completed_focuses"].append(focus)
    state["current_focus"] = None
    state["last_step"] = "done"
    save_state(vault, state)

    print(f"\n  ✓ Focus '{focus}' marked as completed.")
    print(f"  Completed focuses so far: {', '.join(state['completed_focuses'])}")
    print(f"\n  Set your next focus with: python main.py focus <name>\n")


# ── scan ──────────────────────────────────────────────────────────────────────

def cmd_scan(
    codebase: Path,
    tool: str,
    vault: Path,
    lang: Optional[str] = None,
    include: list[str] | None = None,
    exclude: list[str] | None = None,
    auto: bool = False,
) -> int:
    """Run 1_scan.py and record the result."""
    args = [str(codebase), "--tool", tool, "--vault", str(vault)]
    if lang:
        args += ["--lang", lang]
    if auto:
        args.append("--auto")
    if include:
        args += ["--include"] + include
    if exclude:
        args += ["--exclude"] + exclude

    rc = _run_script("1_scan.py", args)

    if rc == 0:
        state = load_state(vault)
        state["scans"].append({
            "tool": tool,
            "codebase": str(codebase),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lang": lang,
        })
        state["last_step"] = "scan"
        save_state(vault, state)

    return rc


# ── extract ───────────────────────────────────────────────────────────────────

def cmd_extract(
    vault: Path,
    codebase: Optional[Path] = None,
    tool: Optional[str] = None,
    filepath: Optional[str] = None,
    func: Optional[str] = None,
    auto: bool = False,
    mode: str = "batch",
    from_scan: bool = False,
    scan_path: Optional[Path] = None,
) -> int:
    """Run 2_extract.py in the requested mode and record the result."""
    if from_scan:
        # Use provided scan_path or find most recent
        if scan_path:
            target_scan = scan_path
        else:
            logs_dir = vault / LOGS_DIR
            scan_files = sorted(logs_dir.glob("scan_*.json"), reverse=True)
            if not scan_files:
                print("No scan files found. Run 'main.py scan' first.")
                return 1
            target_scan = scan_files[0]

        args = ["from-scan", str(target_scan), "--vault", str(vault)]
        if auto:
            args.append("--auto")
        return _run_script("2_extract.py", args)

    if mode == "paste":
        return _run_script("2_extract.py", ["paste", "--vault", str(vault)])

    if mode == "quick":
        return _run_script("2_extract.py", ["quick", "--vault", str(vault)])

    if mode == "interactive":
        if not all([codebase, tool, filepath, func]):
            print("Error: interactive mode requires codebase, --tool, --file, and --func")
            return 1
        args = [
            "interactive", str(codebase),
            "--tool", tool,
            "--file", filepath,
            "--func", func,
            "--vault", str(vault),
        ]
        rc = _run_script("2_extract.py", args)
        if rc == 0:
            _record_extraction(vault, tool, filepath, "interactive", 1)
        return rc

    # batch (default)
    if not all([codebase, tool, filepath]):
        print("Error: batch mode requires codebase, --tool, and --file")
        return 1

    args = [
        "batch", str(codebase),
        "--tool", tool,
        "--file", filepath,
        "--vault", str(vault),
    ]
    if auto:
        args.append("--auto")

    rc = _run_script("2_extract.py", args)
    if rc == 0:
        _record_extraction(vault, tool, filepath, "batch" + (" --auto" if auto else ""), 0)
    return rc


def _record_extraction(
    vault: Path, tool: str, filepath: str, mode: str, count: int,
) -> None:
    state = load_state(vault)
    state["extractions"].append({
        "tool": tool,
        "file": filepath,
        "mode": mode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": count,
    })
    state["components_extracted"] += max(count, 1)
    state["last_step"] = "extract"
    save_state(vault, state)


# ── track ─────────────────────────────────────────────────────────────────────

def cmd_track(vault: Path, sub: str = "status") -> int:
    """Run 3_track.py with the given sub-command."""
    return _run_script("3_track.py", [sub, "--vault", str(vault)])


# ── reconcile ─────────────────────────────────────────────────────────────────

def cmd_reconcile(vault: Path, sub_args: list[str] | None = None) -> int:
    """Run 4_reconcile.py."""
    args = (sub_args or ["suggest"]) + ["--vault", str(vault)]
    return _run_script("4_reconcile.py", args)


# ── implement ─────────────────────────────────────────────────────────────────

def cmd_implement(vault: Path, name: Optional[str] = None, status: bool = False) -> int:
    """Run 5_implement.py."""
    if status:
        return _run_script("5_implement.py", ["--status"])
    args = ["--vault", str(vault)]
    if name:
        args.insert(0, name)
    else:
        args.append("--all")
    return _run_script("5_implement.py", args)


# ── report ────────────────────────────────────────────────────────────────────

def cmd_report(
    results: Path,
    vault: Path,
    output: Optional[Path] = None,
    plot: bool = False,
) -> int:
    """Run 8_report.py."""
    args = [str(results), "--vault", str(vault)]
    if output:
        args += ["--output", str(output)]
    if plot:
        args.append("--plot")

    rc = _run_script("8_report.py", args)
    if rc == 0:
        state = load_state(vault)
        state["last_step"] = "report"
        save_state(vault, state)
    return rc


# ── batch ─────────────────────────────────────────────────────────────────────

def _parse_github_url(url: str) -> tuple[str, str]:
    """
    Parse a GitHub URL to extract owner/repo and derive a tool name.

    Returns: (repo_name, tool_name)
    """
    import re
    # Match github.com/owner/repo or github.com/owner/repo.git
    m = re.match(r'https?://github\.com/([^/]+)/([^/\s]+?)(?:\.git)?$', url.strip())
    if m:
        owner, repo = m.group(1), m.group(2)
        # Tool name: owner_repo (sanitized)
        tool = f"{owner}_{repo}".lower().replace("-", "_")
        return repo, tool
    return None, None


def _clone_repo(url: str, clone_dir: Path) -> Optional[Path]:
    """Clone a GitHub repo to a temporary directory."""
    repo_name, _ = _parse_github_url(url)
    if not repo_name:
        return None

    target = clone_dir / repo_name
    if target.exists():
        print(f"  Using existing clone: {target}")
        return target

    print(f"  Cloning {url}...")
    result = subprocess.run(
        ["git", "clone", "--depth", "1", url, str(target)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  ✗ Clone failed: {result.stderr}")
        return None

    return target


def cmd_batch(codebases_file: Path, vault: Path, auto: bool = False) -> int:
    """
    Process multiple codebases from a file.

    Two-phase workflow:
      Phase 1: Clone (if URL) and scan all codebases
      Phase 2: Interactive extraction across all scans

    Supported formats (one per line):
        https://github.com/owner/repo              # GitHub URL (auto-cloned)
        https://github.com/owner/repo  r           # GitHub URL with language hint
        /local/path  tool_name  [language]         # Local path with explicit tool name

    Lines starting with # are ignored.
    """
    if not codebases_file.exists():
        print(f"Codebases file not found: {codebases_file}")
        return 1

    lines = [l.strip() for l in codebases_file.read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]

    if not lines:
        print("No codebases found in file.")
        return 1

    # Create clone directory for GitHub repos
    clone_dir = vault / LOGS_DIR / "clones"
    clone_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'=' * 70}")
    print(f"  BATCH PROCESSING: {len(lines)} codebase(s)")
    print(f"{'=' * 70}")

    # ── Phase 1: Clone and Scan ───────────────────────────────────────────────
    print(f"\n  PHASE 1: Clone and scan all codebases")
    print(f"  {'─' * 60}\n")

    scan_files = []

    for i, line in enumerate(lines, 1):
        parts = line.split()
        first = parts[0]

        # Detect GitHub URL
        if first.startswith("https://github.com/") or first.startswith("http://github.com/"):
            repo_name, tool = _parse_github_url(first)
            if not tool:
                print(f"  [{i}/{len(lines)}] ✗ Invalid GitHub URL: {first}")
                continue

            # Clone the repo
            codebase = _clone_repo(first, clone_dir)
            if not codebase:
                print(f"  [{i}/{len(lines)}] ✗ Clone failed: {first}")
                continue

            # Language hint if provided
            lang = parts[1] if len(parts) > 1 else None

        # Local path format: <path> <tool> [<lang>]
        elif len(parts) >= 2:
            codebase = Path(parts[0])
            tool = parts[1]
            lang = parts[2] if len(parts) > 2 else None

            if not codebase.exists():
                print(f"  [{i}/{len(lines)}] ✗ Path not found: {codebase}")
                continue

        else:
            print(f"  [{i}/{len(lines)}] ✗ Invalid line: {line}")
            continue

        print(f"  [{i}/{len(lines)}] Scanning {tool}...")

        # Run scan (always with auto=True to just build the JSON)
        rc = cmd_scan(codebase, tool, vault, lang=lang, auto=True)

        if rc == 0:
            # Find the scan file
            logs_dir = vault / LOGS_DIR
            matches = sorted(logs_dir.glob(f"scan_{tool}_*.json"), reverse=True)
            if matches:
                scan_files.append(matches[0])
                print(f"           ✓ Scan saved: {matches[0].name}")
        else:
            print(f"           ⚠ Scan failed")

    if not scan_files:
        print("\n  No successful scans. Nothing to extract.")
        return 1

    # ── Phase 2: Interactive Extraction ───────────────────────────────────────
    print(f"\n  {'─' * 60}")
    print(f"  PHASE 2: Interactive extraction")
    print(f"  {'─' * 60}")
    print(f"\n  {len(scan_files)} scan(s) ready for extraction.")
    print(f"  Components are saved immediately. Ctrl+C to pause, re-run to resume.\n")

    if not auto:
        print("  Press Enter to begin extraction (or 'q' to quit): ", end="")
        resp = input().strip().lower()
        if resp == "q":
            print("\n  Extraction skipped. Run again to continue.")
            return 0

    # Process each scan file
    for scan_file in scan_files:
        rc = cmd_extract(vault, from_scan=True, scan_path=scan_file, auto=auto)

    # ── Summary ───────────────────────────────────────────────────────────────
    n_comp = _count_vault_files(vault, COMPONENTS_DIR)
    n_tools = _count_vault_files(vault, TOOLS_DIR)

    print(f"\n{'=' * 70}")
    print(f"  BATCH COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Codebases scanned: {len(scan_files)}")
    print(f"  Components in vault: {n_comp}")
    print(f"  Tools in vault: {n_tools}")

    if n_comp >= 5:
        print("\n  Ready for analysis!")
        print("    python main.py track")
        print("    python main.py reconcile interactive")
    else:
        print(f"\n  {n_comp} components. Continue adding codebases for more coverage.")

    print(f"{'=' * 70}\n")

    return 0


# ── review ────────────────────────────────────────────────────────────────────

def cmd_review(vault: Path) -> int:
    """
    Interactive review workflow:
      1. Show tracking status
      2. Run reconciliation interactively
      3. Prompt to check Obsidian graph
      4. Suggest next actions
    """
    print(f"\n{'=' * 60}")
    print("  REVIEW WORKFLOW")
    print(f"{'=' * 60}")

    # Step 1: Track status
    print("\n  Step 1/3 — Current extraction status\n")
    cmd_track(vault, "status")

    # Step 2: Show clusters
    print("\n  Step 2/3 — Showing clusters and gaps\n")
    cmd_track(vault, "clusters")
    cmd_track(vault, "gaps")

    # Step 3: Reconcile interactively
    print("\n  Step 3/3 — Interactive alias reconciliation\n")
    print("  Would you like to reconcile parameter aliases? [Y/n]: ", end="")
    resp = input().strip().lower()
    if resp != "n":
        cmd_reconcile(vault, ["interactive"])

    # Obsidian prompt
    print(f"\n{'─' * 60}")
    print("  📊 OBSIDIAN GRAPH CHECK")
    print(f"{'─' * 60}")
    print("\n  Open your vault in Obsidian and check the graph view.")
    print("  Look for:")
    print("    - Isolated nodes (missing links)")
    print("    - Unexpected clusters")
    print("    - Missing tools or components")
    print("\n  Press Enter when you're done reviewing the graph: ", end="")
    input()

    # Summary
    n_comp = _count_vault_files(vault, COMPONENTS_DIR)
    n_tools = _count_vault_files(vault, TOOLS_DIR)

    print(f"\n{'=' * 60}")
    print("  REVIEW COMPLETE")
    print(f"{'=' * 60}")
    print(f"\n  Components: {n_comp}")
    print(f"  Tools:      {n_tools}")

    if n_comp >= 5:
        print("\n  Ready for implementation!")
        print("    python main.py implement --all")
    else:
        print(f"\n  Need more components (currently {n_comp}, need ≥5)")
        print("    python main.py batch codebases.txt")

    print(f"\n{'=' * 60}\n")

    state = load_state(vault)
    state["last_step"] = "review"
    save_state(vault, state)

    return 0


# ── review-pending ────────────────────────────────────────────────────────────

def _load_skipped(vault: Path) -> set[str]:
    """Load the set of skipped function names from the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_functions.txt"
    if skip_file.exists():
        return set(line.strip() for line in skip_file.read_text().splitlines() if line.strip())
    return set()


def _save_skipped(vault: Path, skipped: set[str]) -> None:
    """Save the set of skipped function names to the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_functions.txt"
    skip_file.parent.mkdir(parents=True, exist_ok=True)
    skip_file.write_text("\n".join(sorted(skipped)) + "\n")


def _load_skipped_files(vault: Path) -> set[str]:
    """Load the set of skipped file paths from the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_files.txt"
    if skip_file.exists():
        return set(line.strip() for line in skip_file.read_text().splitlines() if line.strip())
    return set()


def _save_skipped_files(vault: Path, skipped: set[str]) -> None:
    """Save the set of skipped file paths to the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_files.txt"
    skip_file.parent.mkdir(parents=True, exist_ok=True)
    skip_file.write_text("\n".join(sorted(skipped)) + "\n")


def _load_skipped_dirs(vault: Path) -> set[str]:
    """Load the set of skipped directory paths from the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_dirs.txt"
    if skip_file.exists():
        return set(line.strip() for line in skip_file.read_text().splitlines() if line.strip())
    return set()


def _save_skipped_dirs(vault: Path, skipped: set[str]) -> None:
    """Save the set of skipped directory paths to the skip list file."""
    skip_file = vault / LOGS_DIR / "skipped_dirs.txt"
    skip_file.parent.mkdir(parents=True, exist_ok=True)
    skip_file.write_text("\n".join(sorted(skipped)) + "\n")


def _is_in_skipped_dir(filepath: str, skipped_dirs: set[str]) -> bool:
    """Check if a filepath is inside any of the skipped directories."""
    for skip_dir in skipped_dirs:
        if filepath.startswith(skip_dir):
            return True
    return False


def _slugify(name: str) -> str:
    """Convert a concept name to a valid filename slug."""
    # Replace spaces and special chars with underscores, lowercase
    slug = re.sub(r'[^\w\s-]', '', name.lower())
    slug = re.sub(r'[\s-]+', '_', slug)
    return slug.strip('_')


def _ensure_concept_note(vault: Path, concept_name: str, concept_type: str) -> Path:
    """
    Create a concept note if it doesn't exist, or return existing path.

    concept_type: 'input', 'output', or 'assumption'
    """
    concepts_dir = vault / CONCEPTS_DIR
    concepts_dir.mkdir(parents=True, exist_ok=True)

    slug = _slugify(concept_name)
    concept_path = concepts_dir / f"{slug}.md"

    if not concept_path.exists():
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

    return concept_path


def _ensure_concepts_for_component(vault: Path, inputs: list[str], outputs: list[str], assumes: list[str]) -> None:
    """Ensure all concept notes exist for a component's inputs, outputs, and assumptions."""
    for inp in inputs:
        _ensure_concept_note(vault, inp, "input")
    for out in outputs:
        _ensure_concept_note(vault, out, "output")
    for assumption in assumes:
        _ensure_concept_note(vault, assumption, "assumption")


def cmd_review_pending(vault: Path) -> int:
    """
    Review functions that were flagged for human review during scanning.

    These are functions where the triage heuristics were uncertain
    (confidence between 0.35-0.55). Shows the code and lets you decide
    whether to extract or skip.
    """
    import json

    logs_dir = vault / LOGS_DIR
    scan_files = sorted(logs_dir.glob("scan_*.json"))

    if not scan_files:
        print("\n  No scan files found. Run 'main.py batch' first.\n")
        return 1

    # Collect all human_review functions across all scans
    pending = []
    for scan_file in scan_files:
        scan_data = json.loads(scan_file.read_text())
        tool = scan_data.get("tool", "unknown")
        for func in scan_data.get("functions", []):
            if func.get("verdict") == "human_review":
                func["_tool"] = tool
                func["_scan_file"] = str(scan_file)
                pending.append(func)

    if not pending:
        print("\n  No functions pending human review. All clear!\n")
        return 0

    # Filter out already-extracted components
    existing = set()
    comp_dir = vault / COMPONENTS_DIR
    if comp_dir.exists():
        existing = {f.stem for f in comp_dir.glob("*.md") if f.name != "README.md"}

    # Filter out already-skipped functions, files, and directories
    skipped = _load_skipped(vault)
    skipped_files = _load_skipped_files(vault)
    skipped_dirs = _load_skipped_dirs(vault)

    def should_include(f):
        if f.get("name") in existing:
            return False
        if f.get("name") in skipped:
            return False
        filepath = f.get("filepath", "")
        if filepath in skipped_files:
            return False
        if _is_in_skipped_dir(filepath, skipped_dirs):
            return False
        return True

    remaining = [f for f in pending if should_include(f)]

    # Count exclusions
    in_skipped_files = sum(1 for f in pending if f.get("filepath", "") in skipped_files)
    in_skipped_dirs = sum(1 for f in pending if _is_in_skipped_dir(f.get("filepath", ""), skipped_dirs))

    print(f"\n{'=' * 70}")
    print(f"  HUMAN REVIEW QUEUE")
    print(f"{'=' * 70}")
    print(f"  Total pending: {len(pending)}")
    print(f"  Already extracted: {len(existing & {f.get('name') for f in pending})}")
    print(f"  Already skipped (functions): {len(skipped & {f.get('name') for f in pending})}")
    print(f"  Already skipped (files): {in_skipped_files}")
    print(f"  Already skipped (dirs): {in_skipped_dirs}")
    print(f"  Remaining: {len(remaining)}")
    print(f"{'=' * 70}\n")

    if not remaining:
        print("  All pending functions have been processed.\n")
        return 0

    # Import the interactive extraction function
    from _shared import ensure_tool_note, update_tool_note

    extracted = 0
    skipped_this_session = 0
    total_to_review = len(remaining)

    try:
        while remaining:
            # Filter out any newly skipped files/dirs
            remaining = [f for f in remaining
                        if f.get("filepath", "") not in skipped_files
                        and not _is_in_skipped_dir(f.get("filepath", ""), skipped_dirs)]

            if not remaining:
                break

            func = remaining.pop(0)
            reviewed_count = total_to_review - len(remaining)

            name = func.get("name", "unknown")
            tool = func.get("_tool", "unknown")
            filepath = func.get("filepath", "")
            language = func.get("language", "unknown")
            confidence = func.get("confidence", "?")
            code = func.get("code", func.get("code_preview", ""))

            print(f"\n{'=' * 70}")
            print(f"  [{reviewed_count}/{total_to_review}] {name}  (remaining: {len(remaining)})")
            print(f"  Tool: {tool} | File: {filepath}")
            print(f"  Confidence: {confidence} (flagged for review)")
            print(f"{'=' * 70}")

            # Display code - strip leading/trailing whitespace
            code = code.strip() if code else ""
            if not code:
                print(f"\n  ⚠ No code available for this function")
                print(f"    (May need to re-scan the codebase)\n")
                continue

            lines = code.split("\n")
            print(f"\n{'─' * 70}")
            print(f"  CODE ({language}, {len(lines)} lines)")
            print(f"{'─' * 70}")
            line_width = 90  # Characters per display line
            for j, line in enumerate(lines[:50], 1):
                # First chunk with line number
                if len(line) <= line_width:
                    print(f"  {j:3}│ {line}")
                else:
                    # Wrap long lines
                    print(f"  {j:3}│ {line[:line_width]}")
                    line_rest = line[line_width:]
                    while line_rest:
                        print(f"      │ {line_rest[:line_width]}")
                        line_rest = line_rest[line_width:]
            if len(lines) > 50:
                print(f"  ... ({len(lines) - 50} more lines)")
            print(f"{'─' * 70}\n")

            # Prompt
            print("  Options:")
            print("    [e] Extract (add to components)")
            print("    [s] Skip function")
            print("    [f] Skip entire FILE (all functions in this file)")
            print("    [d] Skip entire DIRECTORY (all functions in this subdir)")
            print("    [q] Quit (progress saved)")

            choice = input("\n  Choice [e/s/f/d/q]: ").strip().lower()

            if choice in ("q", "quit"):
                print(f"\n  Stopped. {extracted} extracted, {skipped_this_session} skipped this session.")
                break
            elif choice in ("s", "skip"):
                # Add to skip list so it doesn't come back
                skipped.add(name)
                _save_skipped(vault, skipped)
                skipped_this_session += 1
                print("  → Skipped function (won't appear again)")
                continue
            elif choice in ("f", "file"):
                # Skip entire file
                skipped_files.add(filepath)
                _save_skipped_files(vault, skipped_files)
                # Count how many remaining functions are in this file (including current)
                file_funcs = [f for f in remaining if f.get("filepath") == filepath]
                skipped_this_session += 1 + len(file_funcs)  # +1 for current function
                print(f"  → Skipped file: {filepath}")
                print(f"    ({1 + len(file_funcs)} functions in this file won't appear again)")
                # remaining will be filtered at top of loop
                continue
            elif choice in ("d", "dir"):
                # Skip entire directory - get parent dir of current file
                from pathlib import PurePosixPath
                file_dir = str(PurePosixPath(filepath).parent)
                skipped_dirs.add(file_dir)
                _save_skipped_dirs(vault, skipped_dirs)
                # Count how many remaining functions are in this directory (including current)
                dir_funcs = [f for f in remaining if f.get("filepath", "").startswith(file_dir)]
                skipped_this_session += 1 + len(dir_funcs)  # +1 for current function
                print(f"  → Skipped directory: {file_dir}/")
                print(f"    ({1 + len(dir_funcs)} functions in this directory won't appear again)")
                # remaining will be filtered at top of loop
                continue
            else:
                # Extract with quick prompts
                print(f"\n  {'─' * 50}")
                print("  QUICK METADATA")
                print(f"  {'─' * 50}")

                # Parse default inputs from params
                params_raw = func.get("params_raw", "")
                default_inputs = [p.strip().split("=")[0].strip()
                                  for p in params_raw.split(",") if p.strip() and p.strip() != "self"]

                print(f"  Inputs (comma-sep) [{', '.join(default_inputs) or 'none'}]: ", end="")
                inputs_str = input().strip()
                if not inputs_str:
                    inputs = default_inputs
                else:
                    inputs = [i.strip() for i in inputs_str.split(",") if i.strip()]

                print(f"  Outputs (comma-sep) [result]: ", end="")
                outputs_str = input().strip()
                outputs = [o.strip() for o in outputs_str.split(",") if o.strip()] if outputs_str else ["result"]

                print(f"  Assumptions (comma-sep) [none]: ", end="")
                assumes_str = input().strip()
                assumes = [a.strip() for a in assumes_str.split(",") if a.strip()] if assumes_str else []

                # Create concept notes for all inputs, outputs, assumptions
                _ensure_concepts_for_component(vault, inputs, outputs, assumes)

                # Create component markdown
                comp_dir = vault / COMPONENTS_DIR
                comp_dir.mkdir(parents=True, exist_ok=True)

                start_line = func.get("start_line", "?")
                end_line = func.get("end_line", "?")

                md_lines = ["---"]
                md_lines.append(f"name: {name}")
                md_lines.append(f'source_tool: "[[{tool}]]"')
                md_lines.append(f"source_file: {filepath}")
                md_lines.append(f"source_lines: {start_line}-{end_line}")
                md_lines.append(f"source_language: {language}")
                md_lines.append("validated: false")
                md_lines.append("inputs:")
                for inp in inputs:
                    slug = _slugify(inp)
                    md_lines.append(f'  - "[[{slug}|{inp}]]"')
                md_lines.append("outputs:")
                for out in outputs:
                    slug = _slugify(out)
                    md_lines.append(f'  - "[[{slug}|{out}]]"')
                if assumes:
                    md_lines.append("assumes:")
                    for assumption in assumes:
                        slug = _slugify(assumption)
                        md_lines.append(f'  - "[[{slug}|{assumption}]]"')
                md_lines.append("---")
                md_lines.append("")
                md_lines.append(f"# {name}")
                md_lines.append("")
                md_lines.append("## Pseudocode")
                md_lines.append("_TODO: describe algorithm_")
                md_lines.append("")
                md_lines.append("## Original Code")
                md_lines.append(f"```{language}")
                md_lines.append(code)
                md_lines.append("```")

                out_path = comp_dir / f"{name}.md"
                out_path.write_text("\n".join(md_lines), encoding="utf-8")

                # Update tool note
                tool_file = ensure_tool_note(vault, tool, language=language)
                update_tool_note(tool_file, name)

                extracted += 1
                print(f"\n  ✓ Saved: {out_path.name}")

    except KeyboardInterrupt:
        print(f"\n\n  Interrupted. {extracted} extracted, {skipped_this_session} skipped this session.")
        print(f"  Re-run 'main.py review-pending' to continue.")

    print(f"\n{'=' * 70}")
    print(f"  REVIEW SESSION COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Extracted: {extracted}")
    print(f"  Skipped: {skipped_this_session}")
    print(f"  Remaining: {len(remaining) - extracted - skipped_this_session}")
    print(f"{'=' * 70}\n")

    return 0


# ── run (full pipeline for one codebase) ──────────────────────────────────────

def cmd_run(
    codebase: Path,
    tool: str,
    vault: Path,
    lang: Optional[str] = None,
    auto: bool = False,
) -> int:
    """
    Run the full automated pipeline for a single codebase:
        1_scan → 2_extract (from-scan) → 3_track status
    """
    # Step 1: Scan
    print(f"\n{'=' * 60}")
    print(f"  PIPELINE: {tool}")
    print(f"  Step 1/3 — Scanning {codebase}")
    print(f"{'=' * 60}")

    rc = cmd_scan(codebase, tool, vault, lang=lang, auto=auto)
    if rc != 0:
        print(f"\n  ✗ Scan failed (exit {rc}). Stopping pipeline.\n")
        return rc

    # Step 2: Extract from scan
    print(f"\n{'=' * 60}")
    print(f"  Step 2/3 — Extracting from scan")
    print(f"{'=' * 60}")

    rc = cmd_extract(vault, from_scan=True, auto=auto)
    if rc != 0:
        print(f"\n  ⚠ Extract had issues (exit {rc}), continuing...\n")

    # Step 3: Track
    print(f"\n{'=' * 60}")
    print(f"  Step 3/3 — Tracking progress")
    print(f"{'=' * 60}")

    cmd_track(vault, "status")

    # Summary
    n_comp = _count_vault_files(vault, COMPONENTS_DIR)

    print(f"\n{'=' * 60}")
    print(f"  PIPELINE COMPLETE: {tool}")
    print(f"{'=' * 60}")
    print(f"\n  Components in vault: {n_comp}")

    if n_comp >= 5:
        print("\n  Ready for review and implementation!")
        print("    python main.py review")
    else:
        print(f"\n  Need more components. Scan more codebases.")

    print(f"\n{'=' * 60}\n")

    state = load_state(vault)
    state["last_step"] = "run"
    save_state(vault, state)

    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="AGFORSIM Workflow Orchestrator — drives the full pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--vault", type=Path, default=None,
        help="Path to vault (defaults to ../)",
    )
    sub = parser.add_subparsers(dest="command")

    # status
    sub.add_parser("status", help="Show detailed workflow progress")

    # focus
    p = sub.add_parser("focus", help="Set or change the current research focus")
    p.add_argument("name", help="Focus name (e.g. biomass, competition, mortality)")

    # next
    sub.add_parser("next", help="Suggest the most useful next action")

    # done
    sub.add_parser("done", help="Mark current focus as completed")

    # batch (new)
    p = sub.add_parser("batch", help="Process multiple codebases from file")
    p.add_argument("codebases_file", type=Path, help="File with codebase paths")
    p.add_argument("--auto", action="store_true", help="Skip interactive prompts")

    # review
    sub.add_parser("review", help="Interactive review workflow")

    # review-pending
    sub.add_parser("review-pending", help="Review functions flagged for human review")

    # scan
    p = sub.add_parser("scan", help="Scan a codebase for domain functions")
    p.add_argument("codebase", type=Path)
    p.add_argument("--tool", required=True)
    p.add_argument("--lang", choices=[
        "r", "python", "julia", "fortran", "java", "matlab",
        "typescript", "javascript", "c", "cpp", "netlogo", "jupyter",
    ])
    p.add_argument("--auto", action="store_true", help="Skip human review")
    p.add_argument("--include", nargs="*", default=[])
    p.add_argument("--exclude", nargs="*", default=[])

    # extract
    p = sub.add_parser("extract", help="Extract functions to component markdown")
    p.add_argument("codebase", type=Path, nargs="?")
    p.add_argument("--tool")
    p.add_argument("--file", dest="filepath")
    p.add_argument("--func")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--mode", choices=["batch", "interactive", "paste", "quick"],
                   default="batch")
    p.add_argument("--from-scan", action="store_true",
                   help="Extract from most recent scan JSON")

    # track
    p = sub.add_parser("track", help="Track extraction progress and patterns")
    p.add_argument("sub", nargs="?", default="status",
                   choices=["status", "inputs", "outputs", "clusters", "gaps", "export"])

    # reconcile
    p = sub.add_parser("reconcile", help="Reconcile aliases and parameter names")
    p.add_argument("sub_args", nargs="*", default=["suggest"])

    # implement
    p = sub.add_parser("implement", help="Generate Python component stubs")
    p.add_argument("name", nargs="?", help="Component name (omit for --all)")
    p.add_argument("--status", action="store_true", help="Show pipeline status")

    # report
    p = sub.add_parser("report", help="Generate analysis report from results")
    p.add_argument("results", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--plot", action="store_true")

    # run
    p = sub.add_parser("run", help="Full pipeline: scan → extract → track")
    p.add_argument("codebase", type=Path)
    p.add_argument("--tool", required=True)
    p.add_argument("--lang", choices=[
        "r", "python", "julia", "fortran", "java", "matlab",
        "typescript", "javascript", "c", "cpp", "netlogo", "jupyter",
    ])
    p.add_argument("--auto", action="store_true", help="Skip interactive prompts")

    # Parse
    args = parser.parse_args()
    vault = resolve_vault(args.vault) if args.vault else VAULT_DEFAULT

    # Dispatch
    if args.command == "status":
        cmd_status(vault)

    elif args.command == "focus":
        cmd_focus(vault, args.name)

    elif args.command == "next":
        cmd_next(vault)

    elif args.command == "done":
        cmd_done(vault)

    elif args.command == "batch":
        rc = cmd_batch(args.codebases_file, vault, auto=args.auto)
        sys.exit(rc)

    elif args.command == "review":
        rc = cmd_review(vault)
        sys.exit(rc)

    elif args.command == "review-pending":
        rc = cmd_review_pending(vault)
        sys.exit(rc)

    elif args.command == "scan":
        rc = cmd_scan(
            args.codebase, args.tool, vault,
            lang=args.lang,
            include=args.include or None,
            exclude=args.exclude or None,
            auto=args.auto,
        )
        sys.exit(rc)

    elif args.command == "extract":
        if args.mode == "paste":
            rc = cmd_extract(vault, mode="paste")
        elif args.mode == "quick":
            rc = cmd_extract(vault, mode="quick")
        elif args.from_scan:
            rc = cmd_extract(vault, from_scan=True, auto=args.auto)
        else:
            rc = cmd_extract(
                vault, args.codebase, args.tool,
                filepath=args.filepath, func=args.func,
                auto=args.auto, mode=args.mode,
            )
        sys.exit(rc)

    elif args.command == "track":
        rc = cmd_track(vault, args.sub)
        sys.exit(rc)

    elif args.command == "reconcile":
        rc = cmd_reconcile(vault, args.sub_args)
        sys.exit(rc)

    elif args.command == "implement":
        rc = cmd_implement(vault, args.name, status=args.status)
        sys.exit(rc)

    elif args.command == "report":
        rc = cmd_report(args.results, vault, args.output, args.plot)
        sys.exit(rc)

    elif args.command == "run":
        rc = cmd_run(args.codebase, args.tool, vault, lang=args.lang, auto=args.auto)
        sys.exit(rc)

    else:
        # No command given — show status + next suggestion
        cmd_status(vault)
        cmd_next(vault)


if __name__ == "__main__":
    main()
