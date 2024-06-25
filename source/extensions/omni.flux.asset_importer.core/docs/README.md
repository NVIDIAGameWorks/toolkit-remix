# Overview

Wrapper around omni.kit.asset_converter that allows for batch conversion of files from a dictionary or json file.

See `source\extensions\omni.flux.asset_importer.core\data\tests\test_config.json` for an example json config.

json options:

| Argument                                 | Default Value | Comment                                                                                                                                                      |
|------------------------------------------|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| ignore_materials                         | False         | Don't import/export materials                                                                                                                                |
| ignore_animations                        | False         | Don't import/export animations                                                                                                                               |
| ignore_camera                            | False         | Don't import/export cameras                                                                                                                                  |
| ignore_light                             | False         | Don't import/export lights                                                                                                                                   |
| single_mesh                              | False         | By default, instanced props will be export as single USD for reference. If this flag is true, it will export all props into the same USD without instancing. |
| smooth_normals                           | True          | Smoothing normals, which is only for assimp backend.                                                                                                         |
| export_preview_surface                   | False         | Imports material as UsdPreviewSurface instead of MDL for USD export                                                                                          |
| support_point_instancer                  | False         | Deprecated                                                                                                                                                   |
| embed_mdl_in_usd                         | True          | Deprecated.                                                                                                                                                  |
| use_meter_as_world_unit                  | False         | Sets world units to meters, this will also scale asset if it's centimeters model.                                                                            |
| create_world_as_default_root_prim        | True          | Creates /World as the root prim for Kit needs.                                                                                                               |
| embed_textures                           | True          | Embedding textures into output. This is only enabled for FBX and glTF export.                                                                                |
| convert_fbx_to_y_up                      | False         | Always use Y-up for fbx import.                                                                                                                              |
| convert_fbx_to_z_up                      | False         | Always use Z-up for fbx import.                                                                                                                              |
| keep_all_materials                       | False         | If it's to remove non-referenced materials.                                                                                                                  |
| merge_all_meshes                         | False         | Merges all meshes to single one if it can.                                                                                                                   |
| use_double_precision_to_usd_transform_op | False         | Uses double precision for all transform ops.                                                                                                                 |
| ignore_pivots                            | False         | Don't export pivots if assets support that.                                                                                                                  |
| disabling_instancing                     | False         | Don't export instancing assets with instanceable flag.                                                                                                       |
| export_hidden_props                      | False         | By default, only visible props will be exported from USD exporter.                                                                                           |
| baking_scales                            | False         | Only for FBX. It's to bake scales into meshes.                                                                                                               |                                                                                                            |