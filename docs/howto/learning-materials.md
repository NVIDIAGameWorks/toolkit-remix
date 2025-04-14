# Setting Up Material Replacements

Similar to asset replacements, materials can be replaced to enhance a game's visual fidelity. Older games often used
baked lighting and lower-resolution textures, which may not appear optimal in RTX Remix. To improve the game's
appearance and fully utilize the RTX Remix Runtime's path tracing capabilities, materials can be replaced with
higher-resolution textures and physically based materials.

```{warning}
**All textures must be ingested into the project directory before they can be used in a mod.**

Refer to the [Ingesting Assets](learning-ingestion.md) section for information on asset ingestion.
```

## Replacing an Asset's Texture

1. **Panel Access:** Navigate to the "Asset Replacements" tab and locate the "Material Properties" panel.
2. **Mesh Selection:** Select the mesh for which the texture is to be replaced. This can be done by clicking on the mesh
   in the viewport or selecting it from the Stage Manager.

   ```{tip}
   If no material properties are displayed:

    1. Verify that a **mesh** is selected in the Selection Panel. A reference or XForm may be selected instead.
    2. Captured meshes may lack assigned materials. In this case, replace the original reference with a new one.
   ```

3. **Texture Properties Modification:** Within the Material Properties panel, expand the "Base Color" section. Replace
   the texture by clicking the "Browse" button next to the "Diffuse Texture" field. This process applies similarly to
   the "Normal Map Texture" and other texture properties.
4. **Texture Set Assignment:** To assign a texture set (albedo, normal, roughness, etc.), click the "Assign Texture Set"
   button at the top of the Material Properties panel or drag and drop the textures onto the panel. A dialog will
   appear, attempting to automatically identify and map the various material inputs.

## Handling Animated Materials

Working with animated textures requires a few additional steps:

1. **Frame Capture:** Reduce the game's framerate to capture each frame of the animated texture.
2. **Anchor Texture Implementation:**
    * Generate a series of anchor or stand-in textures for each animation frame.
    * Render these textures in a test level to capture their hashes.
3. **Alt+X Developer Menu Utilization:**
    * Access the material setup tab in the Alt+X developer menu.
    * Enable "preserve discarded textures" to retain all hashes for each frame in the material menu.
4. **Hash List Creation:** Compile a list of all hashes obtained from the preserved frames in the material menu.
5. **USDA Manual Replacement:** Replace these hashes through manual editing within a layer's USDA file.

### Animated Materials Using a Sprite Sheet

To integrate animations from a sprite sheet, the following parameters must be specified:

1. The number of rows
2. The number of columns
3. The desired frames per second

After setting these values, ensure that all materials are configured to utilize sprite sheet materials.

The spritesheet should be organized from left to right and top to bottom, as shown in the following example:

![Sprite Sheet Example](../data/images/sprite_sheet_example.png)

## Understanding Material Properties

### Parallax Occlusion Mapping

Parallax Occlusion Mapping (POM) is a technique employed in RTX Remix to enhance the perceived depth and realism of
surfaces. It simulates pixel displacement based on a height map, creating the illusion of intricate surface details.

#### Parallax Occlusion Mapping for Displacement

Displacement encompasses techniques that make simple geometry appear more complex. In RTX Remix, Parallax Occlusion
Mapping achieves this effect.

#### Pixel Depth Calculation

In Remix, the apparent depth of displacement is determined by five factors, calculated as follows:

`(height_map_pixel * (displace_in + displace_out) - displace_in) * displacementFactor * UV_to_world`

* `Height_map_pixel`: A black pixel is displaced to max_depth, while a white pixel is displaced to max_height.
* `displace_in`: A material property that defines the maximum displacement below the original surface.
* `displace_out`: A material property that defines the maximum displacement above the original surface.
* `rtx.displacement.displacementFactor`: A global RtxOption primarily for debugging (recommended value: 1.0).
* `UV_to_world`: The UV density of the surface (the number of world units per UV tile).

For example, for a wall panel repeating every 1.5 meters, a black pixel appears 1.5 \* `displace_in` meters behind the
wall, and a white pixel appears 1.5 \* `displace_out` meters in front of the wall.

Useful calculations:

`total_height = displace_out + displace_in`: The total displacement range (before displacementFactor or UV scaling).

`neutral_height = displace_in / total_height`: The height_map value for no displacement.

#### Comparison with Substance Designer

In Substance Designer, a black pixel on the height map is 1 unit \* `height_scale` deep, with the default preview mesh
being 100x100 units.

#### Adjusting displace_in for Consistency

* To align the displacement depth in Remix with Substance Designer's preview, adjust `displace_in` as follows:
  `displace_in = height_scale / 100`.
* This ensures consistent displacement scaling between Remix and Substance Designer's default preview mesh.
* If outward displacement is desired, `displace_in + displace_out` should equal `height_scale / 100`.

**Custom Mesh Considerations**

For custom meshes in Substance Designer, the adjustment factor for `displace_in` and `displace_out` may require
fine-tuning based on the mesh's specific UV density. Substance Designer does not account for UV density in depth
calculations, so instead of dividing by 100, divide by the custom mesh's UV density.

### Translucency

Translucency is managed during the ingestion process. Materials with "translucent," "glass," or "trans" in their name
are automatically converted to translucent materials.

#### Automatic Conversion during Ingestion

* Materials containing "translucent," "glass," or "trans" in their name are automatically converted to translucent
  during ingestion.
* While an asset is selected in the viewport, access the "material properties" panel.
* Use the three-line menu in the top right of the panel to convert a material to translucent or opaque.

#### Manual Conversion (If Ingestion Fails)

* Select the mesh to convert to translucent or opaque.
* In Asset Replacements, locate "Material Properties."
* Use the hamburger menu in "Material" and select "Create Material Override (Translucent)."

### Emissive Elements

**Emissive Textures:** To make parts of an asset emit light, go to the "emissive" tab, enable "Enable Emission," and
assign the Emissive Mask map texture. Adjust the Emissive Intensity as needed.

### Subsurface Scattering

Subsurface Scattering (SSS) simulates light penetration through solid objects. It is described by a BSSRDF model, an
extension of the BRDF model that assumes light enters and exits at the same surface point. SSS is used to render
realistic translucent objects like skin, wax, and marble, where light scattering is more pronounced than in opaque
objects.

To configure SSS, set the following parameters in Subsurface:

* `Transmittance Color`: The base color of the SSS surface, analogous to the diffuse albedo color for diffuse materials.
  A texture map can also be used.
* `Subsurface Scattering Radius`: The distance (mean free path) that light travels within the SSS object for each color
  channel. Larger values increase scattering and create a tail-like effect. A texture map can also be used.
* `Subsurface Scattering Scale`: A scale factor that controls the overall SSS intensity.
* `Subsurface Scattering Max Scale`: The maximum scattering distance. Samples exceeding this value are clamped.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
