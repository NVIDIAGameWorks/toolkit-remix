# Agentic Remix — Design Overview

How an AI agent drives RTX Remix and where the service implementation lives.

Read this before any other document in this directory.

---

## 1. What it is

An agent — Claude Code, a local model, anything that speaks MCP — connects to a running RTX Remix
Toolkit and edits a mod by calling tools. The Toolkit reads and writes the project's USD through
its existing REST services.

```text
 user  ──▶  agent with modding skill  ──MCP──▶  RTX Remix Toolkit
```

The agent reaches the Toolkit over MCP, which fronts the REST API that writes the mod's USD.
[How a tool comes to exist](#3-how-a-tool-comes-to-exist) has that path in full.

This guide covers the MCP server, REST services, headless launcher and modding skill implemented
in this repository.

---

## 2. The service stack
**RTX Remix serves MCP from the Toolkit.** [`lightspeed.app.trex.base.kit`](../../source/apps/lightspeed.app.trex.base.kit) enables
`lightspeed.trex.service.core` and `lightspeed.trex.mcp.core`. The Toolkit serves MCP
over Streamable HTTP, preferring `127.0.0.1:18014/mcp/` with fallback limited to ports `18014–18019`.
On Windows, it publishes the selected endpoints in a per-user
[discovery manifest](../../source/extensions/lightspeed.trex.mcp.core/docs/README.md#discovery-manifest).
[Finding the MCP server](../../docs/howto/learning-mcp.md#finding-the-mcp-server-information) explains how to find the
selected endpoint. Its tools are the `/stagecraft/*` operations —
project lifecycle, layers, asset references, texture overrides — served by four `.service`
extensions, plus the `/ingestcraft/*` ingestion routes.

`omni.flux.service.factory` owns `ServiceBase` and the service plugin registry. Both app hosts
use these existing services.

**The tool manifest is narrower than the route list.** `mcp.core` drops the transport's own
health, readiness, status and asyncapi endpoints, OpenAPI metadata endpoints, and the root-level
UI-automation endpoints matched by `_CURATED_ROUTE_MAPS`. The remaining REST operations become
tools, including reads.

The curation is a **deny-list, not an allow-list**: a capability that lands a new route prefix
becomes a tool without also having to edit `mcp.core`.

### It runs in the GUI too

Dependencies propagate from `trex.base`, so the **windowed Toolkit serves MCP and REST as well** —
headless is a second host for the same stack, not the only one. Two consequences:

- **Never write "headless" into anything a model reads.** Tool descriptions and
  the published skill are shared by both hosts.
- **The source app dependencies enable MCP in both hosts.** `trex.base` declares `mcp.core`,
  and `stagecraft.headless.kit` also declares it directly. Wait for the server's readiness log
  before connecting.

---

## 3. How a tool comes to exist

```text
   AGENT  (MCP client)
     │  MCP over Streamable HTTP — 127.0.0.1:18014/mcp/
     ▼
   lightspeed.trex.mcp.core
     FastMCP.from_fastapi(app, route_maps=_CURATED_ROUTE_MAPS)
     mcp.mount("remix", rest_api_mcp)
     │ reflects the active REST schema
     ▼
   lightspeed.trex.service.core
     mounts StageCraftService and IngestCraftService
     │ resolves service classes through omni.flux.service.factory
     ▼
   ServiceBase classes registered by .service extensions
     │ route handlers delegate to Toolkit core extensions
     ▼
   Toolkit core extensions / omni.kit.commands
     │
     ▼
   OpenUSD stage and layers  →  save layer to disk
```

`StageCraftService` mounts `ProjectManagerService`, `LayerManagerService`,
`AssetReplacementsService` and `TextureReplacementsService`. `IngestCraftService` mounts
`MassValidatorService`. These services supply the project, layer, asset, texture and ingestion
operations. **`mcp.core` declares no REST route.** It reflects the active FastAPI app's schema.

**Nothing in this repository registers an MCP tool by hand.** The transformation is entirely
schema-driven:

```text
 @self.router.get(...)  →  FastAPI  →  /openapi.json  →  FastMCP.from_fastapi
     operation_id  ──────────────────────────────────►  the tool's name
     description=  ──────────────────────────────────►  what the model reads
     Pydantic request/response models  ──────────────►  the JSON schema
```

- **`description=` is a prompt, not a docstring.** It is the only thing telling a model when to
  reach for the tool. Write it for the model.
- **`operation_id` is API surface.** Renaming one is a breaking change for every agent and every
  published skill.

---

## 4. Route registration

`CoreService` reads its `services` setting, resolves each class through the service factory and
registers its router. The default entries are `StageCraftService` with the default USD context
and `IngestCraftService` with the `ingestcraft` context. An unresolved service name logs an error
and is skipped.

The separate package tree under
[`service.core/routes/`](../../source/extensions/lightspeed.trex.service.core/lightspeed/trex/service/core/routes/__init__.py)
contains no endpoints: `ROUTE_SERVICES` is empty, and its `agentic_enabled` registration setting
defaults to `false`. The existing StageCraft and IngestCraft services are independent of that
setting.

[Implementing REST Service Endpoints](../patterns/services.md) documents the service class,
factory registration and router mounting patterns used by this repository.

---

## 5. The published Agent Skill

MCP supplies *tools*. A skill supplies *instructions*. The
{download}`RTX Remix Modding Agent Skill <../../skills/rtx-remix-modding/SKILL.md>` teaches a general
coding agent how to use Remix and holds the behavioural rules. It is written by hand.

[Using the bundled modding skill](../../docs/howto/learning-mcp.md#bundled-modding-skill)
describes the installation layout and client discovery requirements.

Agents use skill descriptions to select which skill to load. Repository wrappers point to
the published `SKILL.md`, whose prerequisites apply before any edit. Descriptions select the
skill; they do not load its supporting reference files. A Markdown link alone does not put the
linked content into the agent's context.

`SKILL.md` explicitly instructs the agent to read the
{download}`model replacement and asset-reference recipes <../../skills/rtx-remix-modding/references/tool-mode.md>`
before those operations. These detailed tool sequences support autonomous skill use; they are
not MCP prompts or client slash commands.

Why each behavioural rule is worded the way it is — including the incidents that produced them —
is in the {download}`agent skill rule rationale <../../.agents/rules/agent-skill-rules.md>`.
Read it before trimming `SKILL.md`.

**The skill describes only what actually ships.** A rule about a tool belongs in the merge request
that introduces that tool, together with the test that pins it — not written ahead of time.

---

## 6. What the repo covers

- `mcp.core` exposes the curated REST operations as MCP tools.
- StageCraft services expose project lifecycle, layers, asset references and texture overrides.
- IngestCraft exposes the ingestion queue through `MassValidatorService`.
- `stagecraft.headless.kit` and its launchers run the service stack without a window.
- The published modding skill includes model replacement and asset-reference recipes and an
  evaluation suite.

---

## Related documents

The repository's MCP client configurations include a `remix` server entry:
[Claude Code](../../.mcp.json), [Cursor](../../.cursor/mcp.json),
[VS Code](../../.vscode/mcp.json), [Windsurf](../../.windsurf/mcp.json), and
[Codex](../../.codex/config.toml). These settings are separate from bundled skill discovery.

- [Headless RTX Remix](headless-remix.md) — running the headless app, and its limitations
- [Using AI Agents with MCP](../../docs/howto/learning-mcp.md) — pointing an MCP
  client at a running server
- [Implementing REST Service Endpoints](../patterns/services.md) — the general `ServiceBase` /
  REST service pattern in this repo
- [`lightspeed.trex.service.core`](../../source/extensions/lightspeed.trex.service.core/docs/README.md)
  — what the extension owns, its `routes/` layout and every setting it reads
