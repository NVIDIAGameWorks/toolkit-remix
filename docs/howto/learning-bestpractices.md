# Following Best Practices

## Selecting the Appropriate USD Format

USD supports several formats: USD (binary), USDA (ASCII), and USDC. USD is a binary format, whereas USDA is a
human-readable ASCII format.

USDA's readability facilitates external editing, which is useful for asset issue resolution or collaborative workflows.

USD formats offer slightly more efficient loading. For mod distribution, converting USDA files to USD can optimize
loading speeds.

## Organizing Captures

In large mod projects, numerous captures may be taken to encompass all desired modifications. To maintain organization,
it is recommended to adopt a consistent naming convention for these captures, such as prefixing names with the game
section they represent. For instance, captures taken in chapter one could be named using the prefix "ch1_".

```{warning}
Capture renaming is best performed before project creation in RTX Remix. Renaming a capture after it's used in a project
can cause project loading failures. Renaming is permissible only if the capture is not referenced by any existing
projects.
```

## Project Organization Using Layers

When a mod is created, a file named `mod.usda` serves as the primary target layer. This layer is read by the runtime.

As a mod expands, the `mod.usda` file can become very large, potentially spanning thousands or tens of thousands of
lines.

While all overrides can be placed within the `mod.usda` layer, layer composition can enhance organization.

Prior to implementing replacements, consider the types of assets involved. Separating replacements into distinct layers,
such as for model replacements and material replacements, is advisable. For extensive games, organizing layers on a
chapter basis may also be beneficial.

While excessive organization is possible, dividing a mod into component layers simplifies long-term change tracking.

Layers are also valuable for team collaboration. The [Working in a Team](#working-in-a-team) section provides guidance
on project setup for team collaboration.

## Working in a Team

Game remastering can be a substantial undertaking, potentially necessitating team collaboration. Given the artistic
emphasis of Remix mods, structuring a workflow that enables efficient collaboration among artists is beneficial, even if
gameplay mechanics are also modified.

Designating one or two individuals to manage Remix setup and asset preparation can help maintain consistency and avoid
confusion. Excessive involvement in these tasks may introduce errors and inconsistencies in project files.

Version control systems (e.g., Git) are highly recommended for tracking changes and ensuring team synchronization.
The [Setting Up Version Control for Your Project](#setting-up-version-control-for-your-project) section offers
information on version controlling assets.

## Setting Up Version Control for Your Project

Version control is a valuable tool for tracking project changes, enabling reversion to previous versions and preventing
data loss, especially in team settings.

When setting up version control, consider the following:

* Remix projects predominantly involve art assets, making version control systems optimized for large binary files
  suitable. Git LFS (Large File Storage) or Perforce are viable options.
* Configure the version control system to ignore Remix-generated files (e.g., thumbnails) to maintain repository
  cleanliness.
* Employ a branching strategy to manage different features or changes, allowing concurrent work without interference.

```{important}
Exclude the `deps` folder from version control, as it is a symlink to the game's rtx-remix folder and cannot be
transferred between systems.

Failure to exclude this folder may result in errors when attempting to load the project on a different system.
```

Adding captures to version control facilitates project sharing. However, the potentially large size of captures may
warrant a separate storage solution, with only the mod itself under version control.

## Choosing Project Directories

It is recommended to create a dedicated folder for all RTX Remix projects, located *outside* the game's installation
directory.

For example, if the game is installed in `C:/Program Files (x86)/Steam/common/Portal`, projects can be created at
`C:/Users/<USER>/RemixProjects` or `D:/RemixProjects`.

## Using Relative Paths for Portability

Although absolute paths are supported, using relative paths is recommended for portability. This approach allows the
project to be moved to different systems without requiring path adjustments.

When creating a project, the RTX Remix Toolkit generates a folder structure that includes a `deps` symlink. This symlink
connects the project to the game's `rtx-remix/mod` folder and should be used when referencing captures or third-party
mod dependencies.

```{tip}
**Example**

Instead of using an absolute capture path:

`C:\Program Files (x86)\Steam\common\Portal\rtx-remix\captures\capture_01.usd`,

use a relative, portable reference:

`./deps/captures/capture_01.usd`.
```

## Managing Source and Ingested Assets

For organization, consider creating additional folders within the project folder to separate source and ingested assets.
This structure is particularly useful for version controlled projects, as it allows for easy tracking of changes to
both source and ingested assets.

* Source directory:
    * Contains pre-ingestion assets and textures (FBX, USD, OBJ, etc.)
    * May be external to the project directory

* Output directory:
    * Created manually within the project directory
        * `(project_root)/assets/ingested/` is a suitable output directory
    * The external asset copying feature defaults to `(project_root)/assets/ingested/`
    * Contains ingested assets (USD or DDS) referenced in the project

### Linking External Assets Depot

Given the potential size of project folders and source asset folders, consider storing assets in a central depot and
using symlinks to connect them to your projects.

Example command:

```bat
mklink /J "YOUR_PROJECT_DIR/assets" "INGESTED_ASSET_DIR"
```

## Optimizing Noise Levels When Relighting

A high number of lights can increase noise due to rendering inefficiencies in light sampling. Similarly, numerous
occluded lights in a small area can cause noise. While this is generally acceptable in confined spaces, it can be
problematic in larger areas.

Conversely, insufficient lighting in an area can also increase noise as the renderer relies on longer lighting paths.
This may be unavoidable in areas primarily lit indirectly.

Thin geometry or detailed curvature on reflective or transparent surfaces may introduce noise because camera jitter (
used for anti-aliasing and upscaling) can disrupt the denoiser, as Remix loses the ability to track the geometry across
frames.

Avoid intersecting light sources with other geometry, as this reduces sampling efficiency.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
