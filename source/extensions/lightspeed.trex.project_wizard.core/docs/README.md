# lightspeed.trex.project_wizard.core

Provides project-wizard schemas and project creation or repair services shared by Toolkit workflows.

## Responsibilities

- Validate project, mod, capture, and RTX Remix dependency paths.
- Distinguish missing project-layer metadata from other path validation failures.
- Create or repair project layers and their linked resources.

## Non-Responsibilities

- Does not render wizard pages or windows.
- Does not own StageCraft workspace transitions.

## Architecture

- `ProjectWizardSchema` validates wizard inputs and raises `ProjectFileMetadataError` for missing project metadata.
- `ProjectWizardCore` creates or repairs project files from validated wizard data.
