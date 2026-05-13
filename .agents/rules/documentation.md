## Documentation

Feature/significant change -> update docs.

### Placement

- `docs_dev/` = developer docs: architecture, patterns, build/test, standards, internals.
- `docs/` = user docs: UI guides, how-to, REST API, `docs/remix-glossary.md` terminology.
- Extension `docs/README.md` = extension role/scope/architecture.
- `.agents/` = agent directives only; link `docs_dev/` for details.

### When

- New extension/major feature -> `docs_dev/patterns/` or `docs_dev/architecture/`; user-facing -> `docs/howto/` or
  `docs/toolkitinterface/`.
- New pattern/convention -> relevant `docs_dev/`.
- New command/UI workflow -> `docs/howto/`.
- API change -> source docstrings; API pages auto-generated.
- Bug changes documented behavior -> update affected page.

### Rules

- No duplicate content across `docs/`, `docs_dev/`, `.agents/`; cross-reference.
- Use existing page if possible; new page only when no fit.
- Built docs: descriptive relative links, no raw file paths. `.agents/` may use paths.
- Reader-first: action first, short caveats, field-tested claims.
- Commands single-line copy-pasteable. Windows cmd env recipe: `set VAR=1&& command`; no space before `&&`, no quotes.
- Do not require Script Editor snippets or threading boilerplate when workflow works without them.
- No run-specific evidence in reference docs: sizes, timings, counts -> PR/chat.
- Avoid versioned paths unless version load-bearing; prefer globs/unversioned refs.
- Tables only when scan value beats prose.
- Match existing `docs_dev/tools/debugging.md` voice: short intro, numbered recipes, short asides.
