# Example Crash Manifest

This is a fictional case manifest. Use it to review table shape, not as evidence for a real crash.

## Case

Name: `example-capture-switch-crashes`
Scope: Toolkit crashes seen while opening a project and switching captures.
Repo: `lightspeed-kit`
Toolkit branch/commit: `dev/example/aftermath @ abc1234`
HdRemix/DXVK build: `remix-main+def5678`
Driver/GPU: `Example Driver 555.55 / RTX Example`

## Root Cause Summary

| Root Cause ID | Likely Layer | Confidence | Runs | Shared Signature | Key Evidence | Status / Owner |
|---|---|---:|---|---|---|---|
| RC-01 | GPU / DXVK / HdRemix | Medium | RUN-001, RUN-002 | Device lost after capture switch | `remix-dxvk.log` ends near `EndFrame`; Windows has LiveKernelEvent 141; no Python traceback | Needs rendering engineer review with AF dump if available |
| RC-02 | Kit / USD stage load | Low | RUN-003 | Crash during project open before capture selection | Kit log tail mentions stage load; minidump stack has USD/Sdf frames; no DXVK failure signature | Needs paired repro with same project and clean launch |

## Run Details

| Time | Run ID | Likely Root Cause | Outcome | Trigger | Evidence | Artifacts | Notes |
|---|---|---|---|---|---|---|---|
| 2026-06-02 10:14:22 EDT | RUN-001 | RC-01 | Crash | Switched from capture `warehouse` to `street`, then focused another app | LiveKernelEvent 141; `remix-dxvk.log` stops after frame work; no Kit Python traceback | `RUN-001_capture-switch/RUN_MANIFEST.md`; minidump UUID `11111111-2222-3333-4444-555555555555` | First crash in this case; AF dump missing |
| 2026-06-02 10:31:08 EDT | RUN-002 | RC-01 | Crash | Repeated capture switch with same project, different source capture | Same DXVK tail shape as RUN-001; Windows watchdog report within 2 minutes | `RUN-002_capture-switch-alt-source/RUN_MANIFEST.md`; AF dump `example-gpu-dump.nv-gpudmp` | Same bucket as RUN-001, stronger evidence if AF opens |
| 2026-06-02 11:03:44 EDT | RUN-003 | RC-02 | Crash | Opened project from launcher, no capture switch | Kit log ends during stage load; minidump stack includes `Sdf.dll`; DXVK log has no device-lost marker | `RUN-003_project-open/RUN_MANIFEST.md`; minidump UUID `aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee` | Different timing and signature from RC-01 |
| 2026-06-02 11:27:10 EDT | RUN-004 | Unknown | No crash | Repeated RUN-003 after clean rebuild | Project opened; no minidump; logs captured for comparison | `RUN-004_project-open-control/RUN_MANIFEST.md` | Control run; do not treat as a crash |

## Repro Guide

1. Launch Toolkit from the recorded `launch cwd` in each run manifest.
2. Open the project listed in the run manifest.
3. For RC-01, switch captures using the exact source and target names in the run table.
4. For RC-02, open the project without switching captures and wait until stage load is complete or the app crashes.

## Open Questions

- Is RC-01 reproducible with an AF dump on the same HdRemix/DXVK build?
- Does RC-02 reproduce on a clean branch with the same project and no extra Toolkit processes?
- Are RUN-001 and RUN-002 from the same app process or separate launches?
