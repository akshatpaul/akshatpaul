#!/usr/bin/env python3
"""Splice the contents of stats.md into README.md between marker comments.

    <!-- STATS:START -->
    ...generated content...
    <!-- STATS:END -->

Idempotent: running it repeatedly replaces the block in place.
"""

from __future__ import annotations

import pathlib
import sys

README = pathlib.Path("README.md")
STATS = pathlib.Path("stats.md")
START = "<!-- STATS:START -->"
END = "<!-- STATS:END -->"


def main() -> None:
    readme = README.read_text()
    stats = STATS.read_text().strip()

    if START not in readme or END not in readme:
        sys.exit(f"error: README.md is missing the {START} / {END} markers")

    head, _, rest = readme.partition(START)
    _, _, tail = rest.partition(END)
    updated = f"{head}{START}\n{stats}\n{END}{tail}"

    if updated != readme:
        README.write_text(updated)
        print("README.md stats block updated")
    else:
        print("README.md stats block already current")


if __name__ == "__main__":
    main()
