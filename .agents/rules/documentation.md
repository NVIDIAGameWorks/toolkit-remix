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
