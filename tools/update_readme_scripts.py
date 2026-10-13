#!/usr/bin/env python3
"""Update script catalogs in README files.

This utility scans the `working`, `experimental`, and `templates` directories for
Python scripts and refreshes generated sections in the corresponding README files.
"""

from __future__ import annotations

import argparse
import ast
import logging
import re
import sys
from pathlib import Path
from typing import Iterable

LOGGER = logging.getLogger(__name__)

CATALOG_TARGETS = (
    {
        "name": "working",
        "dir": Path("working"),
        "readme": Path("working/README.md"),
        "start": "<!-- WORKING_SCRIPTS_START -->",
        "end": "<!-- WORKING_SCRIPTS_END -->",
        "link_prefix": "./",
    },
    {
        "name": "experimental",
        "dir": Path("experimental"),
        "readme": Path("experimental/README.md"),
        "start": "<!-- EXPERIMENTAL_SCRIPTS_START -->",
        "end": "<!-- EXPERIMENTAL_SCRIPTS_END -->",
        "link_prefix": "./",
    },
    {
        "name": "templates",
        "dir": Path("templates"),
        "readme": Path("templates/README.md"),
        "start": "<!-- TEMPLATE_SCRIPTS_START -->",
        "end": "<!-- TEMPLATE_SCRIPTS_END -->",
        "link_prefix": "./",
    },
    {
        "name": "non-oci",
        "dir": Path("non-oci"),
        "readme": Path("non-oci/README.md"),
        "start": "<!-- NON_OCI_SCRIPTS_START -->",
        "end": "<!-- NON_OCI_SCRIPTS_END -->",
        "link_prefix": "./",
    },
    {
        "name": "repo",
        "dir": Path("."),
        "readme": Path("README.md"),
        "start": "<!-- TOPLEVEL_SCRIPT_DIRECTORIES_START -->",
        "end": "<!-- TOPLEVEL_SCRIPT_DIRECTORIES_END -->",
        "link_prefix": "",
    },
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description="Update generated script sections in README files.")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--check",
        action="store_true",
        help="Only validate whether files are up-to-date; do not write changes.",
    )
    mode_group.add_argument(
        "--write",
        action="store_true",
        help="Write updates to files (default behavior).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable debug logging.",
    )
    return parser.parse_args()


def configure_logging(verbose: bool) -> None:
    """Configure application logging.

    Args:
        verbose: Whether to enable debug-level logs.
    """
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )


def extract_summary(script_path: Path) -> str:
    """Extract a short summary from a script docstring.

    Args:
        script_path: Path to a Python script.

    Returns:
        str: First line of module docstring, or fallback text.
    """
    try:
        source = script_path.read_text(encoding="utf-8")
        module_ast = ast.parse(source)
        docstring = ast.get_docstring(module_ast)
        if not docstring:
            return "No module docstring summary yet."
        return docstring.strip().splitlines()[0].strip()
    except SyntaxError:
        return "Unable to parse module for summary."
    except OSError:
        return "Unable to read script for summary."


def extract_readme_summary(directory_path: Path) -> str:
    """Extract a short summary from a directory README file.

    Args:
        directory_path: Path to a directory that may contain README content.

    Returns:
        str: First markdown paragraph line, or fallback text.
    """
    readme_candidates = [directory_path / "README.md", directory_path / "README"]
    for candidate in readme_candidates:
        if not candidate.exists():
            continue
        try:
            content = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            return "Subproject directory."

        for line in content.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped
        return "Subproject directory."
    return "Subproject directory."


def list_python_scripts(directory: Path) -> list[Path]:
    """List Python scripts in a directory.

    Args:
        directory: Directory to scan.

    Returns:
        list[Path]: Sorted `.py` files directly under the directory.
    """
    if not directory.exists():
        return []
    return sorted(
        path for path in directory.glob("*.py") if path.is_file() and path.name != "__init__.py"
    )


def list_subdirectories(directory: Path) -> list[Path]:
    """List first-level subdirectories in a directory.

    Args:
        directory: Directory to scan.

    Returns:
        list[Path]: Sorted immediate subdirectories excluding hidden folders.
    """
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_dir() and not path.name.startswith(".") and path.name != "__pycache__"
    )


def build_directory_catalog(directory: Path, link_prefix: str) -> str:
    """Build markdown catalog entries for scripts in a directory.

    Args:
        directory: Directory containing scripts.
        link_prefix: Markdown link path prefix.

    Returns:
        str: Markdown list content.
    """
    scripts = list_python_scripts(directory)
    subdirs = list_subdirectories(directory)
    if not scripts and not subdirs:
        return "- _No scripts cataloged yet._"

    lines: list[str] = []
    for subdir in subdirs:
        summary = extract_readme_summary(subdir)
        readme_path = subdir / "README.md"
        if readme_path.exists():
            relative_dir_link = f"{link_prefix}{subdir.name}/README.md"
        else:
            relative_dir_link = f"{link_prefix}{subdir.name}/"
        lines.append(f"- [`{subdir.name}/`]({relative_dir_link}) - {summary}")

    for script in scripts:
        summary = extract_summary(script)
        relative_name = f"{link_prefix}{script.name}"
        lines.append(f"- [`{script.name}`]({relative_name}) - {summary}")
    return "\n".join(lines)


def build_repo_directory_overview() -> str:
    """Build markdown overview for top-level script directories.

    Returns:
        str: Markdown list for directory READMEs.
    """
    return "\n".join(
        [
            "- [`working/`](working/README.md) - Production-ready scripts.",
            "- [`experimental/`](experimental/README.md) - Prototypes and in-progress scripts.",
            "- [`templates/`](templates/README.md) - Reusable model scripts (simple/threaded).",
            "- [`non-oci/`](non-oci/README.md) - Non-OCI scripts and projects.",
        ]
    )


def replace_marked_section(content: str, start_marker: str, end_marker: str, body: str) -> str:
    """Replace a generated markdown section bounded by markers.

    Args:
        content: Full README content.
        start_marker: Section start marker.
        end_marker: Section end marker.
        body: Markdown body to inject between markers.

    Returns:
        str: Updated README content.

    Raises:
        ValueError: If markers cannot be found.
    """
    escaped_start = re.escape(start_marker)
    escaped_end = re.escape(end_marker)
    pattern = re.compile(rf"{escaped_start}.*?{escaped_end}", re.DOTALL)
    replacement = f"{start_marker}\n{body}\n{end_marker}"
    updated, count = pattern.subn(replacement, content, count=1)
    if count != 1:
        raise ValueError(f"Missing markers: {start_marker} / {end_marker}")
    return updated


def update_target(target: dict[str, object], check_only: bool) -> tuple[bool, str | None]:
    """Update or check a single README target.

    Args:
        target: Target configuration dictionary.
        check_only: Whether to check instead of writing.

    Returns:
        tuple[bool, str | None]: (changed, error message)
    """
    readme_path = target["readme"]
    if not isinstance(readme_path, Path):
        return False, "Invalid target README path type."

    start_marker = target["start"]
    end_marker = target["end"]
    if not isinstance(start_marker, str) or not isinstance(end_marker, str):
        return False, "Invalid markers in target configuration."

    try:
        content = readme_path.read_text(encoding="utf-8")
    except OSError as exc:
        return False, f"Failed to read {readme_path}: {exc}"

    if target["name"] == "repo":
        body = build_repo_directory_overview()
    else:
        directory = target["dir"]
        link_prefix = target["link_prefix"]
        if not isinstance(directory, Path) or not isinstance(link_prefix, str):
            return False, "Invalid directory target configuration."
        body = build_directory_catalog(directory, link_prefix)

    try:
        updated = replace_marked_section(content, start_marker, end_marker, body)
    except ValueError as exc:
        return False, f"{readme_path}: {exc}"

    changed = updated != content
    if changed and not check_only:
        try:
            readme_path.write_text(updated, encoding="utf-8")
        except OSError as exc:
            return False, f"Failed to write {readme_path}: {exc}"

    return changed, None


def run_updates(targets: Iterable[dict[str, object]], check_only: bool) -> int:
    """Run updates for all targets and return process exit code.

    Args:
        targets: Target configurations.
        check_only: Whether to run in check mode.

    Returns:
        int: Exit code (0 on success, non-zero on failure).
    """
    errors: list[str] = []
    changed_targets: list[str] = []

    for target in targets:
        changed, error = update_target(target, check_only=check_only)
        name = str(target.get("name", "unknown"))
        if error:
            errors.append(error)
            continue
        if changed:
            changed_targets.append(name)

    if changed_targets:
        action = "Needs update" if check_only else "Updated"
        LOGGER.info("%s: %s", action, ", ".join(changed_targets))
    else:
        LOGGER.info("No catalog changes detected.")

    if errors:
        for error in errors:
            LOGGER.error(error)
        return 2

    if check_only and changed_targets:
        return 1

    return 0


def main() -> int:
    """Program entrypoint.

    Returns:
        int: Process exit code.
    """
    args = parse_args()
    configure_logging(args.verbose)
    check_only = args.check
    return run_updates(CATALOG_TARGETS, check_only=check_only)


if __name__ == "__main__":
    sys.exit(main())
