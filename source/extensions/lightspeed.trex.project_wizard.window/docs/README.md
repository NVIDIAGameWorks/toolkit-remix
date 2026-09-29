# lightspeed.trex.project_wizard.window

Provides the modal windows for creating and opening RTX Remix projects.

## Responsibilities

- Hosts the Create and Open Project Wizard windows and their pages.
- Shows immediate modal progress after an Open-with-Capture request and blocks duplicate submissions.
- Carries progress through RTX IO package checks, project preparation, and the scene-opening handoff.
- Restores the wizard after cancellation or failure and shows setup errors without leaving the workflow blocked.
- Logs accepted requests, preparation phases, cancellation, failures, and scene-opening handoff for diagnosis.

## Non-Responsibilities

- Project validation and preparation are owned by `lightspeed.trex.project_wizard.core`.
- Individual wizard page layouts and input handling are owned by the corresponding page widget extensions.
- Scene loading after handoff is owned by Kit's file-opening workflow.

## Architecture

- `ProjectWizardBase` owns the wizard lifecycle, completion guard, recovery, and completion event.
- `CreateProjectWizardWindow` configures the project-creation page flow.
- `OpenProjectWizardWindow` configures the existing-project and capture-selection flow.

## Project-opening feedback

Submitting Open with Capture by double-clicking a capture or pressing Next/Open opens an **Opening Project** progress
popup after the wizard closes.
The popup prevents another submission from changing or restarting the accepted request. It reports package checking,
project preparation, project-data loading, and the final scene-opening handoff.

Cancellation is available while RTX IO packages are checked. Later preparation steps disable cancellation because they
cannot be safely interrupted. Cancelling restores the wizard; setup failures restore it and display an error dialog.
The same lifecycle milestones, cancellations, and failures are written to the application log for troubleshooting.
