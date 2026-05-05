## Code Style

Apply `docs_dev/code-quality/code-style.md` to every file you write or modify. Most rules are enforced by the
linter (`.ruff.toml`) — the style guide covers what the linter cannot check.

**Do not add section comments** (e.g. `# --- Public methods ---`) to classes. Let the member ordering speak for itself.

**Never use `# noqa` to suppress lint errors.** Fix the underlying issue instead. If a private member needs to be
accessed from another module, make it public. If a broad exception catch is flagged, narrow the exception type.
`# noqa` is an absolute last resort — only acceptable when the lint rule is provably wrong and no code change can
satisfy it.
