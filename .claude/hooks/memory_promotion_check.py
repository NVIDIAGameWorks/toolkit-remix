#!/usr/bin/env python3
"""Stop hook: detect changes to auto-memory and show a git-style diff for promotion review.

Compares current memory content against a cached snapshot from the last review.
If changes are detected, outputs a unified diff and updates the cache so the
next stop passes cleanly. Scans the entire memory directory recursively for
main + subagent memories.

Exits 0 to allow stop, exits 2 with stderr message to force Claude to continue.
"""

import difflib
import sys
from pathlib import Path

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_FILENAME = ".memory_cache"
MIN_LINES = 5


def get_memory_dir():
    """Derive the Claude Code auto-memory directory from the current working directory.

    Claude Code encodes project paths as directory names by replacing
    ':' and path separators with '-'.
    """
    cwd = str(Path.cwd().resolve())
    project_key = cwd.replace(":", "-").replace("\\", "-").replace("/", "-")
    return CLAUDE_PROJECTS_DIR / project_key / "memory"


def read_memory_snapshot(memory_dir):
    """Read all .md files into a single snapshot string keyed by relative path.

    Returns the snapshot string and total line count.
    """
    md_files = sorted(memory_dir.rglob("*.md"))
    if not md_files:
        return "", 0

    sections = []
    total_lines = 0
    for f in md_files:
        try:
            content = f.read_text(encoding="utf-8")
            rel = str(f.relative_to(memory_dir))
            sections.append(f"=== {rel} ===\n{content}")
            total_lines += len(content.splitlines())
        except Exception:
            pass

    return "\n\n".join(sections), total_lines


def compute_diff(old_content, new_content):
    """Compute a unified diff between old and new memory snapshots."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile="memory (last reviewed)",
            tofile="memory (current)",
            n=3,
        )
    )
    return "".join(diff)


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    memory_dir = get_memory_dir()
    if not memory_dir.exists():
        sys.exit(0)

    cache_file = memory_dir / CACHE_FILENAME

    current, total_lines = read_memory_snapshot(memory_dir)
    if not current or total_lines < MIN_LINES:
        sys.exit(0)

    cached = ""
    if cache_file.exists():
        try:
            cached = cache_file.read_text(encoding="utf-8")
        except Exception:
            pass

    if current == cached:
        sys.exit(0)

    diff = compute_diff(cached, current)
    if not diff:
        sys.exit(0)

    # Update cache immediately so the next stop passes cleanly
    try:
        cache_file.write_text(current, encoding="utf-8")
    except Exception:
        pass

    print(
        f"Auto-memory has changed since last review.\n\n"
        f"{diff}\n"
        f"Review the diff above. If any additions are stable, confirmed learnings "
        f"(not session-specific notes), ask the user if they'd like to promote "
        f"them to the appropriate docs_dev/ file.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
