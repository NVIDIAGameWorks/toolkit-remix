# lightspeed.hydra.remix.core

Loads the HdRemix native library and exposes the renderer integration used by RTX Remix Toolkit extensions.

## Responsibilities

- Preload `HdRemix.dll` and report whether the renderer is supported.
- Cache the support state and user-facing message.
- Normalize known native support failures into actionable Toolkit guidance while preserving native diagnostics in logs.
- Provide object-picking, highlighting, and renderer configuration bindings.

## Architecture

- `HdRemixFinalizer` configures and preloads the native library during extension startup.
- `RemixExtern.check_support()` calls the required `hdremix_issupported_ex` export. It logs the native failure message
  and normalizes known failures, such as an incompatible NVIDIA driver, before caching the user-facing message.
- `is_remix_supported()` exposes the cached support state and message to callers. Raw native error codes remain an
  implementation detail of the support check.
