## License Headers

Every new Python file needs SPDX Apache-2.0 header. Exact template:
`docs_dev/code-quality/code-style.md` License Headers.

- New Python files: current year
- Existing Python files: never change year when editing
- Existing Python missing header: add it; original year from `git log --follow --diff-filter=A -- <file>`
- Non-Python (`.toml`, `.lua`, `.md`, `.rst`, `.kit`): no header
