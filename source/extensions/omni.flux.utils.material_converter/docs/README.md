# Material Converter

This is a simple utility to convert materials from a given shader to another shader.

## Public API

- `MaterialConverterCore`: runs one converter against a material prim on a stage.
- `get_converter_builder(input_subidentifier)`: returns the registered builder for an input shader
  identifier from `SupportedShaderInputs` (`OmniPBR`, `OmniGlass`, `UsdPreviewSurface`, `gltf_material`,
  or `None`). Returns `None` for an unknown identifier.
- `ConverterBuilderBase.select_output(shader_prim)`: selects the Aperture output shader for one input
  shader prim. The glTF builder selects `AperturePBR_Translucent` for a positive transmission factor
  and `AperturePBR_Opacity` otherwise. The opacity shader disables legacy alpha state. `BLEND` enables
  alpha blending, `MASK` uses a greater-or-equal alpha test with `alphaCutoff` (default 0.5), and
  `OPAQUE` disables blending and alpha testing.
- `TEXTURE_SOURCE_CHANNEL_CUSTOM_DATA_KEY` (`remix:sourceChannel`, in `utils`): custom data that a
  converter writes on a texture input when the source texture packs several channels. The value names the
  channel to extract (`G` for glTF roughness, `B` for glTF metallic). The asset pipeline extracts that channel
  and removes the marker when it replaces the texture.
- `TEXTURE_SOURCE_FACTOR_CUSTOM_DATA_KEY` (`remix:sourceFactor`, in `utils`): custom data that the glTF
  converter writes on a texture input when the glTF factor (base color, emissive, roughness, metallic) is not 1,
  because `AperturePBR` has no input that multiplies a factor with a texture. The value is one float for a mono
  channel or three or four floats for a color texture. The asset pipeline bakes the factor into the texture and
  removes the marker when it replaces the texture.
