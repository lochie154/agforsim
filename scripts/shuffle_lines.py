#!/usr/bin/env python3
"""
shuffle_lines.py

Randomly shuffle the non-empty lines of a text file.
Intended for randomising a markdown list of URLs or links.

Usage:
    python scripts/shuffle_lines.py INPUT_FILE OUTPUT_FILE
    python scripts/shuffle_lines.py repos-github.md repos-github-shuffled.md
"""

import random
import sys


def shuffle_lines(input_file: str, output_file: str) -> None:
    """Read non-empty lines from *input_file*, shuffle, and write to *output_file*."""
    with open(input_file, "r", encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f if line.strip()]

    random.shuffle(lines)

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    print(f"Shuffled {len(lines)} lines → {output_file}")


def main():
    if len(sys.argv) != 3:
        print("Usage: shuffle_lines.py INPUT OUTPUT", file=sys.stderr)
        sys.exit(1)
    shuffle_lines(sys.argv[1], sys.argv[2])


if __name__ == "__main__":
    main()
