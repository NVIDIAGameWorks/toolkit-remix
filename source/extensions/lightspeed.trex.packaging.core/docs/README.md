# lightspeed.trex.packaging.core

## Overview

Core extension used to package mods for distribution.

The schema accepted by the core requires the following format:

```python
"""
The context name to use for the packaging stage. Should be a unique context name.
"""
context_name: str

"""
The mod layer paths should be ordered by opinion strength where the strongest layer is first.
All mod layers found in a given project should be in found in the list, including external mod dependencies
"""
mod_layer_paths: List[Path]

"""
A list of layers to package.
Must at least contain the strongest mod layer found in `mod_layer_paths` or the packaging process will quick return.
"""
selected_layer_paths: List[Path]

"""
The directory where the packaged mod should be stored.
WARNING: The directory will be emptied prior to packaging the mod.
"""
output_directory: Path

"""
How external dependencies should be handled during packaging.
- ModPackagingMode.REDIRECT: Creates the smallest package and keeps dependency references pointed at installed mods.
- ModPackagingMode.IMPORT: Creates a standalone package and preserves the layered USD output.
- ModPackagingMode.FLATTEN: Creates a standalone package, flattens the packaged result into one root layer, and only keeps assets still
  referenced by the flattened output.
"""
packaging_mode: ModPackagingMode = ModPackagingMode.FLATTEN

"""
How the packaged root USD layer should be written.
- None: Keeps the packaged root layer extension from the source mod layer.
- UsdExtensions.USD: Writes the packaged root layer with the `.usd` extension.
- UsdExtensions.USDA: Writes the packaged root layer as human-readable `.usda`.
- UsdExtensions.USDC: Writes the packaged root layer as binary `.usdc`.
"""
output_format: UsdExtensions | None = UsdExtensions.USD

"""
The display name used for the mod in the RTX Remix Runtime.
"""
mod_name: str

"""
The mod version. Used when building dependency lists.
"""
mod_version: str

"""
Optional text used to describe the mod in more details.
"""
mod_details: Optional[str] = None
```

Packaging is non-destructive: it only mutates temporary packaging layers and the packaged output directory. The source
project root layer and project sublayers are left unchanged during packaging. The only exception is the unresolved
reference fix workflow, where the user explicitly chooses to replace or remove broken references in the project.
