# lightspeed.trex.rtxio.core

Shared RTX IO probing, validation, compression, extraction, and cancellation
logic used by toolkit packaging and project-open flows.

## Responsibilities

- Resolve the packaged `RtxIoResourcePackager.exe` and
  `RtxIoResourceExtractor.exe` paths for toolkit code.
- Detect extractable RTX IO root package files below a mod or project directory.
- Scan USD stages for broken authored texture references before open/edit
  decides whether extraction is required.
- Run RTX IO compression and extraction subprocesses while surfacing progress and
  cancellation state to callers.
- Delete packaged DDS files after successful compression when the caller opts
  into cleanup.
- Define shared split-size presets so packaging and project-wizard flows use
  the same RTX IO sizing choices.

## Non-Responsibilities

- Does not create or own packaging UI. `lightspeed.trex.packaging.widget` owns
  the packaging panel layout and user interaction.
- Does not decide when the project wizard should prompt, block, or continue.
  `lightspeed.trex.project_wizard.core` owns the open/edit flow decisions.
- Does not run the standard USD mod packaging pipeline. That remains in
  `lightspeed.trex.packaging.core`.
- Does not interpret or edit mod metadata beyond the RTX IO-specific schema
  fields it owns.

## Architecture

`RtxIoCore` is the central runtime entry point. It exposes three groups of
behavior:

- probe helpers that detect `.pkg` files and scan a USD stage for missing
  authored texture references
- execution helpers that compress a packaged directory, extract packages, and
  optionally delete packaged DDS files
- progress/cancellation plumbing that keeps long RTX IO operations responsive for
  callers in packaging and project-wizard flows

The core keeps all subprocess handling in one place so both packaging and
project-open flows reuse the same cancellation behavior, progress semantics, and
package filtering rules. `RtxIoProbeResult` carries the combined results of the
directory probe and broken-reference scan. `RtxIoSplitSizePreset` in `items.py`
defines the shared split-size choices used by the UI and packaging schema
validation layers.
