# Changelog

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [2024.2.1]

### Added:
- REMIX-2541: Expose Inference Mode UI for AI Texture Tool
- REMIX-2526: AI Texture accept jpeg
- REMIX-119: Automatically switch to the mod layer when a wrong layer is set as an edit target
- REMIX-74, REMIX-114, REMIX-1483: Add events to validate the project + restore edit target
- REMIX-2695: Check if Remix is supported
- REMIX-2028: Add duplicate button to lights in selection tree
- REMIX-1090: Add tree headers to the capture list to describe the columns
- REMIX-1923: Add xform copy/paste functionality
- REMIX-114: Save Authoring Layer on Set

### Fixed:
- REMIX-2669: Fix slowdown on project creation + light optimization
- REMIX-2521: Adding check for Windows reserved words
- REMIX-2709: Fix capture window dpi
- REMIX-1542 REMIX-1693: don't lose focus of widgets when modifying properties
- REMIX-2419 REMIX-2736: Handle 'f' key press anywhere on layout or ingestion tab. Handle 'Ctrl+S', etc. key presses on all tabs
- REMIX-2719: Choose the same GPU for DXVK, as the one in Hydra Engine
- REMIX-2722: Adjust default light intensity (first pass. Will do more ajustements)
- REMIX-2642: Spelling / Wording / Grammar corrections in the Annotations for the Input File Path
- REMIX-2654, REMIX-2661: AI Tools don't run on 20-series GPUs. AI Tools don't get cleaned out of memory after inference is done.
- [HDRemix] Fix scale not affecting lights


## Known Issues

| **Issue:** | Wireframe Viewport Display Unavailable   |
|---:|:---|
|**Description:**| We expect the wireframe display feature to be unavailable for an extended period. We apologize for any inconvenience and sincerely appreciate your patience. |
|**Workaround:**| None
|**Status:**| _On Hold_ |
|**ETA for Resolution:**| _TBD_ If you consider this feature a priority and would like us to expedite its resolution, please reach out to us through the link below. Your feedback is invaluable in helping us prioritize and address user concerns. |
|**Version Affected:**| _Current Release_ |

| **Issue:** | Known Issue: Unable to Create Projects on exFAT or FAT32 Formatted Drives   |
|---:|:---|
|**Description:**| Users may encounter an issue when attempting to create projects on drives formatted with the exFAT file system. Currently, the system does not support the creation of projects on exFAT or FAT32 formatted drives, leading to an error during the project creation process. |
|**Workaround:**| Users are advised to create projects on drives formatted with NTFS file systems. |
|**Status:**| _Will not fix_ |
|**ETA for Resolution:**| _TBD_ If you consider this feature a priority and would like us to expedite its resolution, please reach out to us through the link below. Your feedback is invaluable in helping us prioritize and address user concerns. |
|**Version Affected:**| _Current Release_ |


## How to Report an Issue

Prerequisite: You need to have a (free) github account
1. Go the [RTX Remix Github Issues page](https://github.com/NVIDIAGameWorks/rtx-remix/issues)
2. Click the green "New Issue" button
3. Select the bug template (Runtime, Documentation, Toolkit, Feature Request) and click "Get Started"
4. Fill out the form template, providing as much detailed information as you can, including attaching files and/or images
5. Click the green "Submit new issue" to send a ticket directly to the RTX Remix Team!


***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) <sub>
