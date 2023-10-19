# Profiling your app from the start

## Step 1: run Tracy

Download and run Tracy form here: https://github.com/wolfpld/tracy

## Step 2: run the app with profiler extensions

Run the app with those args:
```
--enable omni.kit.profile_python --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend="tracy" --/app/profileFromStart=true
```

This will enable the profiling when your start your app.

# Profiling your code

If you don't need to run the profiling at the beginning, just run with:
```
--enable omni.kit.profile_python --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend="tracy"
```

After you can push `F5` to start/stop the profiling.

# Links
https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html
