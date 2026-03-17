#!/usr/bin/env python3
"""Stop hook: run the project's actual check scripts to verify completion gates.

Invokes format_code, lint_code, and repo check_changelog to determine which
gates pass or fail. Only runs when Python files have been modified.

Exits 0 to allow stop, exits 2 with stderr message to force Claude to continue.
"""

import os
import subprocess
import sys
from pathlib import PurePosixPath

IS_WINDOWS = os.name == "nt" or sys.platform == "win32"
GATE_TIMEOUT = 120  # seconds per gate

# Each gate: (label, windows_cmd, unix_cmd)
# Commands are run from the project root (hook cwd).
# Windows: use .\ prefix so cmd /c finds scripts in cwd, not PATH.
GATES = [
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
        ["cmd", "/c", ".\\repo.bat", "check_changelog"],
        ["bash", "./repo.sh", "check_changelog"],
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
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            py_files.update(
                f
                for f in result.stdout.strip().split("\n")
                if f.endswith(".py") and any(f.startswith(p) for p in SOURCE_PREFIXES)
            )
        except Exception:
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
    import re

    match = re.search(r"Found (\d+) errors?", output)
    return match is not None and int(match.group(1)) > 0


def run_gate(label, win_cmd, unix_cmd):
    """Run a gate check script. Returns (label, passed, output_snippet)."""
    cmd = win_cmd if IS_WINDOWS else unix_cmd
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=GATE_TIMEOUT,
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

        return label, passed, snippet
    except subprocess.TimeoutExpired:
        return label, False, f"Timed out after {GATE_TIMEOUT}s"
    except FileNotFoundError as e:
        return label, False, f"Script not found: {e}"
    except Exception as e:
        return label, False, str(e)


def main():
    py_files = get_modified_python_files()
    if not py_files:
        sys.exit(0)

    extensions = get_modified_extensions(py_files)

    # Run all gates and collect results
    passed, failed = [], []
    for label, win_cmd, unix_cmd in GATES:
        gate_label, ok, snippet = run_gate(label, win_cmd, unix_cmd)
        (passed if ok else failed).append((gate_label, snippet))

    if not failed:
        sys.exit(0)

    # Build report
    files_summary = "\n".join(f"  {f}" for f in py_files[:20])
    if len(py_files) > 20:
        files_summary += f"\n  ... and {len(py_files) - 20} more"

    passed_list = "\n".join(f"  - {l}" for l, _ in passed) if passed else "  (none)"
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
