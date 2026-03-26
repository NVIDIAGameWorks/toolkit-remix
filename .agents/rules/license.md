## License Headers

Every new Python file must begin with the SPDX Apache-2.0 license header. Read `docs_dev/code-quality/code-style.md` →
License Headers section for the exact template.

**Key directives:**

- New files: use the current year
- Existing files: do NOT change the year, even when editing
- Existing files missing the header: add it (use `git log --follow --diff-filter=A -- <file>` for the original year)
- Non-Python files (`.toml`, `.lua`, `.md`, `.rst`, `.kit`): no header required

Full template: `docs_dev/code-quality/code-style.md` → License Headers section
