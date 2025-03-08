
# [Formats](#formats)

Remix utilizes Omniverse's standard USD (for scenes) and MDL (for materials) file formats.  Most content used in Omniverse needs to be converted into one of those standard formats so that your file can be used universally among the applications being used within the platform.  You can view the [Omniverse Format documentation](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html) to read further details about file formats and format conversions.

## Asset Converter

Apps in Omniverse are loaded with the Asset Converter extension. With it, users can convert models into USD using the [**Asset Converter**](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html#asset-converter) service. Below is a list of formats it can convert to USD.

| Extension | Format | Description |
| :------- | :--------- | :------------------------- |
| `.fbx` | Autodesk FBX Interchange File | Common 3D model saved in the Autodesk Filmbox format |
| `.obj` | Object File Format | Common 3D Model format |
| `.gltf` | GL Transmission Format File | Common 3D Scene Description |
| `.lxo` | Foundry MODO 3D Image Format | Foundry MODO is a type of software used for rendering, 3D modeling, and animation |

## [Materials](#materials)

NVIDIA has developed a custom schema in USD to represent material assignments and specify material parameters. In Omniverse, these specialized USD’s get an extension change to .MDL signifying that it is represented in NVIDIA’s open-source MDL (Material Definition Language).


### DL Texture Formats Accepted

MDL Materials throughout Omniverse can accept texture files in the following formats.

| Extension | Format | Description |
| :------- | :--------- | :------------------------- |
|`.bmp`|Bitmap Image File|Common image format developed by Microsoft|
|`.dds`|DirectDraw Surface|Microsoft DirectX format for textures and environments|
|`.gif`|Graphical Interchange Format File|Common color constrained lossless web format developed by CompuServe|
|`.hdr`|High Dynamic Range Image File|High Dynamic Range format developed by Industrial Light and Magic|
|`.pgm`|Portable Gray Map|Files that store grayscale 2D images. Each pixel within the image contains only one or two bytes of information (8 or 16 bits)|
|`.jpg`|Joint Photographic Experts Group|Common “lossy” compressed graphic format|
|`.pic`|PICtor raster image format|DOS imaging standard mainly used by Graphics Animation System for Professionals (GRASP) and Pictor Paint|
|`.png`|Portable Network Graphics File|Common “lossless” compressed graphics format|
|`.ppm`|Adobe Photoshop Document|The native format for Adobe Photoshop documents|

## USD File Formats

Universal Scene Description (USD) is a versatile framework designed to encode data that can be scaled, organized hierarchically, and sampled over time. Its primary purpose is to facilitate the exchange and enhancement of data among different digital content creation applications.

| Extension | Format | Description |
| :------- | :--------- | :------------------------- |
|`.usd`|Universal Scene Description (Binary)|This is the standard binary or ASCII file format for USD. It stores the 3D scene and asset data in a compact, binary form, making it efficient for storage and processing|
|`.usda`|Universal Scene Description (ASCII)|This format stores USD data in a human-readable, ASCII text format. It's primarily used for debugging and as a reference because it's easier for humans to read and modify. However, it's less efficient in terms of file size and loading speed compared to the binary format|
|`.usdc`|Universal Scene Description (Crate)|This is a binary format for USD, but it's optimized for high-performance data storage and retrieval. .usdc files are typically used as the primary format for asset storage and production pipelines, as they offer faster loading and saving times compared to .usd files|

<!----- Placeholder for where Release Notes will go  ----->


<!----- ## [Release Notes](#release-notes)  ----->


<!----- ### [Known Issues](#known-issues)  ----->


<!----- Example of format for release notes?
* [REMIX-2121](https://omniverse-jirasw.nvidia.com/browse/REMIX-2121): On v2023.5.1 - Application Crash from gpu.foundation.plugin when navigating to the Project File Location or the Remix Directory location while using a TitianRTX
    * [https://omniverse-jirasw.nvidia.com/browse/REMIX-2121](https://omniverse-jirasw.nvidia.com/browse/REMIX-2121)

Example: [https://docs.omniverse.nvidia.com/composer/latest/release_notes.html](https://docs.omniverse.nvidia.com/composer/latest/release_notes.html)

 ----->

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
