# lightspeed.hdremix.renderer_settings

Exposes live HdRemix renderer controls in **Edit > Preferences > HdRemix Renderer**. Settings changed here are persisted in carb settings and can be pushed to the running dxvk-remix runtime through `hdremix_set_configvar` without re-capturing.

## Responsibilities

- Own global renderer settings and synchronize them with the running dxvk-remix runtime.

## Non-Responsibilities

- Does not author per-material DLSS NR control masks; material property widgets and MDL schemas own them.

## Architecture

- `HdRemixRendererExtension`: registers the preferences page, wraps Kit's **Viewport** page, and owns bridge lifetime.
- `HdRemixRendererPreferencePage`: builds the preferences UI and writes user edits to persistent carb settings.
- `DLSS_SETTINGS`: defines persistent paths, runtime keys, defaults, and value types for every DLSS NR control.
- `DlssSettingsPanel`: builds the shared, synchronized controls used by Preferences and the viewport pane.
- `HdRemixSettingsBridge`: waits for viewport-owned HdRemix initialization, inherits DLSS NR controls from capture config, and forwards subsequent user edits.
- The renderer bridge publishes DLSS Neural Rendering availability for all Toolkit UI hosts.

## Preferences

Settings are exposed as a dedicated **Edit > Preferences > HdRemix Renderer** page registered as a sibling of Kit's built-in "Viewport" page. The extension also stubs Kit's "Viewport" page content with a one-line redirect notice (its built-in settings — Auto Frame on stage open, viewport-toolbar visibility, Area Select Occluded Objects — are no-ops against the customized Remix viewport). The Viewport page is kept registered (only its `build` is wrapped) so the viewport menubar's "Preferences" navigation, which looks the page up by title, keeps working. The DLSS 3D-Guided Neural Generation settings are also available in the viewport **Render Settings** pane.

### DLSS 3D-Guided Neural Generation [Experimental]

Controls the global DLSS 3D-Guided Neural Generation settings. The group remains hidden until the running dxvk-remix runtime reports support. A missing feature DLL, unsupported platform, or initialization failure keeps it hidden.


| Control | Runtime config variable | Default |
|---|---|---|
| DLSS 3D-Guided Neural Generation | `rtx.dlssNeuralRendering.enable` | `false` |
| Model | `rtx.dlssNeuralRendering.model` | `Model A` |
| Structure Intensity | `rtx.dlssNeuralRendering.structuralStrength` | `0.7` |
| Tone Intensity | `rtx.dlssNeuralRendering.toneStrength` | `0.3` |
| Enable Auto Mask | `rtx.dlssNeuralRendering.useAutoMask` | `false` |
| Character Intensity | `rtx.dlssNeuralRendering.skinStructureStrength` | `0.5` |

The collapsed **Advanced Settings** section contains:

| Control | Runtime config variable | Default |
|---|---|---|
| Highlight Recovery | `rtx.dlssNeuralRendering.enableHighlightRecovery` | `true` |
| Highlight Recovery Thresholds | `rtx.dlssNeuralRendering.highlightRecoveryThresholds` | `[1.0, 8.0, 0.75, 0.99]` |
| Volumetric Improvement | `rtx.dlssNeuralRendering.enableVolumetricControlMask` | `true` |

Model supports `Model A`, `Model B`, and `Model C`, represented by runtime values `0`, `1`, and `2`. Intensity values are clamped to `[0, 1]`. Highlight recovery thresholds are clamped to `[0, 32]`. These controls are global renderer controls; per-material control-mask values are authored elsewhere. The generic `rtx.dlssNeuralRendering.intensity` value remains synchronized with capture and runtime configuration at a default of `1.0`, but is not exposed in the UI.

When a capture is imported, its current-schema runtime DLSS NR values seed the Toolkit controls without being written back to the renderer. Pre-release captures that use the retired `style` key are reset to the release defaults, which are then queued for the renderer. Subsequent user edits are applied live; edits made before HdRemix is ready are queued individually. The bridge observes renderer readiness without initiating support discovery in renderer-less consumers.

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

Settings survive restarts, but a loaded capture's resolved DLSS NR values take precedence and reseed the corresponding controls.

| Setting path | Type | Default | Description |
|---|---|---|---|
| `/persistent/exts/lightspeed.hdremix.renderer_settings/enableDlssNeuralRendering` | bool | `false` | Enables DLSS 3D-Guided Neural Generation globally |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingModel` | int | `0` | Model: 0: Model A, 1: Model B, 2: Model C |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingIntensity` | float | `1.0` | Internal global effect intensity synchronized with capture configuration |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingToneIntensity` | float | `0.3` | Global tone intensity |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingStructureIntensity` | float | `0.7` | Global structure intensity |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/enableDlssNeuralRenderingAutoMask` | bool | `false` | Enables Auto Mask |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingCharacterIntensity` | float | `0.5` | Auto Mask character intensity |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/enableDlssNeuralRenderingHighlightRecovery` | bool | `true` | Enables highlight recovery |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/dlssNeuralRenderingHighlightRecoveryThresholds` | float4 | `[1.0, 8.0, 0.75, 0.99]` | Highlight recovery thresholds |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/enableDlssNeuralRenderingVolumetricImprovement` | bool | `true` | Enables volumetric improvement |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/integrateIndirectMode` | int | `2` | GI integrator mode (matches dxvk-remix's IntegrateIndirectMode enum) |
| `/persistent/exts/lightspeed.hdremix.renderer_settings/overrideCaptureIntegrator` | bool | `false` | Whether the integrator above overrides each loaded capture's preset on stage open |
