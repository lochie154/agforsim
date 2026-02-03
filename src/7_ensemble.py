#!/usr/bin/env python3
"""
Run ensemble of implementations on scenario.

Usage:
    python 7_ensemble.py scenarios/test.yaml
    python 7_ensemble.py scenarios/test.yaml --systems natural_forest,agroforestry
    python 7_ensemble.py scenarios/test.yaml --years 50 --output results/
"""

import argparse
import json
from pathlib import Path
from datetime import datetime

# TODO:
# - [ ] Load scenario from YAML
# - [ ] Select components/systems
# - [ ] Run each on same inputs
# - [ ] Collect outputs over time
# - [ ] Compute divergence metrics
# - [ ] Export results to outputs/


def main():
    parser = argparse.ArgumentParser(description="Run ensemble")
    parser.add_argument("scenario", type=Path, help="Scenario YAML file")
    parser.add_argument("--systems", default="natural_forest,agroforestry")
    parser.add_argument("--years", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("../outputs"))
    
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    
    print(f"\nRunning ensemble:")
    print(f"  Scenario: {args.scenario}")
    print(f"  Systems: {args.systems}")
    print(f"  Years: {args.years}")
    
    try:
        from agforsim.scenarios import load_scenario
        from agforsim.systems import NaturalForest, Agroforestry, Silvopasture, Monoculture, FoodForest
        from agforsim.ensemble import EnsembleRunner, EnsembleRun
        
        scenario = load_scenario(args.scenario)
        
        systems = {
            "natural_forest": NaturalForest,
            "agroforestry": Agroforestry,
            "silvopasture": Silvopasture,
            "monoculture": Monoculture,
            "food_forest": FoodForest,
        }
        
        runs = []
        for name in args.systems.split(","):
            name = name.strip()
            if name in systems:
                runs.append(EnsembleRun(systems[name](), scenario, name))
        
        print(f"\n  Running {len(runs)} systems...")
        runner = EnsembleRunner(runs)
        results = runner.execute(args.years)
        
        # Report
        print(f"\n{'='*50}")
        print("RESULTS")
        print(f"{'='*50}")
        
        for r in results:
            if r.success:
                final = r.outputs[-1]
                print(f"\n{r.label}:")
                print(f"  Biomass: {final.get('total_biomass_kg', 'N/A')}")
                print(f"  Density: {final.get('density_trees_ha', 'N/A')}")
            else:
                print(f"\n{r.label}: FAILED - {r.error}")
        
        # Save
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_file = args.output / f"ensemble_{timestamp}.json"
        
        data = [{"label": r.label, "success": r.success, 
                 "outputs": r.outputs if r.success else [], 
                 "error": r.error} for r in results]
        
        out_file.write_text(json.dumps(data, indent=2, default=str))
        print(f"\nResults saved to {out_file}")
    
    except ImportError as e:
        print(f"\nError: {e}")
        print("Make sure agforsim is installed: pip install -e .")


if __name__ == "__main__":
    main()
