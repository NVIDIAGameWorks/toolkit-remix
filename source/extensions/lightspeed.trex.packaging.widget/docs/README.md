# lightspeed.trex.packaging.widget

Widget for packaging RTX Remix mods for distribution.

## Features

- Package mod files and dependencies
- Configure mod metadata (name, version, details)
- Select output directory
- Select layers to include
- Choose a packaging mode: redirect dependencies, import dependencies, or flatten into one layer
- Choose an output extension for the packaged root layer: preserve extensions, `usd`, `usda`, or `usdc`
- Explain packaging-mode and output-format side effects through the in-widget info popup
- Keep packaging non-destructive for the source project; only the packaged output and temporary packaging layers are modified
- Compress DDS textures into RTX IO `.pkg` files for optimized streaming

## RTX IO Packaging

The **RTX IO PACKAGING** section adds RTX IO controls to the existing packaging
flow:

- **Packaging mode** enables post-packaging RTX IO compression for normalized
  DDS textures in the packaged output.
- **Delete packaged DDS files after compression** removes only the packaged DDS
  files after successful RTX IO compression.
- **Split package files** maps to the RTX IO packager's `--split` option with
  `1 GB`, `2 GB`, `4 GB`, `8 GB`, and `16 GB` presets.

The widget relies on the shared `lightspeed.trex.rtxio.core` extension for
RTX IO tooling and split-size definitions.

### Enabling RTX IO in-game

Add the following line to your mod's `rtx.conf`:

```ini
rtx.io.enabled = True
```
