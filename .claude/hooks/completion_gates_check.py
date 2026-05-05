#!/usr/bin/env python3
"""Stop hook: run the project's actual check scripts to verify completion gates.

Invokes format_code, lint_code, and repo check_changelog to determine which
gates pass or fail. Only runs when Python files have been modified.

Exits 0 to allow stop, exits 2 with stderr message to force Claude to continue.
"""

import os
import re
import subprocess
import sys
from contextlib import suppress
from importlib import import_module
from pathlib import PurePosixPath

IS_WINDOWS = os.name == "nt" or sys.platform == "win32"
GATE_TIMEOUT = 120  # seconds per gate


def _get_base_branch() -> str:
    """Auto-detect the base branch using the shared utility."""
    # The hook runs from project root; tools/utils is on the same level
    tools_dir = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "utils")
    tools_path = os.path.normpath(tools_dir)
    sys.path.insert(0, tools_path)
    try:
        return import_module("detect_base_branch").detect_base_branch()
    except ImportError:
        return "main"
    finally:
        with suppress(ValueError):
            sys.path.remove(tools_path)


def _build_gates() -> list[tuple[str, list[str], list[str]]]:
    """Build the gate command list, injecting the correct base branch for changelog checks."""
    base = _get_base_branch()
    return [
        (
            "Format check",
            ["cmd", "/c", ".\\format_code.bat", "--check"],
            ["bash", "./format_code.sh", "--check"],
        ),
        (
            "Lint check",
            ["cmd", "/c", ".\\lint_code.bat", "all"],
            ["bash", "./lint_code.sh", "all"],
        ),
        (
            "Changelog check",
            ["cmd", "/c", ".\\repo.bat", "check_changelog", "-t", f"origin/{base}"],
            ["bash", "./repo.sh", "check_changelog", "-t", f"origin/{base}"],
        ),
    ]


# Only check Python files under these prefixes (ignore hooks, tools, etc.)
SOURCE_PREFIXES = ("source/",)


def get_modified_python_files():
    """Check if any source Python files were modified (staged or unstaged).

    Only includes files under SOURCE_PREFIXES to avoid triggering on
    hook scripts, tools, or other non-source Python files.
    """
    py_files = set()
    for cmd in (
        ["git", "diff", "--name-only"],
        ["git", "diff", "--cached", "--name-only"],
    ):
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
            py_files.update(
                f
                for f in result.stdout.strip().split("\n")
                if f.endswith(".py") and any(f.startswith(p) for p in SOURCE_PREFIXES)
            )
        except (OSError, subprocess.SubprocessError):
            pass
    return sorted(py_files)


def get_modified_extensions(py_files):
    """Extract unique extension names from modified file paths."""
    extensions = set()
    for f in py_files:
        parts = PurePosixPath(f).parts
        if "extensions" in parts:
            idx = parts.index("extensions")
            if idx + 1 < len(parts):
                extensions.add(parts[idx + 1])
    return sorted(extensions)


def _has_ruff_errors(output: str) -> bool:
    """Check ruff output for actual errors even when repo_lint reports 0.

    repo_lint's summary can report "0 errors" while ruff itself found unfixed
    errors. Parse the raw output for ruff's "Found N errors" line.
    """
    match = re.search(r"Found (\d+) errors?", output)
    return match is not None and int(match.group(1)) > 0


def run_gate(label, win_cmd, unix_cmd):
    """Run a gate check script. Returns (label, passed, output_snippet, full_output)."""
    cmd = win_cmd if IS_WINDOWS else unix_cmd
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT,
            check=False,
        )
        output = (result.stdout + result.stderr).strip()
        # Keep last 20 lines to avoid flooding
        lines = output.splitlines()
        snippet = "\n".join(lines[-20:]) if len(lines) > 20 else output

        passed = result.returncode == 0
        # repo_lint may return exit code 0 even when ruff found unfixable errors.
        # Double-check by parsing ruff output directly for lint gates.
        if passed and label == "Lint check" and _has_ruff_errors(output):
            passed = False

        return label, passed, snippet, output
    except subprocess.TimeoutExpired:
        output = f"Timed out after {GATE_TIMEOUT}s"
        return label, False, output, output
    except FileNotFoundError as e:
        output = f"Script not found: {e}"
        return label, False, output, output
    except OSError as e:
        output = str(e)
        return label, False, output, output


def _changelog_failure_is_preexisting(output: str, extensions: list[str]) -> bool:
    """Check if a changelog failure is only about extensions we did NOT modify.

    If `repo check_changelog` fails but none of the failing extensions overlap
    with the extensions we actually changed, the failure is pre-existing from
    committed code and should not block the agent.
    """
    # Extract extension names from the error output
    failing_exts = set()
    for line in output.splitlines():
        stripped_line = line.strip()
        # Lines like "Version has not been incremented for source/extensions/foo.bar"
        if stripped_line.startswith("Version") and "source/extensions/" in stripped_line:
            parts = stripped_line.split("source/extensions/")
            if len(parts) > 1:
                ext_name = parts[1].strip().rstrip("/")
                failing_exts.add(ext_name)

    if not failing_exts:
        return False

    modified_set = set(extensions)
    # If ALL failing extensions are outside what we modified, it's pre-existing
    return failing_exts.isdisjoint(modified_set)


def main():
    py_files = get_modified_python_files()
    if not py_files:
        sys.exit(0)

    extensions = get_modified_extensions(py_files)

    # Run all gates and collect results
    gates = _build_gates()
    passed, failed = [], []
    for label, win_cmd, unix_cmd in gates:
        gate_label, ok, snippet, output = run_gate(label, win_cmd, unix_cmd)
        if not ok and label == "Changelog check" and _changelog_failure_is_preexisting(output, extensions):
            # Pre-existing changelog issue from committed code — don't block
            passed.append((gate_label, snippet + "\n    (pre-existing, not from current changes)"))
            continue
        (passed if ok else failed).append((gate_label, snippet))

    if not failed:
        sys.exit(0)

    # Build report
    files_summary = "\n".join(f"  {f}" for f in py_files[:20])
    if len(py_files) > 20:
        files_summary += f"\n  ... and {len(py_files) - 20} more"

    passed_list = "\n".join(f"  - {gate_label}" for gate_label, _ in passed) if passed else "  (none)"
    failed_sections = []
    for label, snippet in failed:
        failed_sections.append(f"  - {label}:\n    {snippet.replace(chr(10), chr(10) + '    ')}")
    failed_list = "\n".join(failed_sections)

    print(
        f"Completion gates check failed.\n\n"
        f"Modified Python files ({len(py_files)}):\n{files_summary}\n\n"
        f"Modified extensions: {', '.join(extensions) if extensions else 'unknown'}\n\n"
        f"Gates PASSED:\n{passed_list}\n\n"
        f"Gates FAILED:\n{failed_list}\n\n"
        f"Fix the failing gates before stopping. See .agents/rules/completion-gates.md for details.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
