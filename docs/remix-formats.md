
# [Formats](#formats)

Remix utilizes Omniverse's standard USD (for scenes) and MDL (for materials) file formats.  Most content used in Omniverse needs to be converted into one of those standard formats so that your file can be used universally among the applications being used within the platform.  You can view the [Omniverse Format documentation](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html) to read further details about file formats and format conversions.

## Asset Converter

Apps in Omniverse are loaded with the Asset Converter extension. With it, users can convert models into USD using the [**Asset Converter**](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html#asset-converter) service. Below is a list of formats it can convert to USD.

| Level                | Operating System  | CPU                   | CPU Cores | RAM     | GPU                | VRAM  | Disk           |
| :------------------: | :---------------: | :-------------------: | :-------: | :-----: | :----------------: | :---: | :------------: |
| Min              |   Windows 10/11   | Intel I7 or AMD Ryzen | 4         | 16 GB   | GeForce RTX 3060Ti | 8 GB  | 512 GB SSD     |
| Rec          |   Windows 10/11   | Intel I7 or AMD Ryzen | 8         | 32 GB   | GeForce RTX 4070   | 12 GB | 512 GB M.2 SSD |




<table>
  <tr>
   <td><strong>Extension</strong>
   </td>
   <td><strong>Format</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>.fbx
   </td>
   <td>Autodesk FBX Interchange File
   </td>
   <td>Common 3D model saved in the Autodesk Filmbox format
   </td>
  </tr>
  <tr>
   <td>.obj
   </td>
   <td>Object File Format
   </td>
   <td>Common 3D Model format
   </td>
  </tr>
  <tr>
   <td>.gltf
   </td>
   <td>GL Transmission Format File
   </td>
   <td>Common 3D Scene Description
   </td>
  </tr>
  <tr>
   <td>.lxo
   </td>
   <td>Foundry MODO 3D Image Format
   </td>
   <td>Foundry MODO is a type of software used for rendering, 3D modeling, and animation.
   </td>
  </tr>
</table>


## [Materials](#materials)

NVIDIA has developed a custom schema in USD to represent material assignments and specify material parameters. In Omniverse, these specialized USD’s get an extension change to .MDL signifying that it is represented in NVIDIA’s open-source MDL (Material Definition Language).


### DL Texture Formats Accepted

MDL Materials throughout Omniverse can accept texture files in the following formats.


<table>
  <tr>
   <td><strong>Extension</strong>
   </td>
   <td><strong>Format</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>.bmp
   </td>
   <td>Bitmap Image File
   </td>
   <td>Common image format developed by Microsoft.
   </td>
  </tr>
  <tr>
   <td>.dds
   </td>
   <td>DirectDraw Surface
   </td>
   <td>Microsoft DirectX format for textures and environments.
   </td>
  </tr>
  <tr>
   <td>.gif
   </td>
   <td>Graphical Interchange Format File
   </td>
   <td>Common color constrained lossless web format developed by CompuServe.
   </td>
  </tr>
  <tr>
   <td>.hdr
   </td>
   <td>High Dynamic Range Image File
   </td>
   <td>High Dynamic Range format developed by Industrial Light and Magic.
   </td>
  </tr>
  <tr>
   <td>.pgm
   </td>
   <td>Portable Gray Map
   </td>
   <td>Files that store grayscale 2D images. Each pixel within the image contains only one or two bytes of information (8 or 16 bits)
   </td>
  </tr>
  <tr>
   <td>.jpg
   </td>
   <td>Joint Photographic Experts Group
   </td>
   <td>Common “lossy” compressed graphic format.
   </td>
  </tr>
  <tr>
   <td>.pic
   </td>
   <td>PICtor raster image format
   </td>
   <td>DOS imaging standard mainly used by Graphics Animation System for Professionals (GRASP) and Pictor Paint.
   </td>
  </tr>
  <tr>
   <td>.png
   </td>
   <td>Portable Network Graphics File
   </td>
   <td>Common “lossless” compressed graphics format.
   </td>
  </tr>
  <tr>
   <td>.ppm
   </td>
   <td>Adobe Photoshop Document
   </td>
   <td>The native format for Adobe Photoshop documents.
   </td>
  </tr>
</table>




## USD File Formats

Universal Scene Description (USD) is a versatile framework designed to encode data that can be scaled, organized hierarchically, and sampled over time. Its primary purpose is to facilitate the exchange and enhancement of data among different digital content creation applications.


<table>
  <tr>
   <td><strong>Extension</strong>
   </td>
   <td><strong>Format</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td>.usd
   </td>
   <td>Universal Scene Description (Binary)
   </td>
   <td>This is the standard binary or ASCII file format for USD. It stores the 3D scene and asset data in a compact, binary form, making it efficient for storage and processing.
   </td>
  </tr>
  <tr>
   <td>.usda
   </td>
   <td>Universal Scene Description (ASCII)
   </td>
   <td>This format stores USD data in a human-readable, ASCII text format. It's primarily used for debugging and as a reference because it's easier for humans to read and modify. However, it's less efficient in terms of file size and loading speed compared to the binary format.
   </td>
  </tr>
  <tr>
   <td>.usdc
   </td>
   <td>Universal Scene Description (Crate)
   </td>
   <td>This is a binary format for USD, but it's optimized for high-performance data storage and retrieval. .usdc files are typically used as the primary format for asset storage and production pipelines, as they offer faster loading and saving times compared to .usd files.
   </td>
  </tr>
</table>



<!----- Placeholder for where Release Notes will go  ----->


<!----- ## [Release Notes](#release-notes)  ----->


<!----- ### [Known Issues](#known-issues)  ----->


<!----- Example of format for release notes?
* [REMIX-2121](https://omniverse-jirasw.nvidia.com/browse/REMIX-2121): On v2023.5.1 - Application Crash from gpu.foundation.plugin when navigating to the Project File Location or the Remix Directory location while using a TitianRTX
    * [https://omniverse-jirasw.nvidia.com/browse/REMIX-2121](https://omniverse-jirasw.nvidia.com/browse/REMIX-2121)

Example: [https://docs.omniverse.nvidia.com/composer/latest/release_notes.html](https://docs.omniverse.nvidia.com/composer/latest/release_notes.html)

 ----->

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>