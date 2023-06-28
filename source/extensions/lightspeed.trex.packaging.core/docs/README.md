# Overview

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
Whether the reference dependencies taken from external mods should be redirected or copied in this mod's package
during the packaging process.
- Redirecting will allow the mod to use the installed mod's dependencies so updating a dependency will be as simple
  as to install the updated dependency.
- Copying will make sure the mod is completely standalone so no other mods need to be installed for this mod to be
  loaded successfully."
"""
redirect_external_dependencies: Optional[bool] = True

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
