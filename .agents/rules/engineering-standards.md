## Engineering Standards

Read `docs_dev/code-quality/engineering-standards.md` for full guidance. Always fix the root cause instead of hiding a
symptom.

- Do not fix at the wrong layer.
- Do not swallow exceptions.
- Do not add bypass flags instead of repairing behavior.
- Do not edit vendored Kit extension code under `_build/**/extscache/`; fix via launch config, settings, env, `.kit`,
  or extension manager.
- Do not use sleeps to paper over broken async or data flow.
- Keep components single-purpose.
- Do not use `getattr()`; use direct access, named constants, protocols, or explicit adapter/version branches.
- Avoid `hasattr()` on types you control; narrow the type or define a protocol.
