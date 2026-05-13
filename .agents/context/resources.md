## Research Resources

Need authority? Matching MCP first when available. Else state unavailable; use `docs_dev`, official docs, repo patterns.
Owners: MCP -> `.agents/context/project.md`; specialists -> `.agents/rules/subagents.md`; docs ->
`.agents/rules/documentation.md`; pip -> `.agents/commands/add-pip-dep.md`.

### Web Docs

- OpenUSD API: https://openusd.org/release/api/
- `pxr` Python (`Usd`, `Sdf`, `Gf`, `Vt`): https://docs.omniverse.nvidia.com/kit/docs/pxr-usd-api/latest/pxr.html
- `omni.ui` widgets/styles/events: https://docs.omniverse.nvidia.com/kit/docs/omni.ui/latest/omni.ui.html
- Kit overview/ext system: https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/kit_overview.html
- Kit tests (`AsyncTestCase`, UI, coverage): https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html

### Internal Codebase References

New pattern? Agent-oriented code nav first: semantic discovery, overviews, symbols, refs/callsites. Raw search only for
exact strings, generated output, logs.

| What to look for                  | Where to search                               |
|-----------------------------------|-----------------------------------------------|
| A service endpoint implementation | Extensions matching `*.service`               |
| A factory plugin implementation   | Extensions matching `*.plugin.*`              |
| An event extension                | Extensions matching `lightspeed.event.*`      |
| A validator                       | `omni.flux.validator.*`                       |
| A tree/list model                 | Extensions with `.model` suffix               |
| Job queue usage                   | `omni.flux.job_queue.*` and consumers         |
| Settings declaration patterns     | Any `config/extension.toml` with `[settings]` |
