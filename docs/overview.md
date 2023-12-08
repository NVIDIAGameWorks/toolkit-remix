![Lightspeed Studio](data/images/lightspeed.png "Lightspeed Studios")

# [RTX Remix Overview](#rtx-remix-overview)


## [Features and Benefits](#features-and-benefits)


### [Introduction](#introduction)

RTX Remix is a cool tool for upgrading older DirectX 8 and 9 games. It adds fancy stuff like path tracing, NVIDIA DLSS (a smart upscaling technology), better textures using AI, and lets people create their own game stuff. It's like giving your old games a makeover. RTX Remix has two parts: the RTX Remix runtime (which makes the game look better) and the RTX Remix creator toolkit (which helps you make cool stuff for the game). You can use RTX Remix to make classic games look awesome and share your creations with others.


### [How Does It Work](#how-does-it-work)

You don't need to be a computer expert to use RTX Remix. It does most of the hard work for you. But it helps to know a bit about how it works. The RTX Remix runtime has two main parts: the Bridge and the Toolkit.

The Bridge is like a middleman. It sits next to the game and listens to what the game wants to do. It then sends this information to another program called NvRemixBridge.exe, which can handle more stuff because it's fancier. This fancy part makes sure the game can use a lot of memory and works better with modern technology like ray tracing.

But the Bridge is just the messenger. It sends all the game instructions to another part called the RTX Remix Toolkit. This Toolkit is like a super powerful graphics engine. It takes all the things the game wants to draw, like characters and objects, and makes them look amazing using path tracing.

The Toolkit also knows how to swap out the old game stuff with new and improved things from an RTX Remix Mod that you put in a special folder. It keeps track of what's what using special codes (hash IDs) so it knows what to change in the game as you play.

When you get your hands on the RTX Remix creator toolkit, you'll be able to easily make and add new game stuff like objects, materials, and lights. And it's built on NVIDIA Omniverse, so you'll have lots of cool tools to make your game look even better.

<!----- ON HOLD - Need to figure out how to handle this section

### [Development Roadmap](#development-roadmap)

[https://github.com/NVIDIAGameWorks/rtx-remix/wiki/Roadmap](https://github.com/NVIDIAGameWorks/rtx-remix/wiki/Roadmap)

 ----->

## [Technical Requirements](#technical-requirements)

Please review the [Omniverse Technical Requirement Documentation](https://docs.omniverse.nvidia.com/materials-and-rendering/latest/common/technical-requirements.html) for further details on what is required to use Applications within the Omniverse Platform.


## [Compatibility](#compatibility)

<!----- https://github.com/NVIDIAGameWorks/rtx-remix/wiki/Compatibility ----->

The RTX Remix Runtime is primarily targeting DirectX 8 and 9 games with a fixed function pipeline for compatibility. Injecting the Remix runtime into other content is unlikely to work. It is important to state that even amongst DX8/9 games with fixed function pipelines, there is diversity in how they utilize certain shader techniques or handle rendering. As a result, there are crashes and unexpected rendering scenarios that require improvements to the RTX Remix runtime for content to work perfectly.   

It is our goal to work in parallel with the community to identify these errors and improve the runtime to widen compatibility with as many DX8 and 9 fixed function games as possible.  As Remix development continues, we will be adding revisions to the RTX Remix Runtime that will expand compatibility for more and more titles.  Some of those solutions will be code contributions submitted by our talented [developer community](http://discord.gg/rtxremix), which we will receive on our [GitHub as pull requests](https://github.com/NVIDIAGameWorks/rtx-remix/pulls) and integrate into the main RTX Remix Runtime.  RTX Remix is a first of its kind modding platform for reimagining a diverse set of classic games with the same workflow, but it's going to take some investigation and work to achieve that broad compatibility.


### [Fixed Function Pipelines](#fixed-function-pipelines)

Remix functions by intercepting the data the game sends to the GPU, recreating the game's scene based on that data, and then path tracing that recreated scene. With a fixed function graphics pipeline, the game is just sending textures and meshes to the GPU, using standardized data formats. It's reasonable (though not easy) to recreate a scene from this standardized data.

With a shader graphics pipeline, the game can send the data in any format, and the color of a given surface isn't determined until it is actually drawn on the screen. This makes it very difficult to recreate the scene - and there are a lot of other problems that occur as well.

The transition from 100% fixed function to 100% shader was gradual - most early DirectX 9.0 games only used shaders for particularly tricky cases, while later DirectX 9.0 games (like most made with 9.0c) may not use the fixed function pipeline at all. Applying Remix to a game using a mix of techniques will likely result in the fixed function objects showing up, and the shader dependent objects either looking wrong, or not showing up at all.

We have some experimental code to handle very simple vertex shaders, which will enable some objects which would otherwise fail. Currently, though, this is very limited. See the ‘Vertex Shader Capture’ option in ‘Game Setup -> Parameters’.


### [DirectX Versions](#directx-versions)

Remix functions as a DirectX 9 replacer, and by itself cannot interact with OpenGL or DirectX 7, 8, etc.

However, there exists various wrapper libraries which can translate from early OpenGL or DirectX 8 to fixed function DirectX 9. While multiple translation layers introduce even more opportunities for bugs, these have been effectively used to get Remix working with several games that are not DirectX 9.

We are not currently aware of any wrapper libraries for DirectX 7 to fixed function DirectX 9, but in theory such a wrapper is reasonable to create.


### [Defining Compatibility](#defining-compatibility)

Games are 'compatible' if the majority of their draw calls can be intercepted by Remix. That doesn't mean there won't currently be crashes or other bugs that prevent a specific game from launching. If the game crashes, but the content is compatible, then fixing the crash means the game can be remastered. If the game's content isn't compatible, then fixing the crash won't really achieve anything.

This also doesn't mean that everything in the game will be Remix compatible - often specific effects will either need to be replaced using the existing replacements flow, or will need some kind of custom support added to the runtime (like terrain).


### [Rules of Thumb](#rules-of-thumb)

The following quick checks can help you quickly narrow down on how likely a game is to be compatible, even before you try to run RTX Remix.

#### [Publish Date](#publish-date)

The best “at a glance” way to guess if a game is compatible is to look at the publish date. Games released between 2000 and 2005 are most likely to work. Games after 2010 are almost certainly not going to work (unless they are modified to support fixed function pipelines).

#### [Graphics API version](#graphics-api-version)

DirectX 8 and DirectX 9.0 will probably be fixed function, and thus feasible. DirectX 9.0c games are usually mostly shader based, so probably won't work.

#### [Supported GPU](#supported-gpu)

The Nvidia Geforce 2 graphics card was the last card to be fixed function only, so if the game could run on that card, it's probably fixed function. Note that many games supported fixed function when they released, but removed that support in later updates. Testing the content It's actually possible to tell dxvk to dump out any shaders used by the game, adding these settings to your environment variables:
```
DXVK_SHADER_DUMP_PATH=/some/path
DXVK_LOG_LEVEL=debug
```
If that dumps out a few shaders, then the content may mostly be Remix compatible. If it dumps out a lot of shaders, then the game probably won't be workable.


## [Formats](#formats)

Remix utilizes Omniverse's standard USD (for scenes) and MDL (for materials) file formats.  Most content used in Omniverse needs to be converted into one of those standard formats so that your file can be used universally among the applications being used within the platform.  You can view the [Omniverse Format documentation](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html) to read further details about file formats and format conversions.

### Asset Converter

Apps in omniverse are loaded with the Asset Converter extension. With it, users can convert models into USD using the [**Asset Converter**](https://docs.omniverse.nvidia.com/composer/latest/common/formats.html#asset-converter) service. Below is a list of formats it can convert to USD.

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


### [Materials](#materials)

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




### USD File Formats

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

Need to leave feedback about the RTX Remix Documentation?  [Click here](https://docs.google.com/forms/d/1vym6SgptS4QJvp6ZKTN8Mu9yfd5yQc76B3KHIl-n4DQ/prefill)