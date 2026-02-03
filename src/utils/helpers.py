\"\"\"Utility functions for working with external repositories and models.\"\"\"

import subprocess
import pathlib


def clone_repo(url: str, dest: str) -> None:
    dest_path = pathlib.Path(dest)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", url, dest], check=True)
