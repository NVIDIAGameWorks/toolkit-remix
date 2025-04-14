# Game Compatibility

RTX Remix is designed for DirectX 8 and 9 games that use a fixed function pipeline. It's unlikely to work with other
types of games. Even among compatible games, there can be differences in how they handle rendering, which might lead to
crashes or unexpected visual issues.

The goal is to work with the community to identify and fix these issues to expand compatibility with more games. As RTX
Remix evolves, updates will improve compatibility.

## Defining Compatibility

A game is considered `compatible` if RTX Remix can intercept most of its drawing instructions. This doesn't guarantee a
bug-free experience initially. If a compatible game crashes, fixing the crash can make it remasterable. If the game
content isn't compatible, fixing crashes won't achieve much.

Keep in mind that not everything in a compatible game will automatically work with Remix. Some effects might need to be
replaced or require custom support for instance.

## Fixed Function Pipelines

RTX Remix works by capturing the data the game sends to the graphics card, recreating the scene, and then applying path
tracing. Fixed function pipelines send textures and meshes to the GPU in standardized formats, making it possible
(though complex) to reconstruct the scene.

Later games use shader graphics pipelines, where the game can send data in any format, and the color of a surface is
determined when it's drawn. This makes it very difficult for RTX Remix to recreate the scene, leading to
incompatibility.

Early DirectX 9 games might use a mix of fixed function and shaders, while later ones often rely entirely on shaders.
Applying Remix to a mixed game might result in only the fixed function parts being enhanced.

There's experimental support for simple vertex shaders, which can help with some objects that would otherwise fail.

```{seealso}
For more information on the difficulties associated with path tracing games with shaders, see the answer to the
following question: [Why are Shaders Hard to Path Trace?](../remix-faq.md#why-are-shaders-hard-to-path-trace)
```

## DirectX Versions

RTX Remix functions as a replacement for DirectX 9 and doesn't directly support OpenGL or older DirectX versions.

However, wrapper libraries can translate older OpenGL or DirectX 8 games to fixed function DirectX 9. While these
wrappers can introduce more issues, they've been used successfully to make some non-DirectX 9 games work with Remix.

A list of available wrappers is maintained in the
[following Discord thread](https://discord.com/channels/1028444667789967381/1055002970091176006/1055002970091176006) of
the [RTX Remix Showcase Discord Community](https://discord.gg/c7J6gUhXMk).

## ModDB Compatibility Table

The ModDB community maintains a compatibility table that lists games known to work with RTX Remix. This table also
includes the last tested RTX Remix runtime version and configuration files to help you get started quickly. You can find
it on the [ModDB website](https://www.moddb.com/rtx/). Feel free to contribute your own findings!

## Rules of Thumb

Here is a flow chart to help you determine if a game is likely to be compatible with Remix:

![Remix Compatibility](https://i.redd.it/0xi36freoojc1.png)

 > Image credit: **Traggey** ([RTX Remix Showcase Discord](https://discord.gg/c7J6gUhXMk))

More detailed tips for determining compatibility can be found below.

### Publish Date

Games released between 2000 and 2005 are the most likely to be compatible. Games released after 2010 are generally not
compatible unless they've been modified.

### Graphics API version

DirectX 8 and early DirectX 9.0 games are likely to use fixed function pipelines and are thus more likely to be
compatible. DirectX 9.0c games are usually mostly shader-based and probably won't work.

### Supported GPU

If a game could run on an NVIDIA GeForce 2 graphics card (which was fixed function only), it's likely to be fixed
function. However, some games that initially supported fixed functions removed that support in later updates.

### Checking for Shaders

You can use the following environment variables with `dxvk` to see if a game uses shaders:

```text
DXVK_SHADER_DUMP_PATH=/some/path
DXVK_LOG_LEVEL=debug
```

If that dumps out a few shaders, then the content may mostly be Remix compatible. If it dumps out a lot of shaders, then
the game probably won't be workable.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
