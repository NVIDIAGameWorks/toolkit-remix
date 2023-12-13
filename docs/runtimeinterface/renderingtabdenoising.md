# Denoising

Denoising allows you to toggle denoising on and off, as well as tune denoising parameters in detail. Denoising is a critical part of modern Path Tracing renderers and turning it off entirely has mainly educational value. Adjusting the individual settings may be beneficial for image quality or compatibility, depending on the game and mod in question.


![Denoising](../data/images/rtxremix_026.png)


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
   <td>Denoising Enabled Checkbox
   </td>
   <td>rtx.useDenoiser
   </td>
   <td>Checked
   </td>
   <td>Enables usage of denoiser(s) when set to true, otherwise disables denoising when set to false.
<p>
Denoising is important for filtering the raw noisy ray traced signal into a smoother and more stable result at the cost of some potential spatial/temporal artifacts (ghosting, boiling, blurring, etc).
<p>
Generally should remain enabled except when debugging behavior which requires investigating the output directly, or diagnosing denoising-related issues.
   </td>
  </tr>
  <tr>
   <td>2
   </td>
   <td>Reference Mode Checkbox
   </td>
   <td>rtx.useDenoiserReferenceMode
   </td>
   <td>Unchecked
   </td>
   <td>Enables the reference "denoiser" when set to true, otherwise uses the standard denoiser when set to false. Note this requires the denoiser to be enabled to function.
<p>
The reference denoiser allows for a reference multi-sample per pixel contribution to accumulate which should converge slowly to the ideal result the renderer is working towards.
<p>
Useful for analyzing quality differences in various denoising methods, post-processing filters, or for more accurately comparing subtle effects of potentially biased rendering techniques which may be hard to see through usual noise and filtering.
<p>
Also useful for higher quality artistic renders of a scene beyond what is possible in real time.
   </td>
  </tr>
  <tr>
   <td><strong>3</strong>
   </td>
   <td colspan="3" ><strong>Settings</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>4
   </td>
   <td>Separate Primary Direct/Indirect Denoiser Checkbox
   </td>
   <td>
   </td>
   <td>Unchecked
   </td>
   <td>Seperatethe Primary Direct and Indirect layers into their own individual option levels
   </td>
  </tr>
  <tr>
   <td>5
   </td>
   <td>Reset History on Setting Change Checkbox
   </td>
   <td>rtx.resetDenoiserHistoryOnSettingsChange
   </td>
   <td>Unchecked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>6
   </td>
   <td>Replace Direct Specular HitT with Indirect Specular HitT Checkbox
   </td>
   <td>rtx.replaceDirectSpecularHitTWithIndirectSpecularHitT
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>7
   </td>
   <td>Pre-NRD Filter HitT Signal Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Unchecked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>8
   </td>
   <td>Filter Fireflies in Disocclusion Checkbox
   </td>
   <td>
   </td>
   <td>Unchecked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>9
   </td>
   <td>Use Virtual Shading Normals Checkbox
   </td>
   <td>rtx.useVirtualShadingNormalsForDenoising
   </td>
   <td>Checked
   </td>
   <td>A flag to enable or disable the usage of virtual shading normals for denoising passes.
<p>
This is primarily important for anything that modifies the direction of a primary ray, so mainly PSR and ray portals as both of these will view a surface from an angle different from the "virtual" viewing direction perceived by the camera.
<p>
This can cause some issues with denoising due to the normals not matching the expected perception of what the normals should be, for example normals facing away from the camera direction due to being viewed from a different angle via refraction or portal teleportation.
<p>
To correct this, virtual normals are calculated such that they always are oriented relative to the primary camera ray as if its direction was never altered, matching the virtual perception of the surface from the camera's point of view.
<p>
As an aside, virtual normals themselves can cause issues with denoising due to the normals suddenly changing from virtual to "real" normals upon traveling through a portal, causing surface consistency failures in the denoiser, but this is accounted for via a special transform given to the denoiser on camera ray portal teleportation events.
<p>
As such, this option should generally always be enabled when rendering with ray portals in the scene to have good denoising quality.
   </td>
  </tr>
  <tr>
   <td>10
   </td>
   <td>Adaptive Resolution Denoising Checkbox
   </td>
   <td>rtx.adaptiveResolutionDenoising
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>11
   </td>
   <td>Adaptive Accumulation Checkbox
   </td>
   <td>rtx.adaptiveAccumulation
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>12
   </td>
   <td>Demodulate Roughness Checkbox
   </td>
   <td>rtx.demodulate.demodulateRoughness
   </td>
   <td>Checked
   </td>
   <td>Demodulate roughness to improve specular details.
   </td>
  </tr>
  <tr>
   <td>13
   </td>
   <td>Roughness sensitivity
   </td>
   <td>rtx.demodulate.demodulateRoughnessOffset
   </td>
   <td>0.100
   </td>
   <td>Strength of roughness demodulation, lower values are stronger.
   </td>
  </tr>
  <tr>
   <td>14
   </td>
   <td>Direct Light Boiling Filter Checkbox
   </td>
   <td>rtx.demodulate.enableDirectLightBoilingFilter
   </td>
   <td>Checked
   </td>
   <td>Boiling filter removes direct light samples when its luminance is too high.
   </td>
  </tr>
  <tr>
   <td>15
   </td>
   <td>Direct Light Boiling Threshold
   </td>
   <td>rtx.demodulate.directLightBoilingThreshold
   </td>
   <td>5.0
   </td>
   <td>Remove direct light samples when its luminance is higher than the average one multiplied by this threshold .
   </td>
  </tr>
  <tr>
   <td>16
   </td>
   <td>Enhance BSDF Detail Under DLSS Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>17
   </td>
   <td>Indirect Light Enhancement Mode Dropdown
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Normal Difference
   </td>
   <td>Choices: Laplacian & Normal Difference
   </td>
  </tr>
  <tr>
   <td>18
   </td>
   <td>Direct/Indirect Light Sharpness
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.70, 1.00
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>19
   </td>
   <td>Direct/Indirect Light Max Strength
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>10.00, 1.50
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>20
   </td>
   <td>Pixel Highlight Reuse Strength
   </td>
   <td>rtx.pixelHighlightReuseStrength
   </td>
   <td>0.500
   </td>
   <td>The specular portion when we reuse the last frame's pixel value.
   </td>
  </tr>
  <tr>
   <td>21
   </td>
   <td>Indirect Light Min Sharpen Roughness
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.300
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>22
   </td>
   <td>Use Post Filter Checkbox
   </td>
   <td>rtx.postfx.enable
   </td>
   <td>Checked
   </td>
   <td>Enables post-processing effects.
   </td>
  </tr>
  <tr>
   <td>23
   </td>
   <td>Post Filter Threshold
   </td>
   <td>rtx.postFilterThreshold
   </td>
   <td>0.300
   </td>
   <td>Clamps a pixel when its luminance exceeds x times of the average.
   </td>
  </tr>
  <tr>
   <td><strong>24</strong>
   </td>
   <td colspan="3" ><strong>Noise Mix</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>25
   </td>
   <td>Noise Mix Ratio Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.200
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>26
   </td>
   <td>Noise NdotV Power Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.500
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>27
   </td>
   <td>Noise Clamp Low Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.500
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>28
   </td>
   <td>Noise Clamp High Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>2.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>29</strong>
   </td>
   <td colspan="3" ><strong>Primary Direct/Indirect Light Denoiser</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>30
   </td>
   <td>NRD Version
   </td>
   <td><!--- Needs Description --->
   </td>
   <td><!--- Needs Description --->
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>31
   </td>
   <td>Denoiser Dropdown
   </td>
   <td>
   </td>
   <td>ReLAX
   </td>
   <td>Choices: ReBLUR & ReLAX
   </td>
  </tr>
  <tr>
   <td>32
   </td>
   <td>Reset History
   </td>
   <td><!--- Needs Description --->
   </td>
   <td><!--- Needs Description --->
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>33
   </td>
   <td>Advanced Settings Checkbox
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Unchecked
   </td>
   <td>Reveals the <strong>Reprojection Test Skipping without motion</strong> checkbox
   </td>
  </tr>
  <tr>
   <td><strong>34</strong>
   </td>
   <td colspan="3" ><strong>Integrator Settings</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>35</strong>
   </td>
   <td colspan="3" ><strong>Diffuse</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>36
   </td>
   <td>Max Direct HitT % Slider
   </td>
   <td>rtx.denoiser.maxDirectHitTContribution
   </td>
   <td>-1
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>37</strong>
   </td>
   <td colspan="3" ><strong>Specular</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>38
   </td>
   <td>Lobe Trimming: Main Level Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>1.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>39
   </td>
   <td>Lobe Trimming: Low Roughness Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>1.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>40
   </td>
   <td>Lobe Trimming: High Roughness Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>41</strong>
   </td>
   <td colspan="3" ><strong>Common Settings</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>42
   </td>
   <td>Frame Time Delta [ms]
   </td>
   <td>rtx.timeDeltaBetweenFrames
   </td>
   <td>0.0
   </td>
   <td>Frame time delta to use during scene processing. Setting this to 0 will use actual frame time delta for a given frame. Non-zero value is primarily used for automation to ensure determinism run to run.
   </td>
  </tr>
  <tr>
   <td>43
   </td>
   <td>Debug
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>44
   </td>
   <td>Denoising Range
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>65400.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>45
   </td>
   <td>Disocclusion Threshold
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.010
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>46
   </td>
   <td>Disocclusion Threshold Alt.
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.100
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>47
   </td>
   <td>Split screen: Noisy | Denoised Output
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>48</strong>
   </td>
   <td colspan="3" ><strong>ReLAX Settings</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>49
   </td>
   <td>Preset Dropdown
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>Finetuned (More Stable)
   </td>
   <td>Choices: Finetuned. Finetuned (More Stable), & RTXDI Sample
   </td>
  </tr>
  <tr>
   <td>50
   </td>
   <td>History Length (ms) Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>500.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>51
   </td>
   <td>Min History Length (frames) Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>15
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>52
   </td>
   <td>Diff fast history length (frames) Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>2
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>53
   </td>
   <td>Spec fast history length (frames) Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>6
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>54
   </td>
   <td>Anti-firefly Checkbox
   </td>
   <td>
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>55
   </td>
   <td>Roughness edge stopping Checkbox
   </td>
   <td>
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>56
   </td>
   <td>Virtual history clamping Checkbox
   </td>
   <td>
   </td>
   <td>Checked
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>57
   </td>
   <td>HitT Reconstruction Mode Dropdown
   </td>
   <td>
   </td>
   <td>Area 3x3
   </td>
   <td>Choices: Off, Area 3x3, & Area 5x5
   </td>
  </tr>
  <tr>
   <td><strong>58</strong>
   </td>
   <td colspan="3" ><strong>PRE-PASS:</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>59
   </td>
   <td>Diff preblur radius Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>50.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>60
   </td>
   <td>Spec preblur radius Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>50.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>61</strong>
   </td>
   <td colspan="3" ><strong>REPROJECTION:</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>62
   </td>
   <td>Spec variance boost Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.00
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>63
   </td>
   <td>Clamping sigma scale Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>2.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>64</strong>
   </td>
   <td colspan="3" ><strong>SPATIAL FILTERING:</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>65
   </td>
   <td>A-trous iterations Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>5
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>66
   </td>
   <td>Diff-Spec luma Weight Sliders
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>1.0, 1.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>67
   </td>
   <td>Diff-Spec-Rough fraction Sliders
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.90, 0.55, 0.45
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>68
   </td>
   <td>Luma-Normal-Rough relaxation Sliders
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.65, 0.80, 0.50
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>69
   </td>
   <td>Spec lobe angle slack Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>12.500
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>70
   </td>
   <td>Diff-Spec min luma weight Sliders
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.050, 0.000
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>71
   </td>
   <td>Depth threshold Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.010
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>72
   </td>
   <td>Confidence Driven Relaxation Multiplier Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.700
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>73
   </td>
   <td>Confidence Drive Luminance Edge Stopping Relaxation Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>1.500
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>74
   </td>
   <td>Confidence Driven Normal Edge Stopping Relaxation Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>0.600
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>75</strong>
   </td>
   <td colspan="3" ><strong>DISOCCLUSION FIX:</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>76
   </td>
   <td>Edge-stop normal power Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>8.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>77
   </td>
   <td>History Fix Stride Between Samples Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>32.0
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>78
   </td>
   <td>Frames to fix Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>2
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>79</strong>
   </td>
   <td colspan="3" ><strong>SPATIAL VARIANCE ESTIMATION:</strong>
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td>80
   </td>
   <td>History threshold Slider
   </td>
   <td><!--- Needs Description --->
   </td>
   <td>2
   </td>
   <td><!--- Needs Description --->
   </td>
  </tr>
  <tr>
   <td><strong>81</strong>
   </td>
   <td colspan="3" ><strong>Secondary Direct/Indirect Light Denoiser</strong>
   </td>
   <td><em>(Please review Reference’s 29 - 80 for descriptions for all secondary settings)</em>
   </td>
  </tr>
</table>

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://docs.google.com/forms/d/1vym6SgptS4QJvp6ZKTN8Mu9yfd5yQc76B3KHIl-n4DQ/prefill) <sub>