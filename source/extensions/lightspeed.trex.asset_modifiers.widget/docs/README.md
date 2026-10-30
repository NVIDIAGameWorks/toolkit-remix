# lightspeed.trex.asset_modifiers.widget

The **Asset Modifiers** window edits modifier settings and runs the active modifier.

## Responsibilities

- Show the registered modifiers, the source getter, and the typed inputs with the native property fields.
- Show an empty state until a provider registers a modifier.
- Submit runs with a cancellable progress popup and report the result in a notification.
- Show modifier jobs in the Job Queue with their sources.

## Non-Responsibilities

- The core resolves sources and builds graphs. Provider extensions define modifiers.
- The Stage Manager plugin owns the row action and context submenu. Both call `AssetModifierSubmitter.submit()`.

## Architecture

`AssetModifiersWidget` uses the ComfyUI Workflow panel layout. Its rows use `NativeDelegate`, with the declared
numeric bounds on drag fields. One Job Queue display adapter serves every `AssetModifierJob` subclass. The
extension depends on no ComfyUI extension.

## Use

1. Open **Window > Modifiers > Asset Modifiers**.
2. Select a modifier and a source: **Selected Prims**, **All Compatible Prims**, or **File Path Constant**.
3. Edit the inputs and click **Run Modifier**.
