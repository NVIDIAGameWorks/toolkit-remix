# Game Setup Tab

![GameSetup](../data/images/rtxremix_034.png)


<table>
  <tr>
   <td><strong>Ref</strong>
   </td>
   <td><strong>Option</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>1
   </td>
   <td>Step 1: UI Textures
   </td>
   <td>This feature allows you to tag all textures known to be part of the UI. This will enable Remix to skip them when Path Tracing and render a complete UI view on top.
   </td>
  </tr>
  <tr>
   <td>2
   </td>
   <td>Step 1.2: Worldspace UI Textures (optional)
   </td>
   <td>Like Step 1, this section allows you to tag UI textures, but this time for world-space rendering (as opposed to screen-space) – think user interface elements that exist in the 3D game world with the characters, not as a flat overlay on the screen.
   </td>
  </tr>
  <tr>
   <td>3
   </td>
   <td>Step 2: Parameter Tuning
   </td>
   <td>This feature allows you to specify the coordinate system used in the game, to help ensure Remix can match the rendering correctly, and that captures look correct with the proper up direction in the Remix App. You can also enable shader-based vertex capture here and adjust its parameters.  <em>(See the Parameter Tuning Chart Below)</em>
   </td>
  </tr>
  <tr>
   <td>4
   </td>
   <td>Step 3: Sky Textures (optional)
   </td>
   <td>This feature allows you to adjust the look of the Path Traced sky, as well as tune compatibility parameters to allow for better sky detection.
   </td>
  </tr>
  <tr>
   <td>5
   </td>
   <td>Step 4: Ignore Textures (optional)
   </td>
   <td>This feature allows you to ignore certain objects by texture entirely.
   </td>
  </tr>
  <tr>
   <td>6
   </td>
   <td>Step 5: Ignore Lights (optional)
   </td>
   <td>This feature allows you to ignore certain lights by texture entirely.
   </td>
  </tr>
  <tr>
   <td>7
   </td>
   <td>Step 6: Particle Textures (optional)
   </td>
   <td>This feature allows you to tag certain textures as belonging to particles. This enables Remix to detect these particles properly and render them correctly in Path Tracing.
   </td>
  </tr>
  <tr>
   <td>8
   </td>
   <td>Step 7: Decal Textures (optional)
   </td>
   <td>Like Step 7, but for dynamic decals. Dynamic decals are used for effects like bullet holes that appear during gameplay. Static decals are parts of the map.
   </td>
  </tr>
  <tr>
   <td>9
   </td>
   <td>Step 7.1: Dynamic Decal Textures
   </td>
   <td>Like Step 7, but for dynamic decals. Dynamic decals are used for effects like bullet holes that appear during gameplay. Static decals are parts of the map.
   </td>
  </tr>
  <tr>
   <td>10
   </td>
   <td>Step 8.1: Legacy Cutout Textures
   </td>
   <td>This feature allows you to tag certain textures as alpha tested (“cutout”) even if the original game used alpha blending to represent surfaces with “holes.” For a Path Tracing renderer there is a big difference in whether alpha testing or blending is used, so this tagging can help these surfaces render correctly.
   </td>
  </tr>
  <tr>
   <td>11
   </td>
   <td>Step 8.2: Water Textures
   </td>
   <td>Like Decals, tagging Terrain textures can help Remix render terrain correctly.
   </td>
  </tr>
  <tr>
   <td>12
   </td>
   <td>Step 8.3: Water Textures (optional)
   </td>
   <td>Like Decals and Terrain, tagging water textures can help Remix render water correctly.
   </td>
  </tr>
  <tr>
   <td>13
   </td>
   <td>Step 9: Material Options (optional)
   </td>
   <td>This feature allows you to adjust the properties of the Remix default Path Tracing material. This material gets used if there is no material replacement found for a given mesh or texture in the game (this happens when you have no mod loaded for example or decide to turn replacements off). You can also set modifiers for PBR materials in general – whether default or loaded from a Mod – that can adjust their general properties like roughness or color scale.  <em>(See the Material Options Chart Below)</em>
   </td>
  </tr>
</table>

## Parameter Tuning Options


![GameSetup](../data/images/rtxremix_032.png)


<table>
  <tr>
   <td><strong>Ref</strong>
   </td>
   <td><strong>Option</strong>
   </td>
   <td><strong>RTX Option</strong>
   </td>
   <td><strong>Default Value</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>1
   </td>
   <td>Scene Unit Scale
   </td>
   <td>rtx.sceneScale
   </td>
   <td>1.000
   </td>
   <td>Defines the ratio of rendering unit (1cm) to game unit, i.e. sceneScale = 1cm / GameUnit.
   </td>
  </tr>
  <tr>
   <td>2
   </td>
   <td>Scene Z-Up Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>3
   </td>
   <td>Scene Left-Handed Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Unchecked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>4
   </td>
   <td>Unique Object search Distance
   </td>
   <td>rtx.uniqueObjectDistance
   </td>
   <td>300.000
   </td>
   <td><!--- Needs Description --->[cm]
   </td>
  </tr>
  <tr>
   <td>5
   </td>
   <td>Skybox Transformer Enabled Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>1.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>6
   </td>
   <td>Skybox Transformer Scale
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>7
   </td>
   <td>Shader-based Vertex Capture Checkbox
   </td>
   <td>rtx.useVertexCapture
   </td>
   <td>Unchecked
   </td>
   <td>When enabled, it injects code into the original vertex shader to capture final shaded vertex positions. Is useful for games using simple vertex shaders, that still also set the fixed function transform matrices.
   </td>
  </tr>
  <tr>
   <td>8
   </td>
   <td>Vertex Color Strength
   </td>
   <td>rtx.vertexColorStrength
   </td>
   <td>0.6
   </td>
   <td>A scalar to apply to how strong vertex color influence should be on materials.
<p>
A value of 1 indicates that it should be fully considered (though do note the texture operation and relevant parameters still control how much it should be blended with the actual albedo color), a value of 0 indicates that it should be fully ignored.
   </td>
  </tr>
</table>



## Material Options (optional)


![GameSetup](../data/images/rtxremix_033.png)


<table>
  <tr>
   <td><strong>Ref</strong>
   </td>
   <td><strong>Option</strong>
   </td>
   <td><strong>RTX Option</strong>
   </td>
   <td><strong>Default Value</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>1
   </td>
   <td colspan="3" ><strong>Legacy Material Defaults</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>2
   </td>
   <td>Use Albedo/Opacity Texture (if present) Checkbox
   </td>
   <td>rtx.legacyMaterial.useAlbedoTextureIfPresent
   </td>
   <td>Checked
   </td>
   <td>A flag to determine if an "albedo" texture (a qualifying color texture) from the original application should be used if present on non-replaced "legacy" materials.
   </td>
  </tr>
  <tr>
   <td>3
   </td>
   <td>Albedo
   </td>
   <td>rtx.legacyMaterial.albedoConstant
   </td>
   <td>R: 255 G: 255 B: 255
   </td>
   <td>The default albedo constant to use for non-replaced "legacy" materials. Should be a color in sRGB colorspace with gamma encoding.
   </td>
  </tr>
  <tr>
   <td>4
   </td>
   <td>Opacity
   </td>
   <td>rtx.legacyMaterial.opacityConstant
   </td>
   <td>1.0
   </td>
   <td>The default opacity constant to use for non-replaced "legacy" materials. Should be in the range 0 to 1.
   </td>
  </tr>
  <tr>
   <td>5
   </td>
   <td>Emissive Color
   </td>
   <td>rtx.legacyMaterial.emissiveColorConstant
   </td>
   <td>R: 0, G: 0, B: 0
   </td>
   <td>The default emissive color constant to use for non-replaced "legacy" materials. Should be a color in sRGB colorspace with gamma encoding.
   </td>
  </tr>
  <tr>
   <td>6
   </td>
   <td>Emissive Intensity
   </td>
   <td>rtx.legacyMaterial.emissiveIntensity
   </td>
   <td>0.0
   </td>
   <td>The default emissive intensity to use for non-replaced "legacy" materials.
   </td>
  </tr>
  <tr>
   <td>7
   </td>
   <td>Roughness
   </td>
   <td>rtx.legacyMaterial.roughnessConstant
   </td>
   <td>0.7
   </td>
   <td>The default perceptual roughness constant to use for non-replaced "legacy" materials. Should be in the range 0 to 1.
   </td>
  </tr>
  <tr>
   <td>8
   </td>
   <td>Metallic
   </td>
   <td>rtx.legacyMaterial.metallicConstant
   </td>
   <td>0.1
   </td>
   <td>The default metallic constant to use for non-replaced "legacy" materials. Should be in the range 0 to 1.
   </td>
  </tr>
  <tr>
   <td>9
   </td>
   <td>Anisotropy
   </td>
   <td>rtx.legacyMaterial.anisotropy
   </td>
   <td>0.0
   </td>
   <td>The default roughness anisotropy to use for non-replaced "legacy" materials. Should be in the range -1 to 1, where 0 is isotropic.
   </td>
  </tr>
  <tr>
   <td>10
   </td>
   <td colspan="3" ><strong>PBR Material Modifiers</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>11
   </td>
   <td colspan="3" ><strong>Opaque</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>12
   </td>
   <td>Albedo Scale Slider
   </td>
   <td>rtx.opaqueMaterial.albedoScale
   </td>
   <td>1.0
   </td>
   <td>A scale factor to apply to all albedo values in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>13
   </td>
   <td>Albedo Bias Slider
   </td>
   <td>rtx.opaqueMaterial.albedoBias
   </td>
   <td>0.0
   </td>
   <td>A bias factor to add to all albedo values in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>14
   </td>
   <td>Roughness Scale Slider
   </td>
   <td>rtx.opaqueMaterial.roughnessScale
   </td>
   <td>1.0
   </td>
   <td>A scale factor to apply to all roughness values in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>15
   </td>
   <td>Roughness Bias Slider
   </td>
   <td>rtx.opaqueMaterial.roughnessBias
   </td>
   <td>0.0
   </td>
   <td>A bias factor to add to all roughness values in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>16
   </td>
   <td>Normal Strength Slider
   </td>
   <td>rtx.translucentMaterial.normalIntensity
   </td>
   <td>1.0
   </td>
   <td>An arbitrary strength scale factor to apply when decoding normals in the translucent material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>17
   </td>
   <td>Enable dual-layer animated water normal Checkbox
   </td>
   <td>rtx.opaqueMaterial.layeredWaterNormalEnable
   </td>
   <td>Checked
   </td>
   <td>A flag indicating if layered water normal should be enabled or disabled.
<p>
Note that objects must be properly classified as animated water to be rendered with this mode.
   </td>
  </tr>
  <tr>
   <td>18
   </td>
   <td>Layered Motion Direction Sliders
   </td>
   <td>rtx.opaqueMaterial.layeredWaterNormalMotion
   </td>
   <td>-0.250, 0.0
   </td>
   <td>A vector describing the motion in the U and V axes across a texture to apply for layered water.
<p>
Only takes effect when layered water normals are enabled (and an object is properly classified as animated water).
   </td>
  </tr>
  <tr>
   <td>19
   </td>
   <td>Layered Motion Scale  Slider
   </td>
   <td>rtx.opaqueMaterial.layeredWaterNormalMotionScale
   </td>
   <td>9.000
   </td>
   <td>A scale factor applied to the layered water normal motion vector.
<p>
Only takes effect when layered water normals are enabled (and an object is properly classified as animated water).
   </td>
  </tr>
  <tr>
   <td>20
   </td>
   <td>LOD bias  Slider
   </td>
   <td>rtx.opaqueMaterial.layeredWaterNormalLodBias
   </td>
   <td>5.000
   </td>
   <td>The LoD bias to use when sampling from the normal map on layered water for the second layer of detail.
<p>
This value typically should be greater than 0 to allow for a more blurry mip to be selected as this allows for a low frequency variation of normals to be applied to the higher frequency variation from the typical normal map.
<p>
Only takes effect when layered water normals are enabled (and an object is properly classified as animated water).
   </td>
  </tr>
  <tr>
   <td><strong>21</strong>
   </td>
   <td colspan="3" ><strong>Translucent</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>22
   </td>
   <td>Transmit. Color Scale Slider
   </td>
   <td>rtx.translucentMaterial.transmittanceColorScale
   </td>
   <td>1.0
   </td>
   <td>A scale factor to apply to all transmittance color values in the translucent material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>23
   </td>
   <td>Transmit. Color Bias Slider
   </td>
   <td>rtx.translucentMaterial.transmittanceColorBias
   </td>
   <td>0.0
   </td>
   <td>A bias factor to add to all transmittance color values in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td>24
   </td>
   <td>Normal Strength Slider
   </td>
   <td>rtx.opaqueMaterial.normalIntensity
   </td>
   <td>1.0
   </td>
   <td>An arbitrary strength scale factor to apply when decoding normals in the opaque material. Should only be used for debugging or development.
   </td>
  </tr>
  <tr>
   <td><strong>25</strong>
   </td>
   <td colspan="3" ><strong>PBR Material Overrides</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>26</strong>
   </td>
   <td colspan="3" ><strong>Opaque</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>27
   </td>
   <td>Enable Thin-Film Layer Checkbox
   </td>
   <td>rtx.legacyMaterial.alphaIsThinFilmThickness
   </td>
   <td>Unchecked
   </td>
   <td>A flag to determine if the alpha channel from the albedo source should be treated as thin film thickness on non-replaced "legacy" materials.
   </td>
  </tr>
  <tr>
   <td><strong>28</strong>
   </td>
   <td colspan="3" ><strong>Translucent</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>29
   </td>
   <td>Enable Diffuse Layer Checkbox
   </td>
   <td>rtx.translucentMaterial.enableDiffuseLayerOverride
   </td>
   <td>Unchecked
   </td>
   <td>A flag to force the diffuse layer on the translucent material to be enabled. Should only be used for debugging or development.
   </td>
  </tr>
</table>

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
