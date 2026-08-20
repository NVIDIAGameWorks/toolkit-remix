## Code Style

Apply `docs_dev/code-quality/code-style.md` to every touched file. Linter (`.ruff.toml`) covers many rules; guide covers
the rest.

No section comments in classes (example `# --- Public methods ---`); member order speaks.

Constants only when reused, shared, or semantic. One-use dialog title/message inline OK.

User dialog text: full words, no shorthand (`refs`), no we/us/I. Neutral, clear, professional.

Follow the pattern that the repository already uses when it fits the problem. Grep first: a construct that appears
nowhere needs a reason. Example: `sorted(mapping, key=lambda key: mapping[key])`, because `key=lambda` appears
everywhere.

Do not call a dunder when public syntax or a public API says the same thing: `mapping[key]`, never
`mapping.__getitem__(key)`. Defining a dunder on a class stays normal.

Do not keep a method whose body only forwards one call and adds nothing; fold it into its caller. A method that holds a
guard, an event contract, or a lifecycle hook is not a forwarder. A value that a subclass must supply belongs in the
member that the base class already reads: a property such as `title` or `flags`, or an attribute such as
`_DEFAULT_WIDTH` of `WorkspaceWindowBase`.

Never use `# noqa` to hide lint. Fix cause: publicize needed private member, narrow broad exception, etc. `# noqa` only
when rule is provably wrong and no code change can satisfy it.
