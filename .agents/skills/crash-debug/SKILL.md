---
name: crash-debug
description: Use when investigating RTX Remix Toolkit crashes, Kit minidumps, DXVK/HdRemix logs, Aftermath dumps, GPU device-lost failures, d3d9 crashes, capture-switch repros, or crash handoff bundles.
---

# Crash Debug

Use for RTX Remix Toolkit crash investigations. Keep runs separate, preserve provenance, classify the likely failing
layer only when the evidence supports it, and avoid unsupported root-cause claims.

## Workflow

1. Identify the run: time, run id, trigger, outcome, project/capture names, app path, launch cwd, process id, Toolkit
   commit, HdRemix/DXVK version, driver version, GPU, and any dirty repo state.
2. Draft a dev repro guide early. Include exact launch method, project/capture inputs, UI steps, expected timing,
   observed crash signature, and artifact/run ids. Keep updating it as evidence changes.
3. Check `docs_dev/internal/qa-steps.md` before using `open_project.bat`. Use it for quick Runtime bug repros or rapid
   testing of specific Runtime issues; do not use it for smoke checks, feature validation, or user-flow bugs because it
   bypasses normal UI validation.
4. Gather artifacts: Kit logs, DXVK/HdRemix logs, minidumps, Aftermath dumps, crash metadata, configs, screenshots,
   repro notes, and relevant Windows events. Preserve build/version details for Toolkit, HdRemix/DXVK, GPU driver, and
   OS when available.
5. Bundle artifacts with:

   ```batch
   tools\packman\python.bat tools\crash_debug\bundle_crash_artifacts.py --help
   ```

6. Organize bundles under one case root:

   ```text
   crash-artifacts/<case-name>/
     CASE_MANIFEST.md
     RUN-001_<short-title>/
       RUN_MANIFEST.md
   ```

7. Preserve minidump UUIDs in the run manifest.
8. Use a new `--run-id` for each bundle invocation; the bundler refuses existing run ids to avoid rewriting evidence.
9. When a case has multiple runs, create or update `CASE_MANIFEST.md` using `example-crash-manifest.md` as the table
   format. Keep root-cause ids stable across runs (`RC-01`, `RC-02`, ...), keep unknowns explicit, and do not add
   placeholder rows for artifacts that do not exist.
10. Do not mix logs or dumps from multiple app copies. If multiple Toolkit processes are open, prove which process wrote
   each artifact before drawing conclusions.

## Classification

Use module names, exception codes, stack frames, log tails, crash metadata, and repro timing together.

- Kit/USD/Sdf/Tf: Python traceback, Kit crash metadata, USD/Sdf/Tf modules, extension lifecycle, stage/load state.
- DXVK/HdRemix/d3d9: `d3d9.dll`, `HdRemix.dll`, `remixapi_*`, `QueryFeatureVersion`, `remix-dxvk.log`.
- GPU/driver: `VK_ERROR_DEVICE_LOST`, `NRC EndFrame`, WER `LiveKernelEvent 141`, `nvlddmkm`, `.nv-gpudmp`/`.gpudmp`.
- Extension code: Python traceback, extension logs, recent extension events, tests that isolate the extension.

`lastCommands` is supporting evidence only. A visible UI or command event can be last while the failing layer is
elsewhere.

## Aftermath

Track Kit-owned and DXVK/HdRemix Aftermath separately:

- Kit AF: `NVIDIA Aftermath Status: ...`
- DXVK/HdRemix AF: `dxvk.enableAftermath = True` and `Aftermath enabled` in `remix-dxvk.log`

Kit crash metadata such as `aftermath_status` describes Kit-owned AF only. It does not prove DXVK/HdRemix AF state.

Aftermath is instrumentation, not a workaround. Missing `.nv-gpudmp` files do not prove AF setup failed unless the run
actually reached a GPU/device-lost path that AF can report. Do not add AF toggles to crash isolation by default or infer
AF changes behavior without paired runs that isolate AF state as the changed variable.

## Reporting

Lead with:

```text
Classification: likely <layer>
Confidence: high/medium/low
Why: <evidence>
Not proven: <remaining ambiguity>
Repro guide: <path or current steps>
Next test: <one-variable test>
Workaround: <only if supported>
```
