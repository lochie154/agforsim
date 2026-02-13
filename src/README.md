# AGFORSIM Extraction Pipeline

Scan codebases, extract domain functions, and create Obsidian markdown notes that form a knowledge graph of agroforestry simulation components.

## Quick Start

```bash
# Create a file with GitHub URLs (one per line)
echo "https://github.com/owner/repo1
https://github.com/owner/repo2" > repos.txt

# Run batch processing
python main.py batch repos.txt

# Each function's code is displayed for you to review
# Label inputs/outputs interactively
# Ctrl+C to pause at any time - progress is saved
# Re-run to continue from where you left off
```

## How It Works

### Phase 1: Clone & Scan
The batch command clones all GitHub repos and scans them for functions. Each codebase gets a scan JSON saved to `08_Logs/`.

### Phase 2: Interactive Extraction
For each function, you see:
- The full source code
- File location and line numbers
- Auto-detected inputs from parameters

Then you choose:
- `[e]` Extract with review - edit inputs/outputs/description
- `[a]` Auto-extract - use defaults
- `[s]` Skip - don't extract this function
- `[q]` Quit - stop (progress saved)

### Checkpointing
Each component is saved immediately to `02_Components/`. If you interrupt with Ctrl+C or quit, just re-run the same command to continue. Already-extracted components are skipped automatically.

## File Formats

### Input: Codebases File
One entry per line. GitHub URLs are auto-cloned:

```
https://github.com/owner/repo
https://github.com/owner/repo2  r       # with language hint
/local/path  tool_name  python          # local path with tool name
```

### Output: Component Markdown
Each extracted function becomes an Obsidian note in `02_Components/`:

```yaml
---
name: calculate_biomass
source_tool: "[[repo_name]]"
source_file: src/growth.R
source_lines: 45-67
source_language: r
inputs:
  - name: dbh
    type: null
    unit: null
outputs:
  - name: result
    type: null
    unit: null
---

# calculate_biomass

## Pseudocode
_TODO: describe algorithm_

## Original Code
```r
calculate_biomass <- function(dbh) {
  ...
}
```
```

## Scripts

| File | Purpose |
|------|---------|
| `main.py` | Orchestrator - run `batch`, `status`, `track`, etc. |
| `1_scan.py` | Scan codebase, detect functions, apply triage heuristics |
| `2_extract.py` | Interactive extraction with code review |
| `3_track.py` | Track progress, find clusters, identify gaps |
| `4_reconcile.py` | Find and merge parameter aliases |
| `5_implement.py` | Generate Python stubs from components |
| `8_report.py` | Generate analysis reports |
| `_shared.py` | Shared utilities (paths, parsing, extractors) |

## Commands

```bash
# Main workflow
python main.py batch repos.txt       # Clone, scan, and extract interactively
python main.py batch repos.txt --auto  # Skip prompts (use defaults)

# Individual steps
python main.py scan ~/repo --tool name   # Scan one codebase
python main.py extract --from-scan       # Extract from most recent scan
python main.py track status              # Show extraction progress
python main.py track clusters            # Find related functions
python main.py reconcile interactive     # Merge parameter aliases
python main.py implement                 # Generate Python stubs

# Status
python main.py status    # Show overall progress
python main.py next      # Suggest next action
```

## Vault Structure

```
vault/
├── 01_Tools/           # Tool notes (one per codebase)
├── 02_Components/      # Component notes (one per function)
├── 07_Output/          # Generated stubs
├── 08_Logs/            # Scan JSONs, cloned repos
│   ├── clones/         # Cloned GitHub repos
│   └── scan_*.json     # Scan results
└── src/                # This directory
```
