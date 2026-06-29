# Profiling

Kit has a built-in profiler and bundles Tracy with it - no downloads, no code to add.

## Quick start

Use the regular app profile launcher. It enables the Profiler window, Python
profiling, and the CPU/Tracy profiler backends.

```batch
.\_build\windows-x86_64\release\lightspeed.app.trex.profile.bat
```

````{tip}
You can also launch the dev app in profile or startup profile mode with these commands:

```batch
.\_build\windows-x86_64\release\lightspeed.app.trex_dev.profile.bat
.\_build\windows-x86_64\release\lightspeed.app.trex_dev.profile_startup.bat
```
````

If you launch the regular app directly instead of using the profile launcher,
pass the same settings explicitly.

```batch
set CARB_PROFILING_PYTHON=1&& .\_build\windows-x86_64\release\lightspeed.app.trex.bat --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend=[cpu,tracy]
```

After the app opens, follow [Capture an interaction slowdown](#capture-an-interaction-slowdown)
for an on-demand capture, or [Profile startup only](#profile-startup-only) for a
one-shot startup trace.

Traces land under the Toolkit build or install directory as
`logs\Kit\*\*\traces\ct_<timestamp>.gz`. Use **Show Install Directory** on the
Toolkit home screen to find that directory.

```{seealso}
See [How can I locate the RTX Remix Toolkit Installation Folder?](../../docs/remix-faq.md#how-can-i-locate-the-rtx-remix-toolkit-installation-folder)
in the user-facing FAQ.
```

## Capture an interaction slowdown

Use this when startup is fine, but a specific interaction slows down.

1. Start the regular app in profile mode:

   ```batch
   .\_build\windows-x86_64\release\lightspeed.app.trex.profile.bat
   ```

2. Drive the app to the point just before the slowdown usually happens.
3. Press **F5** to start capturing.
4. Reproduce the slowdown.
5. Press **F5** again to stop capturing.
6. Open the latest `ct_<timestamp>.gz` from
   `<Toolkit build or install directory>\logs\Kit\*\*\traces\` by following
   [Opening existing captures](#opening-existing-captures).

## Profile startup only

One-shot capture: runs the app, writes a trace, quits, opens it in Tracy.

```batch
.\_build\windows-x86_64\release\lightspeed.app.trex.profile_startup.bat
```

The launcher enables Python profiling and passes the regular app to Kit's bundled
`profile_startup.bat` helper.

The trace (`startup_profile.gz`) lands in the directory you ran the command from,
and the launcher opens it in Tracy.

## Live Tracy connection

Watch the app in real time as you interact. Load both backends through the
multiplexer:

```batch
.\_build\windows-x86_64\release\lightspeed.app.trex.profile.bat
```

Inside the app, select **Profiler > Tracy > Launch and Connect**, then press
**F5** to start emitting events.

> Use `[cpu,tracy]`, not a bare `tracy`. The Profiler window crashes if the CPU backend
> isn't loaded.

## Finding your code in a trace

Python frames appear with a `(Python)` suffix; Python-interpreter C-API calls with a
`(C)` suffix. For example:

- `omni.flux.stage_manager.factory.items.StageManagerItem.parent (Python)`
- `builtins.hasattr (C)`

In Tracy, **Ctrl+F** searches zone names - type the function or class name and it jumps
to every call site on every thread. Searching by zone is usually faster than scanning
by thread, especially for async code: asyncio work dispatched through `carb.tasking`
runs on pooled fibers labelled `Fiber #N`, and a single coroutine can execute across
many of them.

## Opening existing captures

Captures are gzip traces (`.gz`), not `.zip` files.

Press **F8** to open the Profiler window, then click **Browse** to open the Captured
Traces Browser.

To open a capture in Tracy, click **tracy** beside it. The Toolkit converts the trace
and opens it in the bundled Tracy app.

To open a capture in a Chromium-based browser:

1. Click **unzip** beside the capture to extract its `.json` file.
2. Open `chrome://tracing` in the browser.
3. Load the extracted `.json` file.

```{note}
Widen the Captured Traces Browser window if you don't see the **tracy** or **unzip**
buttons - on narrower widths they get clipped off the right side.
```

Each row also has **stats**, **snakeviz** (cProfile captures only), and **remove** if
you need them.

## References

- [Kit SDK Profiling](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html)
- [Carbonite Profiler API](https://docs.omniverse.nvidia.com/kit/docs/carbonite/latest/api/group__Profiler.html)
- [Tracy manual](https://github.com/wolfpld/tracy)
