# lightspeed.trex.ai_tools.bundle

Bundle extension that loads the AI Tools widget extensions for RTX Remix. The full RTX Remix app depends on this single
extension to enable AI Tools.

## Responsibilities

- Provide one app dependency that enables the AI Tools widget set in the correct load order.
- Register the AI Tools sidebar item independently of the project so setup, queue management, generation, and asset
  processing remain available while no project is open.
- Load the organized AI Tools layout from the sidebar.
- Own and observe the extension's layout-loading task.

## Non-Responsibilities

- Connecting to ComfyUI, loading workflows, or creating jobs; `lightspeed.trex.comfyui.core` owns those operations.
- Rendering setup, workflow, or job-queue widgets; the corresponding widget extensions own their UI.
- Opening, closing, or otherwise managing the project stage.
- Deciding whether work needs a project. Submission captures the live stage and edit target without saving; Apply
  validates that the same project and layer are open. Generation and asset processing do not use the interactive stage.

## Architecture

- `AIToolsBundleExtension` registers an always-available sidebar descriptor.
- Layout requests resolve the shared AI Tools quick-layout resource and are awaited by one retained owner task.
