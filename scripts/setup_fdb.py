"""Checkout a fixed upstream FDB-v3 revision into an ignored local directory."""

import argparse
import subprocess
from pathlib import Path


UPSTREAM = "https://github.com/DanielLin94144/Full-Duplex-Bench.git"
REVISION = "3e799c45a045256f47d5f1c9cda90157e2d2ec9e"


def setup(destination: Path) -> Path:
    destination = destination.resolve()
    if destination.exists():
        actual = subprocess.check_output(
            ["git", "-C", str(destination), "rev-parse", "HEAD"], text=True
        ).strip()
        if actual != REVISION:
            raise RuntimeError("Existing FDB checkout has a different commit; leave it untouched")
    else:
        if not destination.parent.is_dir():
            raise FileNotFoundError(f"Parent directory does not exist: {destination.parent}")
        subprocess.run(["git", "clone", "--filter=blob:none", UPSTREAM, str(destination)], check=True)
        subprocess.run(["git", "-C", str(destination), "checkout", "--detach", REVISION], check=True)
    return destination / "v3"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=Path("vendor/Full-Duplex-Bench"))
    print(setup(parser.parse_args().destination))
