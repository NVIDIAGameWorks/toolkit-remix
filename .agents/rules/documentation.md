## Documentation Updates

When implementing a feature or making significant changes, update the relevant documentation.

**Where content belongs:**

- **`docs_dev/`** — Technical, developer-focused: architecture, patterns, build/test, code standards, extension
  internals. If it helps someone *build or maintain* the toolkit, it goes here.
- **`docs/`** — User-focused: UI guides, how-to articles, REST API reference, glossary. If it helps someone *use* the
  toolkit, it goes here.

**When to update:**

- New extension or major feature → add/update the relevant `docs_dev/patterns/` or `docs_dev/architecture/` page; if
  user-facing, also update `docs/howto/` or `docs/toolkitinterface/`
- New pattern or convention → add to the appropriate `docs_dev/` file
- New command or UI workflow → update `docs/howto/`
- New or changed API → update docstrings in the source code; API reference pages are auto-generated
- Bug fix that changes documented behavior → update the affected page

**Rules:**

- **Never duplicate content** across `docs/`, `docs_dev/`, and `.agents/` — cross-reference instead. `docs_dev/` is the
  canonical source for developer knowledge. `.agents/` files should reference `docs_dev/` for details and only contain
  agent-specific directives (what to do, not how the underlying process works).
- Keep extension `docs/README.md` files up to date (see extension-docs rule)
- Use the existing page structure; only create a new page if no existing page covers the topic
- **Linking in docs**: use descriptive link text and relative paths, never raw file paths. Agent rules
  (`.agents/`) may use file paths since they are not built by Sphinx.

**Style (for `docs_dev/` and `docs/` pages):**

- Write for the reader who needs to do the thing. Lead with the action (e.g. "Press F8, tick X, press F5"),
  not with an architecture overview of the system.
- Commands must be single-line and copy-pasteable. For Windows cmd.exe env-var + command recipes, use
  `set VAR=1&& command` — no space before `&&` (otherwise the trailing space is captured into the value and
  most Windows programs won't recognise `"1 "` as enabled) and no quotes around `VAR=value` (the quoted
  `set "VAR=1" && command` form silently drops the variable when relayed through `cmd /c` from Git Bash).
  Don't split a recipe across multiple code blocks.
- Don't require the reader to paste code to use a tool. If a workflow works without Script Editor snippets or
  threading boilerplate (e.g. manual `ensure_thread()` calls), don't document those as steps — at most leave
  them as a footnote for edge cases.
- Keep caveats short and actionable. A one-sentence "don't do X" beats a paragraph explaining why the toggle
  is confusing.
- Prefer field-tested claims over theoretical ones. `.pyi` docstrings and reference pages often describe the
  strictest invariants; if empirical evidence shows the tool works in the common case without those steps,
  document the common case.
- Cut verification evidence. Capture sizes, event counts, and timing numbers from a specific run belong in
  PR descriptions or chat, not in a reference doc.
- Avoid pinning version strings in paths unless the version is load-bearing. Prefer globs (`ext-name*`) or
  unversioned references so the doc doesn't rot on the next bump.
- Prefer prose over tables when a table has only 2-3 rows or the columns are all prose. Tables earn their keep
  when readers need to scan many rows.
- Mirror the voice of existing pages like `docs_dev/tools/debugging.md` — narrative intro, numbered recipes,
  short asides.
