## Code Style

Apply `docs_dev/code-quality/code-style.md` to every touched file. Linter (`.ruff.toml`) covers many rules; guide covers
the rest.

No section comments in classes (example `# --- Public methods ---`); member order speaks.

Constants only when reused, shared, or semantic. One-use dialog title/message inline OK.

User dialog text: full words, no shorthand (`refs`), no we/us/I. Neutral, clear, professional.

Never use `# noqa` to hide lint. Fix cause: publicize needed private member, narrow broad exception, etc. `# noqa` only
when rule is provably wrong and no code change can satisfy it.
