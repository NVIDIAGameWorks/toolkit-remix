# Alpha Test / Blending

Alpha Test / Blending allows you to toggle alpha testing and blending in the Remix Toolkit.

![AlphaTest](../../data/images/rtxremix_027.png)

| **Ref** | **Option**                        | **RTX Option**                             | **Default Value** | **Description**                                                                                                                               |
|---------|-----------------------------------|--------------------------------------------|-------------------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| 1       | Render Alpha Blended Checkbox     | rtx.enableAlphaBlend                       | Checked           | Enable rendering alpha blended geometry, used for partial opacity and other blending effects on various surfaces in many games.               |
| 2       | Render Alpha Tested Checkbox      | rtx.enableAlphaTest                        | Checked           | Enable rendering alpha tested geometry, used for cutout style opacity in some games.                                                          |
| 3       | Enable Triangle Culling Checkbox  |                                            | Checked           | <!--- Needs Description --->                                                                                                                  |
| 4       | Emissive Blend Override Checkbox  | rtx.enableEmissiveBlendEmissiveOverride    | Checked           | Override typical material emissive information on draw calls with any emissive blending modes to emulate their original look more accurately. |
| 5       | Emissibe Blend Override Intensity | rtx.emissiveBlendOverrideEmissiveIntensity | 0.2               | The emissive intensity to use when the emissive blend override is enabled. Adjust this if particles for example look overly bright globally.  |
| 6       | Particle Softness                 | rtx.particleSoftnessFactor                 | 0.050             | Multiplier for the view distance that is used to calculate the particle blending range.                                                       |

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
