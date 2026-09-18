# lightspeed.hydra.remix.core

Loads the HdRemix native library and exposes the renderer integration used by RTX Remix Toolkit extensions.

## Responsibilities

- Preload `HdRemix.dll` and report whether the renderer is supported.
- Cache the support state and user-facing message.
- Report local initialization timeouts with qualified display-connection guidance.
- Normalize known native support failures into actionable Toolkit guidance while preserving native diagnostics in logs.
- Provide object-picking, highlighting, and renderer configuration bindings.
- Expose process-local extern readiness without initiating renderer support polling.
- Query the runtime's tri-state DLSS Neural Rendering capability without initiating NGX initialization.

## Non-Responsibilities

- Does not initiate viewport renderer activation or support discovery.

## Architecture

- `HdRemixFinalizer` configures and preloads the native library during extension startup.
- `RemixExtern.check_support()` calls the required `hdremix_issupported_ex` export. It logs the native failure message
  and normalizes known failures, such as an incompatible NVIDIA driver, before caching the user-facing message.
- `is_remix_supported()` exposes the cached support state and message to callers. Raw native error codes remain an
  implementation detail of the support check.
- `is_remix_extern_ready()` reports when viewport-owned support discovery has finished initializing the callable
  native extern. Dependent extensions can wait on this state without starting support discovery in renderer-less
  processes.
- `get_dlss_neural_rendering_support()` queries the native runtime capability: waiting for initialization,
  unavailable, or supported. Consumers keep feature UI hidden until support is reported.
