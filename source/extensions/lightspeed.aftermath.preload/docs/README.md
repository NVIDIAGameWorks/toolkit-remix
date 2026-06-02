# RTX Remix Aftermath Preload

This extension preloads HdRemix's `GFSDK_Aftermath_Lib.x64.dll` before Kit GPU Foundation initializes so DXVK/HdRemix can own Nsight Aftermath GPU crash dump generation.

The extension is enabled by default in RTX Remix Toolkit app configs. Its default mode disables Kit-owned Aftermath and enables the DXVK/HdRemix Aftermath setup.

## Settings

| Setting | Default | Purpose |
| --- | --- | --- |
| `/exts/lightspeed.aftermath.preload/enabled` | `true` | Top-level automation gate. When `false`, the extension leaves Kit and DXVK/HdRemix Aftermath settings unchanged. |
| `/exts/lightspeed.aftermath.preload/kitAftermathEnabled` | `false` | Controls Kit-owned Aftermath via `/renderer/debug/aftermath/enabled`. |
| `/exts/lightspeed.aftermath.preload/hdremixAftermathEnabled` | `true` | Controls HdRemix Aftermath setup: `DXVK_CONFIG_FILE` setup and HdRemix DLL preload. |
| `/exts/lightspeed.aftermath.preload/configureDxvk` | `true` | Controls whether HdRemix setup sets `DXVK_CONFIG_FILE` when the environment variable is unset. |
| `/exts/lightspeed.aftermath.preload/dxvkConfigPath` | empty | Optional override. Can point to `dxvk.conf` or to a directory containing it. |
| `/exts/lightspeed.aftermath.preload/dllPath` | empty | Optional override. Can point to `GFSDK_Aftermath_Lib.x64.dll` or to a directory containing it. |

DXVK config selection order is:

1. Existing `DXVK_CONFIG_FILE` environment variable.
2. `/exts/lightspeed.aftermath.preload/dxvkConfigPath`, if set.
3. `dxvk.conf` in the launch working directory.
4. `data/dxvk.conf` from this extension.

The extension fallback config only enables `dxvk.enableAftermath`. Keep mod/game visual tuning in that mod or game's own `dxvk.conf`.

## Notes

Aftermath is crash instrumentation, not a crash workaround. Verification details and expected log assertions belong in tests so this README can stay focused on the extension's purpose and configuration surface.
