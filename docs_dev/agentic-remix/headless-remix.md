# Headless RTX Remix

A long-lived RTX Remix process serving the Toolkit's existing MCP and REST APIs without an
editor window. MCP clients and HTTP scripts can use the loaded services programmatically.

## Why headless

The headless app provides:

- an MCP server that prefers `127.0.0.1:18014/mcp/`, agent-facing
- a REST API that requests `127.0.0.1:8011` for direct HTTP calls
- a process that stays alive until you Ctrl-C the console

> **What is exposed.** This app serves the Toolkit's tools — project open/close, layer
> management, asset-reference replacement, texture overrides, and asset ingestion via
> `/ingestcraft/*`. The available operations come from the loaded service extensions; inspect
> their request and response schemas at `/openapi.json`.

## Launching

```powershell
.\_build\windows-x86_64\release\lightspeed.app.trex.stagecraft.headless.bat
```

Run the launcher from a built checkout. Wait for the MCP readiness message in the Toolkit log:

```text
SERVICE_READY service=mcp host=127.0.0.1 port=18014
```

The process runs without an editor window. Stop it with Ctrl-C in its console. The
launcher is [`lightspeed.app.trex.stagecraft.headless.bat`](../../source/shell/lightspeed.app.trex.stagecraft.headless.bat),
with a [shell-script counterpart](../../source/shell/lightspeed.app.trex.stagecraft.headless.sh).
The build copies the launcher for its platform into the release directory.

### What the launcher passes

| Flag | Purpose |
|---|---|
| `--no-window` | Suppress the main editor window. |
| `--/app/window/hideUi=1` | Hide the app UI. |
| `--/exts/omni.kit.renderer.core/present/enabled=0` | Do not try to present frames anywhere. |
| `--/app/extensions/excluded/0='lightspeed.trex.app.setup'` | Exclude the editor-app setup extension inherited from the base app. |
| `--/app/extensions/excluded/1='omni.kit.splash'`<br>`--/app/extensions/excluded/2='omni.kit.window.splash'` | Exclude the splash extensions. The app also clears the deferred dependency list described below. |
| `--/renderer/multiGpu/enabled=0` | Disable multi-GPU rendering. |
| `--/app/asyncRendering=0` | Disable asynchronous rendering. |
| `--/app/file/ignoreUnsavedOnExit=1` | Disable Kit's unsaved-file exit prompt. Save modified layers before exiting. |

The launcher does not set `--exec` or `--/app/quitAfter`. Kit continues running while its
MCP and REST servers accept requests.

## Two ports

| Port | Surface | Use it for |
|---|---|---|
| 18014 (preferred) | **MCP over Streamable HTTP** | Agent tool calls. Connect with an MCP client, `.mcp.json`, or the MCP Python SDK. |
| 8011 (requested) | **REST** (uvicorn / FastAPI) | Direct HTTP calls and the OpenAPI schema. |

The MCP server builds its tool list from the REST app's OpenAPI schema at startup. The
`/stagecraft/*` and `/ingestcraft/*` operations become `remix_<operation_id>` tools.
The MCP route filter excludes named infrastructure, API-documentation, and UI-automation
endpoints. Restart the Toolkit after changing which service extensions load so the MCP tool
list reflects their routes.

The headless app configures both servers to bind loopback and does not configure authentication.
Keep these endpoints local.

On Windows, `%LOCALAPPDATA%\NVIDIA\RTX Remix\mcp.json` records the actual MCP and REST
endpoints after MCP starts listening. See the
[discovery manifest](../../source/extensions/lightspeed.trex.mcp.core/docs/README.md#discovery-manifest)
for its fields and stale-file checks.

If MCP port `18014` is occupied, the headless app tries `18015` through `18019` in order, just as
the windowed Toolkit does. If all six ports are unavailable, MCP startup logs an error and stops.
Find `MCP_PORT_FALLBACK` in the Toolkit log and use its `endpoint=http://...`
value to connect. Wait for `SERVICE_READY service=mcp` with the selected host and port before
sending requests; see [Finding the MCP server](../../docs/howto/learning-mcp.md#finding-the-mcp-server-information).
The REST transport can also select another port when `8011` is occupied; check the Toolkit log
for its listening address before making HTTP requests.

Check the REST service (substitute its selected port if fallback occurred):

```powershell
# Inspect the loaded REST routes and their schemas.
curl.exe http://127.0.0.1:8011/openapi.json

# Read the current layer tree after opening a project. Keep the route's trailing slash.
curl.exe http://127.0.0.1:8011/stagecraft/layers/
```

## Connecting a client

See [Using AI Agents with MCP](../../docs/howto/learning-mcp.md#connecting-ai-agents-to-mcp)
for client setup and [the developer overview](overview.md#related-documents) for the repository's
client configurations.

## Saving

Save each modified layer explicitly with `remix_save_layer`, passing its `layer_id`, before
closing the project or stopping the process. The REST equivalent is
`POST /stagecraft/layers/{layer_id}/save`.

The headless app does not include the prompt-based `lightspeed.event.autosave` extension.
It does include save-related event handlers such as `lightspeed.event.save_root_mod`, which
can save the root replacement layer when another layer is saved. These handlers do not
replace an explicit save of each layer the client edits.

## What is loaded, and what is not

The app inherits `lightspeed.app.trex.base`, including its renderer and UI dependencies.
The launcher excludes `lightspeed.trex.app.setup` and the splash extensions. The app also
clears `lightspeed.dependencies.deferred_dependencies` and lists four event exclusions:
`generate_thumbnail`, `layers_cleanup`, `switch_to_replacement`, and `validate_project`.

Its explicit stage-manager dependencies are the core, factory, context, filter, listener,
tree, and interaction extensions. The full dependency and settings lists are in
[`lightspeed.app.trex.stagecraft.headless.kit`](../../source/apps/lightspeed.app.trex.stagecraft.headless.kit).
