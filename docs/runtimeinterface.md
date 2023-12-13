```{toctree}
runtimeinterface/usergraphicsettings.md
runtimeinterface/developermenu.md
runtimeinterface/renderingtab.md
runtimeinterface/renderingtabgeneral.md
runtimeinterface/renderingtabpathtracing.md
runtimeinterface/renderingtablighting.md
runtimeinterface/renderingtabvolumetrics.md
runtimeinterface/renderingtabalphatestbending.md
runtimeinterface/renderingtabdenoising.md
runtimeinterface/renderingtabpostprocessing.md
runtimeinterface/renderingtabdebug.md
runtimeinterface/renderingtabgeometry.md
runtimeinterface/renderingtabplayermodel.md
runtimeinterface/renderingtablightconversion.md
runtimeinterface/renderingtabmaterialfiltering.md
runtimeinterface/gamesetuptab.md
runtimeinterface/enhancementstab.md
runtimeinterface/about.md
```
# Runtime User Guide

RTX Remix comes with a runtime overlay menu containing detailed settings for all the major functions: Rendering, Asset Replacement, and Capture. You can access this menu by pressing **Alt + X** once in game (this hotkey can also be customized using the rtx.conf config file).

When pressing **Alt + X**, you will first be taken to the User Graphics Settings menu. This menu has various high-level settings intended for end users of RTX Remix mods to quickly customize their experience. There are three tabs: General, Rendering and Content. All the settings are described with a tooltip when you hover over them.

The General settings deal mostly with performance and include various upscaling and latency reduction options.

The Rendering settings contain high level image quality settings for the RTX Remix Path Tracing renderer. You can select one of the provided presets or customize each individual setting.

The Content settings allow you to turn off and on each of the three types of replacements supported by RTX Remix: Material, Mesh and Light replacements. These settings can be of interest when you want to evaluate the impact of each type of replacement on the mod project. Note however, that turning all the replacements off does not mean reverting to the original rendering that the underlying game uses. You are still Path Tracing, just with global defaults in place for materials and lights, and without any replacement meshes.

At the bottom of the User Graphics Settings menu, you should see a button for Developer Settings Menu. This will take you to a deeper and more detailed RTX Remix Developer Menu. It contains three main tabs. 
1. The **Rendering tab** is intended mostly for mod authors and runtime developers who need the ultimate control of renderer internals to achieve compatibility or the intended look for a mod or game. 
1. The **Game Setup tab** contains the key capture and tagging workflow that will be needed to make a game moddable and compatible with RTX Remix. 
1. The **Enhancements tab** allows for toggling various types of replacements on and off, as well as highlighting unreplaced assets, all useful for testing and validating mod content.

> 📝 There is a checkbox at the top of the Developer Settings Menu that says "Always Developer Menu." Turning this checkbox on (and saving settings) will take you directly to the Developer menu when pressing **Alt + X**, saving you a click!

The **Rendering tab** in the Developer Settings Menu allows you to customize the Remix Path Tracing renderer. You can change options for upscaling, path tracing and lighting. Every option here has a corresponding setting in the **rtx.conf** file. You can view detailed documentation on all these options in the section on config files below.

Any settings you change in the menus can be saved as new defaults. They will be stored in a file named **rtx.conf** placed next to the **.trex/ runtime** folder. This file will be created if it does not already exist. The next time you start the game with RTX Remix, settings will be read from this file, and applied automatically.

> 📝 You can extend or shrink the Menu panel by holding your mouse cursor over the edge of the panels until the icon changes to the double arrow icon, then drag the edge of the panel to the size you prefer.


## RTX Runtime Interface

RTX Remix makes it easy to adjust how your game looks and runs. To access these settings while playing the game, press **Alt + X** (you can also change this shortcut in the rtx.conf config file).

When you press **Alt + X**, you'll see the User Graphics Settings menu. This menu is designed for regular players who want to quickly change how their RTX Remix mods appear. It has three tabs: General, Rendering, and Content. If you're not sure what a setting does, just hover your mouse over it, and a tooltip will explain.

At the bottom of the User Graphics Settings menu, there's a button for the Developer Settings Menu. This takes you to an even more detailed menu for advanced users. It has three main tabs: Rendering (for mod creators and developers who want full control), Game Setup (important for making games work with RTX Remix), and Enhancements (for testing and improving mod content).

Any changes you make in these menus can be saved as new defaults. They're stored in a file called rtx.conf, which goes in the same folder as the runtime. If this file doesn't exist, RTX Remix will create it. Next time you play with RTX Remix, it will use these saved settings automatically.
 
> ⚠️ **Coders** Check out our RTX Options Documentation on GitHub [here](https://github.com/NVIDIAGameWorks/dxvk-remix/blob/main/RtxOptions.md).

### Keyboard Shortcuts 


<table>
  <tr>
   <td><strong>Input</strong>
   </td>
   <td><strong>Description</strong>
   </td>
  </tr>
  <tr>
   <td><strong>Alt + X</strong>
   </td>
   <td>Open the RTX Runtime Developer Settings Menu
   </td>
  </tr>
  <tr>
   <td><strong>Alt + Delete</strong>
   </td>
   <td>Toggle Cursor
   </td>
  </tr>
  <tr>
   <td><strong>Alt + Backspace</strong>
   </td>
   <td>Toggle Game Input
   </td>
  </tr>
  <tr>
   <td><strong>CTRL + SHIFT + Q</strong>
   </td>
   <td>Open the <strong>Enhancements </strong>Developer Menu
   </td>
  </tr>
</table>