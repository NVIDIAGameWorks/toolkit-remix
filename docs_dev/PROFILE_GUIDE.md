# Profiling your app from the start

## Step 1: Run Tracy

Download and run Tracy from [here](https://github.com/wolfpld/tracy).

## Step 2: Run the app with profiler extensions

Execute the app with the following arguments:

```
--enable omni.kit.profile_python --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend="tracy" --/app/profileFromStart=true
```

This enables profiling when starting your app.

# Profiling your code

If you don't need to run profiling from the beginning, simply run with:

```
--enable omni.kit.profile_python --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend="tracy"
```

Then, you can press `F5` to start/stop the profiling.

## Additional Documentation

- [Kit SDK Profiling Documentation](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/profiling.html)
