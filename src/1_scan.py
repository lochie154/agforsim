#!/usr/bin/env python3
"""
Step 1 — Scan codebase for functions.

Walks a codebase directory, detects R / Python / Julia source files,
extracts function definitions, applies triage heuristics with confidence
scoring, and flags ambiguous cases for human review.

Usage:
    python 1_scan.py ~/repos/sortie --tool sortie
    python 1_scan.py ~/repos/apsim --tool apsim --lang python
    python 1_scan.py ~/repos/sortie --tool sortie --auto   # skip human review
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unittest
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from _shared import (
    LOGS_DIR, LANG_EXTENSIONS,
    resolve_vault, vault_subdir, ensure_tool_note,
    detect_language, extract_functions,
    find_and_extract_zips, ZipSecurityError,
)


# ── triage configuration ───────────────────────────────────────────────────

SKIP_PATH_TOKENS = [
    "test", "tests", "__test", "spec", "mock", "fixture", "fixtures",
    "vignettes", "examples", "demo", "docs",
]

SKIP_PATH_INFRA = [
    "setup", "config", "util", "utils", "helper", "helpers",
    "io", "plot", "viz", "gui", "cli", "logging",
    "migrations", "scripts", "bin",
]

SKIP_FUNC_PREFIXES = [
    "test_", "_test", "__",
    "print_", "plot_", "draw_", "render_",
    "read_", "write_", "load_", "save_",
    "get_", "set_", "is_", "has_", "check_",
    "parse_", "format_", "validate_",
    "log_", "debug_", "warn_",
    "main", "setup", "teardown",
]

DOMAIN_KEYWORDS = [
    "biomass", "growth", "mortality", "allometr", "photosynthes",
    "respir", "transpir", "canopy", "soil", "carbon", "nitrogen",
    "nutrient", "water", "light", "radiation", "temperature",
    "competition", "decompos", "yield", "harvest", "phenolog",
    "leaf", "root", "stem", "branch", "trunk", "crown",
    "density", "basal_area", "dbh", "diameter", "height",
    "fire", "drought", "flood", "wind", "erosion",
    "succession", "regenerat", "recruitment", "dispersal",
    "predation", "herbivory", "pollination", "symbiosis",
    "npp", "gpp", "nee", "lai", "sla", "par", "vpd",
    "evapotranspir", "runoff", "infiltrat", "albedo",
    "simulate", "model", "calc_", "compute_", "estimate_",
]

TRIVIAL_MAX_LINES = 3


# ── dataclass ─────────────────────────────────────────────────────────────

@dataclass
class ScoredFunction:
    """A function with triage metadata."""
    name: str
    filepath: str
    language: str
    start_line: int
    end_line: int
    param_count: int
    body_lines: int
    code: str
    params_raw: str
    verdict: str = "extract"      # extract | skip | human_review
    confidence: float = 1.0
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dict, always keeping full code for extraction."""
        return asdict(self)


# ── triage helpers ─────────────────────────────────────────────────────────

def _count_params(params_raw: str) -> int:
    if not params_raw.strip():
        return 0
    cleaned = re.sub(r"\bself\s*,?\s*", "", params_raw)
    if not cleaned.strip():
        return 0
    return len(re.split(r",\s*(?![^()]*\))", cleaned))


def _body_line_count(code: str) -> int:
    lines = code.strip().split("\n")
    count = 0
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            continue
        count += 1
    return count


def triage_function(func: dict, filepath: str, language: str) -> ScoredFunction:
    """Score a function for domain relevance. Returns ScoredFunction."""
    name = func["name"]
    name_lower = name.lower()
    code = func.get("code", "")
    params_raw = func.get("params_raw", "")
    param_count = _count_params(params_raw)
    body_lines = _body_line_count(code)
    code_lower = code.lower()

    reasons: list[str] = []
    score = 0.5

    # Name prefix penalties
    for prefix in SKIP_FUNC_PREFIXES:
        if name_lower.startswith(prefix):
            score -= 0.30
            reasons.append(f"name starts with '{prefix}'")
            break

    # Domain keyword boosts
    for kw in DOMAIN_KEYWORDS:
        if kw in name_lower:
            score += 0.25
            reasons.append(f"domain keyword '{kw}' in name")
            break

    body_hits = sum(1 for kw in DOMAIN_KEYWORDS if kw in code_lower)
    if body_hits >= 3:
        score += 0.20
        reasons.append(f"{body_hits} domain keywords in body")
    elif body_hits >= 1:
        score += 0.10
        reasons.append(f"{body_hits} domain keyword(s) in body")

    # Size signals
    if body_lines <= TRIVIAL_MAX_LINES:
        score -= 0.15
        reasons.append(f"trivial ({body_lines} lines)")
    if body_lines >= 15:
        score += 0.10
        reasons.append(f"substantial ({body_lines} lines)")
    if param_count >= 4:
        score += 0.10
        reasons.append(f"{param_count} parameters")

    # Numeric constants
    nums = re.findall(r"(?<![a-zA-Z_])\d+\.?\d*(?![a-zA-Z_])", code)
    trivial_nums = {"0", "1", "2", "0.0", "1.0", "2.0", "0.5"}
    nontrivial = [n for n in nums if n not in trivial_nums]
    if len(nontrivial) >= 3:
        score += 0.10
        reasons.append(f"{len(nontrivial)} numeric constants")

    # Math operators
    math_ops = len(re.findall(r"[\*\/\^]|exp\(|log\(|sqrt\(|\*\*", code))
    if math_ops >= 3:
        score += 0.10
        reasons.append(f"{math_ops} math operators")

    # I/O penalty
    io_calls = len(re.findall(
        r"\b(read|write|open|close|print|cat|message|warning|stop)\s*\(", code))
    if io_calls >= 2:
        score -= 0.20
        reasons.append(f"{io_calls} I/O calls")

    # Plot penalty
    plot_calls = len(re.findall(
        r"\b(plot|ggplot|geom_|plt\.|matplotlib|seaborn)\b", code))
    if plot_calls >= 1:
        score -= 0.20
        reasons.append(f"{plot_calls} plot call(s)")

    # Dunder penalty
    if language == "python" and name.startswith("__") and name.endswith("__"):
        score -= 0.30
        reasons.append("dunder method")

    score = max(0.0, min(1.0, score))

    if score >= 0.55:
        verdict = "extract"
    elif score <= 0.35:
        verdict = "skip"
    else:
        verdict = "human_review"

    if not reasons:
        reasons.append("no strong signals")

    return ScoredFunction(
        name=name, filepath=filepath, language=language,
        start_line=func["start_line"], end_line=func["end_line"],
        param_count=param_count, body_lines=body_lines,
        code=code, params_raw=params_raw,
        verdict=verdict, confidence=round(score, 2), reasons=reasons,
    )


def should_skip_path(path: Path) -> bool:
    parts_lower = [p.lower() for p in path.parts]
    for token in SKIP_PATH_TOKENS + SKIP_PATH_INFRA:
        if token in parts_lower:
            return True
    return False


# ── scan result ────────────────────────────────────────────────────────────

@dataclass
class ScanResult:
    tool: str
    codebase: str
    timestamp: str
    language_filter: str | None
    files_scanned: int = 0
    files_with_functions: int = 0
    functions: list[ScoredFunction] = field(default_factory=list)

    @property
    def by_verdict(self) -> dict[str, list[ScoredFunction]]:
        groups: dict[str, list[ScoredFunction]] = {"extract": [], "skip": [], "human_review": []}
        for f in self.functions:
            groups.setdefault(f.verdict, []).append(f)
        return groups

    def to_dict(self) -> dict:
        return {
            "tool": self.tool,
            "codebase": self.codebase,
            "timestamp": self.timestamp,
            "language_filter": self.language_filter,
            "files_scanned": self.files_scanned,
            "files_with_functions": self.files_with_functions,
            "summary": {v: len(fs) for v, fs in self.by_verdict.items()},
            "functions": [f.to_dict() for f in self.functions],
        }


# ── scanning ───────────────────────────────────────────────────────────────

def scan_codebase(
    codebase: Path,
    tool: str,
    lang: str | None = None,
    extract_zips: bool = True,
) -> ScanResult:
    """Scan codebase for function definitions.

    If extract_zips=True, any .zip files found will be securely extracted
    before scanning (zip bombs and path traversal attacks are blocked).
    """
    # First, extract any zip files found in the codebase
    if extract_zips:
        try:
            zip_results = find_and_extract_zips(codebase, remove_after=False)
            if zip_results:
                print(f"  Extracted {len(zip_results)} zip file(s)")
        except Exception as e:
            print(f"  Warning: zip extraction failed: {e}")

    exts = LANG_EXTENSIONS.get(lang, []) if lang else [e for group in LANG_EXTENSIONS.values() for e in group]

    result = ScanResult(
        tool=tool, codebase=str(codebase),
        timestamp=datetime.now(timezone.utc).isoformat(),
        language_filter=lang,
    )

    seen: set[Path] = set()
    for ext in exts:
        for filepath in sorted(codebase.rglob(f"*{ext}")):
            if filepath in seen:
                continue
            seen.add(filepath)
            result.files_scanned += 1

            if should_skip_path(filepath.relative_to(codebase)):
                continue

            try:
                code = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            language = detect_language(str(filepath))
            funcs = extract_functions(code, language)
            if not funcs:
                continue

            result.files_with_functions += 1
            rel = str(filepath.relative_to(codebase))

            for func_data in funcs:
                scored = triage_function(func_data, rel, language)
                result.functions.append(scored)

    return result


# ── human review ───────────────────────────────────────────────────────────

def interactive_review(result: ScanResult) -> None:
    """Interactively review human_review functions."""
    review_funcs = [f for f in result.functions if f.verdict == "human_review"]
    if not review_funcs:
        return

    print(f"\n{'─' * 60}")
    print(f"  HUMAN REVIEW: {len(review_funcs)} function(s) need your decision")
    print(f"{'─' * 60}\n")

    for i, f in enumerate(review_funcs, 1):
        print(f"[{i}/{len(review_funcs)}] {f.name} ({f.filepath}:{f.start_line})")
        print(f"    Confidence: {f.confidence:.0%}")
        print(f"    Reasons: {'; '.join(f.reasons)}")
        print(f"    Preview:")
        for line in f.code.split("\n")[:10]:
            print(f"      {line}")
        if f.code.count("\n") > 10:
            print(f"      ... ({f.body_lines} total lines)")
        print()

        while True:
            choice = input("    [e]xtract / [s]kip / [q]uit review: ").strip().lower()
            if choice in ("e", "extract"):
                f.verdict = "extract"
                f.reasons.append("human chose extract")
                break
            elif choice in ("s", "skip"):
                f.verdict = "skip"
                f.reasons.append("human chose skip")
                break
            elif choice in ("q", "quit"):
                print("    Leaving remaining as human_review.")
                return
            else:
                print("    Please enter 'e', 's', or 'q'.")
        print()


# ── reporting ──────────────────────────────────────────────────────────────

def print_scan_report(result: ScanResult, file=None) -> None:
    out = file or sys.stdout
    groups = result.by_verdict

    def p(text: str = "") -> None:
        print(text, file=out)

    p(f"\n{'=' * 60}")
    p(f"  SCAN: {result.tool}")
    p(f"{'=' * 60}")
    p(f"  Files scanned:    {result.files_scanned}")
    p(f"  With functions:   {result.files_with_functions}")
    p(f"  Total functions:  {len(result.functions)}")
    p(f"{'=' * 60}")
    p(f"  EXTRACT:       {len(groups['extract']):>3}")
    p(f"  HUMAN REVIEW:  {len(groups['human_review']):>3}")
    p(f"  SKIP:          {len(groups['skip']):>3}")
    p(f"{'=' * 60}\n")

    if groups["extract"]:
        p("  EXTRACT:")
        for f in sorted(groups["extract"], key=lambda x: -x.confidence):
            p(f"    {f.confidence:.0%}  {f.filepath}:{f.start_line}  {f.name}")

    if groups["human_review"]:
        p("\n  HUMAN REVIEW:")
        for f in groups["human_review"]:
            p(f"    {f.confidence:.0%}  {f.filepath}:{f.start_line}  {f.name}")
            p(f"         → {'; '.join(f.reasons)}")

    if groups["skip"]:
        p("\n  SKIP:")
        by_file: dict[str, list[str]] = {}
        for f in groups["skip"]:
            by_file.setdefault(f.filepath, []).append(f.name)
        for fp, names in sorted(by_file.items()):
            p(f"    {fp}: {', '.join(names)}")

    p(f"\n{'=' * 60}\n")


# ── persistence ────────────────────────────────────────────────────────────

def save_scan(result: ScanResult, vault: Path) -> Path:
    logs_dir = vault_subdir(vault, LOGS_DIR)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = logs_dir / f"scan_{result.tool}_{ts}.json"
    out_path.write_text(json.dumps(result.to_dict(), indent=2))
    return out_path


# ── CLI ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Scan codebase for domain functions")
    parser.add_argument("codebase", type=Path, help="Path to codebase root")
    parser.add_argument("--tool", required=True, help="Tool / codebase name")
    parser.add_argument("--lang", choices=list(LANG_EXTENSIONS.keys()))
    parser.add_argument("--vault", type=Path, default=None)
    parser.add_argument("--auto", action="store_true", help="Skip human review")
    parser.add_argument("--include", nargs="*", default=[], help="Force extract these names")
    parser.add_argument("--exclude", nargs="*", default=[], help="Force skip these names")

    args = parser.parse_args()
    vault = resolve_vault(args.vault)

    if not args.codebase.is_dir():
        print(f"Error: {args.codebase} is not a directory", file=sys.stderr)
        sys.exit(1)

    print(f"\nScanning {args.codebase} ...")
    result = scan_codebase(args.codebase, args.tool, args.lang)

    # Manual overrides
    include_set = {n.lower() for n in args.include}
    exclude_set = {n.lower() for n in args.exclude}
    for f in result.functions:
        if f.name.lower() in include_set:
            f.verdict = "extract"
            f.confidence = 1.0
            f.reasons = ["--include override"]
        elif f.name.lower() in exclude_set:
            f.verdict = "skip"
            f.confidence = 0.0
            f.reasons = ["--exclude override"]

    # Interactive review (unless --auto)
    if not args.auto:
        interactive_review(result)

    print_scan_report(result)

    scan_path = save_scan(result, vault)
    print(f"Scan saved: {scan_path}")

    ensure_tool_note(vault, args.tool, language=args.lang or "mixed")


# ── unit tests ─────────────────────────────────────────────────────────────

class TestTriage(unittest.TestCase):
    def _func(self, name, code, params="x"):
        return {"name": name, "start_line": 1, "end_line": 5, "code": code, "params_raw": params}

    def test_domain_function(self):
        code = "def calculate_biomass(dbh):\n    return 0.1 * dbh ** 2.4\n"
        scored = triage_function(self._func("calculate_biomass", code, "dbh"), "bio.py", "python")
        self.assertEqual(scored.verdict, "extract")

    def test_test_function(self):
        code = "def test_something():\n    assert True\n"
        scored = triage_function(self._func("test_something", code, ""), "test.py", "python")
        self.assertEqual(scored.verdict, "skip")

    def test_dunder(self):
        code = "def __init__(self):\n    pass\n"
        scored = triage_function(self._func("__init__", code, "self"), "m.py", "python")
        self.assertEqual(scored.verdict, "skip")


class TestPathSkip(unittest.TestCase):
    def test_skip_tests(self):
        self.assertTrue(should_skip_path(Path("src/tests/test_bio.py")))

    def test_keep_normal(self):
        self.assertFalse(should_skip_path(Path("src/models/growth.py")))


def _run_tests():
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


if __name__ == "__main__":
    if "--test" in sys.argv:
        sys.argv.remove("--test")
        _run_tests()
    else:
        main()
