#!/usr/bin/env python3
"""
Step 8 — Generate analysis reports from ensemble results.

Usage:
    python 8_report.py results.json
    python 8_report.py results.json --output thesis/results.md
    python 8_report.py results.json --plot
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from _shared import OUTPUT_DIR, resolve_vault


def load_results(filepath: Path) -> list[dict]:
    """Load ensemble results from JSON."""
    return json.loads(filepath.read_text(encoding="utf-8"))


def compute_stats(results: list[dict], variable: str) -> dict:
    """Compute basic statistics for a variable across results."""
    trajectories = []
    for r in results:
        if r.get("success"):
            vals = [o.get(variable, 0) for o in r.get("outputs", [])]
            trajectories.append(vals)

    if not trajectories:
        return {}

    import statistics

    final_vals = [t[-1] for t in trajectories if t]

    return {
        "n_runs": len(trajectories),
        "final_mean": statistics.mean(final_vals) if final_vals else 0,
        "final_std": statistics.stdev(final_vals) if len(final_vals) > 1 else 0,
        "final_min": min(final_vals) if final_vals else 0,
        "final_max": max(final_vals) if final_vals else 0,
    }


def generate_report(results: list[dict], output_path: Path) -> None:
    """Generate markdown report from results."""
    lines = [
        "# Ensemble Results Report",
        f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "\n## Summary",
        f"\nRuns: {len(results)}",
        f"Successful: {sum(1 for r in results if r.get('success'))}",
    ]

    # Per-system results
    lines.append("\n## System Results\n")
    for r in results:
        lines.append(f"### {r.get('label', 'Unknown')}")
        if r.get("success"):
            outputs = r.get("outputs", [])
            if outputs:
                final = outputs[-1]
                lines.append(f"- Final biomass: {final.get('total_biomass_kg', 'N/A')}")
                lines.append(f"- Final density: {final.get('density_trees_ha', 'N/A')}")
        else:
            lines.append(f"- Error: {r.get('error')}")
        lines.append("")

    # Statistics
    stats = compute_stats(results, "total_biomass_kg")
    if stats:
        lines.append("\n## Biomass Statistics\n")
        lines.append(f"- Mean: {stats['final_mean']:.2f}")
        lines.append(f"- Std: {stats['final_std']:.2f}")
        lines.append(f"- Range: {stats['final_min']:.2f} - {stats['final_max']:.2f}")

    # Gaps
    lines.append("\n## Identified Gaps\n")
    lines.append("- TODO: Identify missing components")
    lines.append("- TODO: Note divergence points")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report saved to {output_path}")


def generate_plot(results: list[dict], output_path: Path) -> None:
    """Generate plot if matplotlib is available."""
    try:
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(10, 6))
        for r in results:
            if r.get("success"):
                vals = [o.get("total_biomass_kg", 0) for o in r.get("outputs", [])]
                ax.plot(vals, label=r.get("label"))

        ax.set_xlabel("Year")
        ax.set_ylabel("Biomass (kg)")
        ax.legend()

        plot_path = output_path.with_suffix(".png")
        plt.savefig(plot_path)
        print(f"Plot saved to {plot_path}")
    except ImportError:
        print("matplotlib not available for plotting")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 8: Generate analysis reports from results",
    )
    parser.add_argument(
        "results", type=Path,
        help="Results JSON file",
    )
    parser.add_argument(
        "--vault", type=Path, default=None,
        help="Path to vault (defaults to ../)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output report path",
    )
    parser.add_argument(
        "--plot", action="store_true",
        help="Generate plots (requires matplotlib)",
    )

    args = parser.parse_args()
    vault = resolve_vault(args.vault)

    # Default output to vault's output directory
    output_path = args.output or (vault / OUTPUT_DIR / "report.md")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = load_results(args.results)
    generate_report(results, output_path)

    if args.plot:
        generate_plot(results, output_path)


if __name__ == "__main__":
    main()
