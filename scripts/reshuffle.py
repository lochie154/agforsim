import random

input_file = "links.md"
output_file = "links_shuffled.md"

with open(input_file, "r", encoding="utf-8") as f:
    lines = [line.rstrip("\n") for line in f if line.strip()]

random.shuffle(lines)

with open(output_file, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"Shuffled {len(lines)} URLs → {output_file}")
