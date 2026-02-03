#!/usr/bin/env python3
"""
AGFORSIM Workflow Orchestrator

Orchestrates the full extraction→implementation→ensemble workflow.
Tracks state between steps and prompts for next focus.

Usage:
    python main.py                    # Interactive mode
    python main.py focus "biomass"    # Set current focus
    python main.py status             # Show progress
    python main.py next               # Suggest next step
"""

import argparse
import json
from pathlib import Path

STATE_FILE = Path(__file__).parent.parent / "logs" / "workflow_state.json"

# TODO:
# - [ ] Parse CLI args for workflow stage
# - [ ] Load/save workflow state (current focus, progress)
# - [ ] Call appropriate sub-script
# - [ ] Prompt for next focus after each cycle
# - [ ] Track components extracted per focus
# - [ ] Suggest when to run ensemble (5+ components)
# - [ ] Suggest next focus based on gaps


def load_state() -> dict:
    """Load workflow state from file."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "current_focus": None,
        "completed_focuses": [],
        "components_extracted": 0,
        "ensembles_run": 0,
    }


def save_state(state: dict):
    """Save workflow state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main():
    parser = argparse.ArgumentParser(description="AGFORSIM Workflow")
    subparsers = parser.add_subparsers(dest="command")
    
    # Focus command
    focus_p = subparsers.add_parser("focus", help="Set current focus")
    focus_p.add_argument("name", help="Focus name (e.g., 'biomass', 'competition')")
    
    # Status command
    subparsers.add_parser("status", help="Show workflow status")
    
    # Next command
    subparsers.add_parser("next", help="Suggest next step")
    
    args = parser.parse_args()
    state = load_state()
    
    if args.command == "focus":
        state["current_focus"] = args.name
        save_state(state)
        print(f"Focus set to: {args.name}")
        print("\nNext steps:")
        print("  1. python 1_scan.py <codebase> --tool <name>")
        print("  2. python 2_extract.py <codebase> --tool <name> --file <file>")
    
    elif args.command == "status":
        print(f"\nCurrent focus: {state.get('current_focus', 'None')}")
        print(f"Components extracted: {state.get('components_extracted', 0)}")
        print(f"Completed focuses: {state.get('completed_focuses', [])}")
        print(f"Ensembles run: {state.get('ensembles_run', 0)}")
    
    elif args.command == "next":
        # TODO: Implement smart suggestions based on state
        print("\nSuggested next step:")
        if not state.get("current_focus"):
            print("  Set a focus: python main.py focus 'biomass'")
        elif state.get("components_extracted", 0) < 5:
            print("  Extract more components: python 2_extract.py ...")
        else:
            print("  Run ensemble: python 7_ensemble.py scenarios/test.yaml")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
