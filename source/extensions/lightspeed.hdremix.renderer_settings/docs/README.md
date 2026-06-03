# lightspeed.hdremix.renderer_settings

Exposes live HdRemix renderer toggles in the Kit Preferences window. Settings changed here can be pushed to the running dxvk-remix runtime via `hdremix_set_configvar` — no re-capture required. For the integrator, whether a push actually happens is gated by the **Override Capture Value** checkbox (see below).

## Preferences

Settings are exposed as a dedicated **Edit > Preferences > HdRemix Renderer** page registered as a sibling of Kit's built-in "Viewport" page. The extension also stubs Kit's "Viewport" page content with a one-line redirect notice (its built-in settings — Auto Frame on stage open, viewport-toolbar visibility, Area Select Occluded Objects — are no-ops against the customized Remix viewport). The Viewport page is kept registered (only its `build` is wrapped) so the viewport menubar's "Preferences" navigation, which looks the page up by title, keeps working.

### Integrate Indirect Illumination Mode

Selects the indirect lighting integrator. Label strings match the dxvk-remix runtime overlay (section "Indirect Illumination", combo "Integrate Indirect Illumination Mode"). Maps to dxvk-remix's `rtx.integrateIndirectMode`:

| Option | rtx.integrateIndirectMode value |
|---|---|
| Importance Sampled | `0` |
| ReSTIR GI | `1` |
| RTX Neural Radiance Cache | `2` (default) |

> **Note:** Changing the integrator forces the dxvk-remix graphics preset to Custom (`rtx.graphicsPreset=4`) so the User-layer write takes effect. The original preset is not restored.

### Override Capture Value

Controls whether the global integrator setting wins over each loaded capture's preset, and gates whether the integrator is pushed to the runtime at all.

- **Off (default)**: the extension does **not** push the integrator — not on stage open, and not when you change the combo above. The loaded capture's preset value applies, and the combo only records your preference for the next time this checkbox is on.
- **On**: the global value is pushed to `rtx.integrateIndirectMode` on stage open, when you change the combo, and the moment you enable this checkbox mid-session — overriding the capture's preset.

## Settings

All settings are persistent (survive restarts).

| Setting path | Type | Default | Description |
|---|---|---|---|
| `/persistent/exts/lightspeed.hdremix.renderer_settings/integrateIndirectMode` | int | `2` | GI integrator mode (matches dxvk-remix's IntegrateIndirectMode enum) |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/overrideCaptureIntegrator` | bool | `false` | Whether the integrator above overrides each loaded capture's preset on stage open |
