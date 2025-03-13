# Geometry

Various compatibility options for geometry handling.

![Geometry](../../data/images/rtxremix_022.PNG)

| **Ref** | **Option**                                        | **RTX Option**                          | **Default Value** | **Description**                                                                        |
|---------|---------------------------------------------------|-----------------------------------------|-------------------|----------------------------------------------------------------------------------------|
| 1       | Enable Triangle Culling (Globally)                |                                         |                   |                                                                                        |
| 2       | Enable Triangle Culling (Override Secondary Rays) |                                         |                   |                                                                                        |
| 3       | Min Prims in Static BLAS                          |                                         | 1000              |                                                                                        |
| 4       | Portals: Virtual Instance Matching Checkbox       | rtx.useRayPortalVirtualInstanceMatching | Checked           |                                                                                        |
| 5       | Portals: Fade in Effect Checkbox                  | rtx.enablePortalFadeInEffect            | Unchecked         |                                                                                        |
| 6       | Reset Buffer Cache Every Frame Checkbox           |                                         |                   |                                                                                        |
| **7**   | **Experimental Geometry Features**                |                                         |                   |                                                                                        |
| 8       | Anti-Culling Checkbox                             | rtx.antiCulling.object.enable           | Unchecked         | Extends lifetime of objects that go outside the camera frustum (anti-culling frustum). |
| 9       | Instance Max Size                                 | rtx.antiCulling.object.numObjectsToKeep | 1000              | The maximum number of RayTracing instances to keep when Anti-Culling is enabled.       |
| 10      | Anti-Culling FoV Scale                            | rtx.antiCulling.object.fovScale         | 1.000             | Scalar of the FOV of Anti-Culling Frustum.                                             |

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
