"""Small, dependency-free release metadata checks used locally and in CI."""
from __future__ import annotations

import argparse
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent.parent
VERSION_PATTERN = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)
SEMVER_PATTERN = re.compile(r"\d+\.\d+\.\d+")


def project_version(root: Path = ROOT) -> str:
    source = (root / "dawsync" / "__init__.py").read_text(encoding="utf-8")
    match = VERSION_PATTERN.search(source)
    if match is None or SEMVER_PATTERN.fullmatch(match.group(1)) is None:
        raise RuntimeError("dawsync.__version__ must be a three-part release version such as 0.2.0")
    return match.group(1)


def check_tag(tag: str, root: Path = ROOT) -> str:
    expected = "v" + project_version(root)
    if tag != expected:
        raise RuntimeError(f"Release tag {tag!r} does not match application version {expected!r}")
    return expected


def main():
    parser = argparse.ArgumentParser(description="Validate DAWSync release metadata")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version", help="Print the application version")
    check = subparsers.add_parser("check-tag", help="Require a v<version> release tag")
    check.add_argument("tag")
    args = parser.parse_args()
    if args.command == "check-tag":
        check_tag(args.tag)
    print(project_version())


if __name__ == "__main__":
    main()
