This directory is the executable modelling code that will be used by developers to plug and play. It takes the core logic and algorithms for the simulator and ensemble runners as well as any model adapters that plug in. It is likely to be very primitive by the end of the honours but will continue to develop in future research projects. 

1. Search for codebases relevant to CURRENT FOCUS and append to list
2. Open codebase, note metadata → tools/{codebase_author}.md
3. TRIAGE files (skip utilities, tests, I/O)
4. Open file, TRIAGE functions (skip trivial)
5. Extract function → components/{name}.md
   - inputs, outputs, code, pseudocode
   - flag ambiguous terms for later reconciliation
6. Repeat 5 until file exhausted
7. Repeat 3-6 until codebase exhausted
8. STOP. Check Obsidian graph and note.
   - What clusters?
   - What's missing?
   - What terms need aliasing?
1. Reconcile aliases and create index notes
2. Have 5+ implementations of same process? → Test ensemble
3. Note results, gaps, divergences
4. Identify NEXT FOCUS based on gaps
5. Back to 1 with new focus

Make a list of files to live within the agforsim_vault/src/ folder given they are python scripts that follow this algorithm: