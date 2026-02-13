# AGFORSIM

Extraction and ensemble pipeline for agroforestry simulation models.

## Overview

This package provides tools for:
- **Scanning** codebases to extract domain-relevant functions
- **Extracting** function metadata (inputs, outputs, assumptions)
- **Tracking** concepts and their relationships
- **Building** ensemble models from compatible components

## Installation

```bash
pip install -e .
```

## Usage

```bash
cd src

# Scan a codebase for functions
python main.py scan /path/to/codebase tool_name --lang python

# Review pending functions (human triage)
python main.py review-pending

# Build indexes
python ../scripts/build_indexes.py

# Resolve concepts from components
python ../scripts/resolve_concepts.py
```

## Directory Structure

```
src/
  main.py          # CLI orchestrator
  1_scan.py        # Codebase scanning
  2_extract.py     # Function extraction
  3_track.py       # Concept tracking
  4_reconcile.py   # Alias resolution
  5_implement.py   # Stub generation
  8_report.py      # Analysis reports
  _shared.py       # Common utilities

scripts/
  build_indexes.py     # Generate index files
  resolve_concepts.py  # Backfill concept notes
```

## Related

- [agforsim-docs](https://github.com/lochie154/agforsim-docs) - Documentation vault
