# Profiling

Kit has a built-in profiler and bundles Tracy with it — no downloads, no code to add.

## Quick start

```batch
set CARB_PROFILING_PYTHON=1&& .\_build\windows-x86_64\release\lightspeed.app.trex_dev.bat
```

> No space before `&&` — `set VAR=1 && command` would capture the trailing space into the
> variable value, which `carb.profiler` doesn't read as enabled.

Inside the app:

1. Press **F8** to open the Profiler window.
2. Tick **CPU Profiler**.
3. Press **F5** to start, drive the app, press **F5** again to stop.

Traces land in `_build\…\release\logs\Kit\RTX Remix Dev\<version>\traces\` as
`ct_<timestamp>.gz`. Open them from the Profiler window's Capture Browser (see
[Opening existing captures](#opening-existing-captures) below).

## Profile startup only

One-shot capture: runs the app, writes a trace, quits, opens it in Tracy.

```batch
set CARB_PROFILING_PYTHON=1&& .\_build\windows-x86_64\release\kit\profile_startup.bat .\_build\windows-x86_64\release\apps\lightspeed.app.trex_dev.kit
```

The trace (`startup_profile.gz`) lands in the directory you ran the command from.

## Live Tracy connection

Watch the app in real time as you interact. Load both backends through the multiplexer:

```batch
set CARB_PROFILING_PYTHON=1&& .\_build\windows-x86_64\release\lightspeed.app.trex_dev.bat --/app/profilerBackend=[cpu,tracy]
```

Inside the app, press **F8** to open the Profiler window and click
**Launch Tracy and Connect**, then press **F5** to start emitting events.

> Use `[cpu,tracy]`, not a bare `tracy`. The Profiler window crashes if the CPU backend
> isn't loaded.

## Finding your code in a trace

Python frames appear with a `(Python)` suffix; Python-interpreter C-API calls with a
`(C)` suffix. For example:

- `omni.flux.stage_manager.factory.items.StageManagerItem.parent (Python)`
- `builtins.hasattr (C)`

In Tracy, **Ctrl+F** searches zone names — type the function or class name and it jumps
to every call site on every thread. Searching by zone is usually faster than scanning
by thread, especially for async code: asyncio work dispatched through `carb.tasking`
runs on pooled fibers labelled `Fiber #N`, and a single coroutine can execute across
many of them.

## Opening existing captures

Press **F8** to open the Profiler window, then click **Browse** to open the Captured
Traces Browser. Each saved trace has a row of buttons — click **tracy** to open it in
the bundled Tracy.

```{note}
Widen the Captured Traces Browser window if you don't see the **tracy** button —
on narrower widths the row's buttons get clipped off the right side.
```

Each row also has **unzip** (extracts the `.gz` to a `.json` you can drop into
`chrome://tracing`), **stats**, **snakeviz** (cProfile captures only), and **remove**
if you need them.

## References

- [Kit SDK Profiling](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html)
- [Carbonite Profiler API](https://docs.omniverse.nvidia.com/kit/docs/carbonite/latest/api/group__Profiler.html)
- [Tracy manual](https://github.com/wolfpld/tracy)
