#!/usr/bin/env python3
"""
README Symbol Checker

This script verifies that all top-level class and function names defined in Python
files under the directory containing a given README.md file are mentioned somewhere
in the README.

To use it, configure `setup.cfg` with a [readme_check] section like:

    [readme_check]
    readmes =
        concordia/views/README.md

This will recursively scan all `.py` files in `concordia/views/` and ensure every
class/function defined in them appears by name (case-sensitive) somewhere in the
corresponding README.md.
"""

import ast
import configparser
import sys
from pathlib import Path
from typing import List


def collect_defined_symbols(py_path: Path) -> List[str]:
    """
    Parse a Python file and return all top-level class and function names.
    """
    with py_path.open(encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=str(py_path))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    ]


def read_readme_text(readme_path: Path) -> str:
    return readme_path.read_text(encoding="utf-8")


def check_readme(readme_path: Path) -> int:
    """
    Check that each symbol defined in the Python files under the same directory
    as the README appears in the README text. Returns exit code (0 or 1).
    """
    readme_text = read_readme_text(readme_path)
    search_dir = readme_path.parent
    exit_code = 0

    for py_file in search_dir.rglob("*.py"):
        defined = collect_defined_symbols(py_file)
        for name in defined:
            if name not in readme_text:
                print(f"V001 Symbol '{name}' is not documented in {readme_path.name}")
                exit_code = 1

    return exit_code


def load_readmes_from_config() -> List[Path]:
    """
    Read the list of README.md files from setup.cfg under the [readme_check] section.
    """
    cfg_path = Path("setup.cfg")
    if not cfg_path.exists():
        sys.stderr.write("ERROR: setup.cfg not found\n")
        sys.exit(2)

    config = configparser.ConfigParser()
    config.read(cfg_path)

    try:
        section = config["readme_check"]
        readmes = [
            Path(p.strip())
            for p in section.get("readmes", "").splitlines()
            if p.strip()
        ]
        if not readmes:
            raise ValueError
        return readmes
    except (KeyError, ValueError):
        sys.stderr.write("ERROR: No [readme_check] readmes configured in setup.cfg\n")
        sys.exit(2)


def main() -> None:
    exit_code = 0
    readmes = load_readmes_from_config()

    for readme in readmes:
        if not readme.exists():
            print(f"ERROR: README file not found: {readme}", file=sys.stderr)
            exit_code = 2
        else:
            exit_code = max(exit_code, check_readme(readme))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
