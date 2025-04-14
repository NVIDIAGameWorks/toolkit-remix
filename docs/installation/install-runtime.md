# Installing the RTX Remix Runtime

The RTX Remix Runtime is needed to play RTX Remix mods. **It is also included when you install the Toolkit.**

## Find the RTX Remix Runtime Bundled with the RTX Remix Toolkit

If you installed the RTX Remix Toolkit, the Runtime is already on your system.

To find it, go to the following folder:
<code>
[<INSTALL_DIRECTORY>](../remix-faq.md#how-can-i-locate-the-rtx-remix-toolkit-installation-folder)\deps\remix_runtime\runtime
</code>

Once you find the directory, you can follow the [instructions below](#installing-the-rtx-remix-runtime-for-your-game) to
install the Runtime for your game.

## Download from GitHub

For access to the latest, potentially unstable features, you can install the RTX Remix Runtime from GitHub.

Download the RTX Remix Runtime files from the
[latest GitHub release](https://github.com/NVIDIAGameWorks/rtx-remix/releases/).

The downloaded zip file contains the necessary files to prepare a supported game for RTX Remix. After unzipping, you
can follow the [instructions below](#installing-the-rtx-remix-runtime-for-your-game) to install the Runtime for your game.

```{tip}
The RTX Remix Bridge and DXVK-Remix files are also available separately on GitHub for users who want to access
experimental updates before they are included in a full Runtime release. You can find them here:

* Bridge Application: [bridge-remix](https://github.com/NVIDIAGameWorks/bridge-remix).
* DXVK-Remix Application: [dxvk-remix](https://github.com/NVIDIAGameWorks/dxvk-remix/).
```

## Installing the RTX Remix Runtime for Your Game

Once you have located the runtime directory, you should find the following files:

```text
runtime/
|--- d3d9.dll  <-- Bridge interposer
|--- ...
\--- .trex/
    |--- NvRemixBridge.exe
    |--- d3d9.dll  <-- Remix Renderer/DXVK-Remix
    \--- ...
```

To prepare your game, start by copying the contents of the directory into the main game’s directory. The
`d3d9.dll` and `.trex/` folder should end up sitting right next to the main game executable.

```{warning}
Some games will search for `d3d9.dll` in a directory other than the directory of the main game executable. For example,
Source Engine games will search in the bin directory next to the main game executable for d3d9.dll instead.
```

Once RTX Remix files are in place, you can start the game normally. You can verify RTX Remix is working by checking for
the splash message at the top of the screen when the game starts. It should say: “Welcome to RTX Remix…” and
provide hotkey information to access the Remix menus.

```{seealso}
For more ways to verify that RTX Remix is working, see the
[Is My Game Being Processed by RTX Remix?](../remix-faq.md#is-my-game-being-processed-by-rtx-remix) section.
```

## Support for Other Graphics APIs

While support for D3D9 is included in Remix out of the box, games that use other graphics APIs can also be made to work
by utilizing translation layers that target D3D9. You will have to acquire these separately. For example, D3D8 games can
be supported through [D3D8to9](https://github.com/crosire/d3d8to9).

1. Open the folder that contains the source files of the game you wish to mod.
2. Locate where the executable (.exe) file is stored. This file is usually found inside a folder named "bin".
3. Copy and paste the Contents of the RTX Remix Runtime folder into the folder that contains the executable (.exe) file

   ![FolderStructureDemo](../data/images/rtxremix_018.PNG)

4. Ensure that the d3d9.dll file from the RTX Remix folder copies over the d3d9.dll file in the game folder.
5. Now, run the game. If the Runtime has been installed successfully, you should be be able to open the **User Graphics
   Settings** Remix menu by pressing **Alt + X**.

   ![UserGraphicSettings](../data/images/rtxremix_012.PNG)

```{tip}
If you are having trouble, try launching your game in Direct X v.7 or lower
```

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
