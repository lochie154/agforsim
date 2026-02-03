#!/usr/bin/env python3
"""
Test individual component implementation.

Usage:
    python 6_test_single.py biomass_from_dbh --inputs '{"dbh": 25, "a": 0.1, "b": 2.4}'
    python 6_test_single.py biomass_from_dbh --file test_inputs.json
"""

import argparse
import json
import sys

# TODO:
# - [ ] Load component by name from registry
# - [ ] Accept test inputs from CLI or file
# - [ ] Run component
# - [ ] Compare output to expected (if provided)
# - [ ] Report success/failure
# - [ ] Save test results


def main():
    parser = argparse.ArgumentParser(description="Test single component")
    parser.add_argument("name", help="Component name")
    parser.add_argument("--inputs", help="JSON inputs")
    parser.add_argument("--file", type=argparse.FileType('r'), help="Input file")
    parser.add_argument("--expected", help="Expected output JSON")
    
    args = parser.parse_args()
    
    # Load inputs
    if args.inputs:
        inputs = json.loads(args.inputs)
    elif args.file:
        inputs = json.load(args.file)
    else:
        print("Provide --inputs or --file")
        sys.exit(1)
    
    # TODO: Load component from registry
    print(f"\nTesting: {args.name}")
    print(f"Inputs: {inputs}")
    
    try:
        # Import and run
        from agforsim.core.registry import registry
        registry.discover()
        
        comp_class = registry.get(args.name)
        if not comp_class:
            print(f"Component not found: {args.name}")
            sys.exit(1)
        
        comp = comp_class()
        result = comp.run(inputs)
        
        print(f"Output: {result}")
        
        if args.expected:
            expected = json.loads(args.expected)
            if result == expected:
                print("✓ PASS")
            else:
                print(f"✗ FAIL: expected {expected}")
                sys.exit(1)
        else:
            print("✓ Completed (no expected value to check)")
    
    except Exception as e:
        print(f"✗ ERROR: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
