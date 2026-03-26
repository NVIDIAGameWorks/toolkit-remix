## Extension Documentation

Every extension must have a `docs/README.md` that describes its role, scope, and architecture without requiring the
reader to study the code.

**Required sections:** Title + summary, Responsibilities, Non-Responsibilities, Architecture (key classes and their
roles).

**Optional sections:** Usage (import snippet), Settings (carb keys + defaults), Known limitations.

The Non-Responsibilities section is as important as Responsibilities — it prevents scope creep and documents which
extension owns what.

Full template and examples: `docs_dev/architecture/extension-guide.md` → "docs/README.md Structure".
