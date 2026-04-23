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
