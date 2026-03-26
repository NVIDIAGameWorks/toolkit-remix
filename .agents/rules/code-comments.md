## Code Comments & Docstrings

Apply to every function, method, and class you write or modify. Read `docs_dev/code-quality/code-style.md` for format
and examples.

**Key directives that change every method signature:**

- All public and protected members (`_foo`) require a Google-style docstring
- Only name-mangled private members (`__foo`) may omit a docstring
- Summary line: one sentence ending with a period — describe *what it does*, not *how*
- Only comment the *why*, never the *what* — if a comment explains what the code does, rewrite the code instead

Full rules and examples: `docs_dev/code-quality/code-style.md` → Inline Comments and Docstrings sections
