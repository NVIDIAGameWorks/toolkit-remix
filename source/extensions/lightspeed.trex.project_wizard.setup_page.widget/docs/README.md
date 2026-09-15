# lightspeed.trex.project_wizard.setup_page.widget

Project Wizard page for choosing a project location, a Remix directory, and a capture when required.

## Responsibilities

- Collect project and Remix-directory paths and publish the page's capture selection into the wizard payload.
- Require a capture for Create/Edit and existing-project flows with the capture picker enabled; it is optional only for an existing project with the picker disabled.
- Delegate capture discovery, bounded classification, and accepted-capture thumbnail resolution to Capture Core.
- Invoke the page's current primary wizard action when a valid capture is double-clicked and the page is unblocked: Create completes the wizard and starts project creation, Edit advances to mod selection, and existing-project setup or recovery completes the wizard.

## Non-Responsibilities

- Discovery does not fully open or compose candidate stages, cache or index results, progressively publish validation, or replace final schema validation.

## Architecture

- `SetupPage` owns the file-picker UI, payload state, navigation blocking, and primary-action activation policy.
- Its background worker calls Capture Core discovery and publishes results only for the current Remix directory.
- `CaptureTreeModel` and `CaptureTreeDelegate` render those candidates. Selection publishes the chosen capture, exact-item activation requests the current primary action, and `ProjectWizardSchema` remains the final validation backstop.
