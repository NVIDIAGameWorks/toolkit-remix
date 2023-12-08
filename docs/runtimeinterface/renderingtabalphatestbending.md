# Alpha Test / Blending

Alpha Test / Blending allows you to toggle alpha testing and blending in the Remix Toolkit.


![AlphaTest](../data/images/rtxremix_027.png)


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
   <td>Render Alpha Blended Checkbox
   </td>
   <td>rtx.enableAlphaBlend
   </td>
   <td>Checked
   </td>
   <td>Enable rendering alpha blended geometry, used for partial opacity and other blending effects on various surfaces in many games.
   </td>
  </tr>
  <tr>
   <td>2
   </td>
   <td>Render Alpha Tested Checkbox
   </td>
   <td>rtx.enableAlphaTest
   </td>
   <td>Checked
   </td>
   <td>Enable rendering alpha tested geometry, used for cutout style opacity in some games.
   </td>
  </tr>
  <tr>
   <td>3
   </td>
   <td>Enable Triangle Culling Checkbox
   </td>
   <td>
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>4
   </td>
   <td>Emissive Blend Override Checkbox
   </td>
   <td>rtx.enableEmissiveBlendEmissiveOverride
   </td>
   <td>Checked
   </td>
   <td>Override typical material emissive information on draw calls with any emissive blending modes to emulate their original look more accurately.
   </td>
  </tr>
  <tr>
   <td>5
   </td>
   <td>Emissibe Blend Override Intensity
   </td>
   <td>rtx.emissiveBlendOverrideEmissiveIntensity
   </td>
   <td>0.2
   </td>
   <td>The emissive intensity to use when the emissive blend override is enabled. Adjust this if particles for example look overly bright globally.
   </td>
  </tr>
  <tr>
   <td>6
   </td>
   <td>Particle Softness
   </td>
   <td>rtx.particleSoftnessFactor
   </td>
   <td>0.050
   </td>
   <td>Multiplier for the view distance that is used to calculate the particle blending range.
   </td>
  </tr>
</table>