## Research Resources

Use these resources when you need authoritative reference before implementing. Prefer MCP tools when available — they
return structured results faster than web pages.

### MCP Servers

See `.agents/context/project.md` → "MCP Servers" for the server list and usage directive. Servers are configured in
`.mcp.json` (canonical, project root) and mirrored to `.cursor/mcp.json`, `.vscode/mcp.json` (Copilot), and
`.windsurf/mcp.json`.

### Sub-Agent Usage

Use sub-agents to keep the main context clean and parallelize independent work. This repo has ~190 extensions — direct
tool calls are often insufficient for broad searches.

- **`Explore`** — searching across multiple extensions for patterns, usages, or existing implementations
- **`Plan`** — before any non-trivial implementation (plan must include tests per testing rule)
- **`Bash`** — long-running build or test jobs
- **`general-purpose`** — multi-step tasks needing both research and code changes

Launch independent sub-agents in the same message when research questions are independent.

### Web Documentation

| URL                                                                                         | Use for                                                                     |
|---------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| https://openusd.org/release/api/                                                            | OpenUSD C++ / Python API reference                                          |
| https://docs.omniverse.nvidia.com/kit/docs/pxr-usd-api/latest/pxr.html                      | `pxr` Python bindings — `Usd`, `Sdf`, `Gf`, `Vt`, etc.                      |
| https://docs.omniverse.nvidia.com/kit/docs/omni.ui/latest/omni.ui.html                      | `omni.ui` widget reference — all widget types, styles, events               |
| https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/kit_overview.html        | Omniverse Kit SDK overview and extension system guide                       |
| https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html | Kit Python extension testing — `AsyncTestCase`, UI test framework, coverage |

### Internal Codebase References

When implementing a pattern for the first time, use the Explore agent to find existing examples:

| What to look for                  | Where to search                               |
|-----------------------------------|-----------------------------------------------|
| A service endpoint implementation | Extensions matching `*.service`               |
| A factory plugin implementation   | Extensions matching `*.plugin.*`              |
| An event extension                | Extensions matching `lightspeed.event.*`      |
| A validator                       | `omni.flux.validator.*`                       |
| A tree/list model                 | Extensions with `.model` suffix               |
| Job queue usage                   | `omni.flux.job_queue.*` and consumers         |
| Settings declaration patterns     | Any `config/extension.toml` with `[settings]` |

### Local Documentation

Two documentation trees — use Glob/Grep to find specific files when needed:

- **`docs/`** — User-facing: UI guides, how-to articles, REST API reference, `docs/remix-glossary.md` (authoritative
  terminology)
- **`docs_dev/`** — Developer-focused: architecture, patterns, code quality, build/test. The dispatch table in
  `commands.md` links to specific pattern guides.

### Legal / Compliance

OSRB (Open Source Review Board) tickets are required for every new pip package. See
`docs_dev/patterns/pip-packages.md` → "Step 0 — License Check" for the full process, including the Confluence link for
NVIDIA employees and instructions for external contributors.
