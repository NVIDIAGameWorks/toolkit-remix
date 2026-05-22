## Code Style

Apply `docs_dev/code-quality/code-style.md` to every file you write or modify. Most rules are enforced by the
linter (`.ruff.toml`) — the style guide covers what the linter cannot check.

**Do not add section comments** (e.g. `# --- Public methods ---`) to classes. Let the member ordering speak for itself.

Constants only when reused, shared, or semantic. One-use dialog title/message inline OK.

User dialog text: full words, no shorthand (`refs`), no we/us/I. Neutral, clear, professional.

Never use `# noqa` to hide lint. Fix cause: publicize needed private member, narrow broad exception, etc. `# noqa` only
when rule is provably wrong and no code change can satisfy it.
