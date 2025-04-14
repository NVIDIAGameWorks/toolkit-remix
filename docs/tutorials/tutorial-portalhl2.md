# Setting Up Portal for RTX Remix Compatibility

```{important}
[Portal with RTX](https://store.steampowered.com/app/2012840/Portal_with_RTX) is required for this tutorial.

Ensure that both Portal and Portal with RTX are installed and fully updated.
```

Many games require specific modifications to properly integrate with the RTX Remix Runtime. In the case of Portal, the
following modifications, implemented in [Portal with RTX](https://store.steampowered.com/app/2012840/Portal_with_RTX),
enhance compatibility with RTX Remix. Other [Source Engine](https://developer.valvesoftware.com/wiki/Source) games (such
as [Half-Life 2](https://developer.valvesoftware.com/wiki/Half-Life_2)) will also necessitate similar configuration
steps to achieve RTX Remix compatibility.

```{warning}
These steps should be considered specific to making Portal compatible.
```

## Copying Required Files

1. **CFG Folder Backup:** Navigate to the **Portal** `cfg` folder (`common\Portal\portal\cfg`) and rename it (e.g., to
   `original-cfg`) to preserve the original data.
2. **CFG Contents Copy:** Copy all files from the **Portal with RTX** `cfg` folder (
   `common\Portal with RTX\portal_rtx\cfg`) and paste them into the **Portal** `cfg` folder
   (`common\Portal\portal\cfg`).
3. **BIN Folder Backup:** Similarly, go to the **Portal** `bin` folder (`common\Portal\bin`) and rename it (e.g., to
   `original-bin`) to preserve the original data.
4. **BIN Contents Copy:** Copy all files from the **Portal with RTX** `bin` folder (`common\Portal with RTX\bin`) and
   paste them into the **Portal** `bin` folder (`common\Portal\bin`).
5. **Configuration Files Copy:** Copy the files named `rtx.conf` and `dxvk.conf` from the **Portal with RTX** folder
   (`common\Portal with RTX`) and paste them into the **Portal** folder (`common\Portal`).
6. **RTX Remix Runtime Files Copy:** Copy
   the [latest RTX Remix Runtime](../installation/install-runtime.md#download-from-github) files to `common\Portal\bin`,
   overwriting any existing files if prompted.

## Updating Game Variables

After launching the game from the Steam library, certain variables may need to be set. These can be configured via the
in-game developer console or Steam launch options.

1. Set `dxlevel` to `70`
2. Set `r_3dsky` to `0`
3. Set `viewmodel_fov` to `90`
4. Set `cl_first_person_uses_world_model` to `0`

### Steam Launch Options

1. Open Steam.
2. Go to the "Library."
3. Right-click the game to be reconfigured.
4. Select "Properties..." from the menu.
5. Go to the "Launch Options" section.
6. Remove any launch options currently displayed in the input box.
7. Set the launch options as detailed above. The Steam Launch Options should appear as follows:
   ```text
   -dxlevel 70 -r_3dsky 0 -viewmodel_fov 90 -cl_first_person_uses_world_model 0
   ```

```{tip}
Launching the game with different DirectX levels may resolve certain issues but could introduce problems in other games.

To change the DirectX Level Launch Options, use the following variable values:

1. `-dxlevel 90` (DirectX v9.0)
2. `-dxlevel 81` (DirectX v8.1)
3. `-dxlevel 80` (DirectX v8.0)
4. `-dxlevel 70` (DirectX v7.0)
```

## Launching the Game

Portal should now be playable with RTX Remix.

To launch the game, launch it normally from the Steam library.

For assistance with setting up RTX Remix for other games, visit
the [RTX Remix Showcase Discord Community](https://discord.gg/c7J6gUhXMk) and
check out the [remix-projects](https://discord.com/channels/1028444667789967381/1055020377430048848) channel.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
