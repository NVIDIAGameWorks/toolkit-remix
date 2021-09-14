## Repo Overview

### Extensions

During build phase extensions are built (native), staged (copied and linked) into `_build/{platform}/{config}/exts` folder. Custom app (`.kit` file config) is used to enable those extensions.

Each extension is a folder (or zip archive) in the end. You can write user code in python code only, or C++ only, or both. Ultimately extension archive could contain python code, python bindings (pyd/so files) and C++ plugins (dll/so). Each binary file is platform and configuration (debug/release) specific. For python bindings naming we follow [Python standards](https://stackoverflow.com/a/37028661).

For more info refer to [Kit documentation](http://omnidocs-internal.nvidia.com/py/index.html). 

#### example.python_ext

Example of pure python extension

src: `source/extensions/example.python_ext`


#### example.cpp_ext

Example of native (C++ only) extension.

src: `source/extensions/example.cpp_ext`


#### example.mixed_ext

Example of mixed extension which has both C++ and python code. They interact via python bindings built and included with this extension.

src: `source/extensions/example.mixed_ext`

### Simple App

Example of an app which runs only those 3 extensions in Kit (and test_runner for tests). All configs are in `source/apps`, they are linked during build (stage phase).

src: `source/apps/omni.app.new_exts_demo_mini.kit`

> `_build\windows-x86_64\release\omni.app.new_exts_demo_mini.bat`

### Running Kit from Python

It also includes example of running Kit from python, both default Kit and an app which runs only those 3 extensions in Kit. 

> `_build\windows-x86_64\release\example.pythonapp.bat`

That runs default python example, to see list of examples:

> `_build\windows-x86_64\release\example.pythonapp.bat --help`

Pass different one as first argument to run it.

### App that brings extra extensions

Another app included: `source/apps/omni.app.precache_exts_demo.kit`. It has a dependency that comes from extension registry. Kit will automatically resolve and download missing extensions when started. But usually we download them at build-time and package final application with everything included to work offline. That is done using `repo precache_exts` tool. It runs after build, starts *Kit* with special set of flags to download all extensions.

In `[repo_precache_exts]` section of `repo.toml` you can find list of kit files it uses.

Also it locks all versions of each extension, including implicit dependencies (2nd, 3rd etc order) and writes back into the kit file. You can fine generated section in the end of kit file. This version lock is then should be committed. That provides reproducible builds and makes kit file completely and immutably define whole application.

To regenerate version lock either delete that section and do clean build, or run `repo precache_exts -u`.


### Config files

* `premake5.lua` - all configuration for generating platform specific build solutions. [premake5 docs](https://github.com/premake/premake-core/wiki).
* `repo.toml` - configuration of all repo tools (build, package, format etc).

Notice `import_configs = ["${root}/_repo/deps/repo_kit_tools/kit-template/repo.toml"]` in `repo.toml`. That is a feature of `repo_man` to import another configuration. In practice it means that this `repo.toml` is merged later on top of imported one. You can find many more shared settings in this file.

Premake file also imports shared configuration with `dofile("_repo/deps/repo_kit_tools/kit-template/premake5.lua")` line.


### CI / Teamcity

[Teamcity Project](https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds) runs on every commit. Builds both platforms, docs, runs tests. Publishing is optional (click "Run" on "publish" configuration).

Teamcity configuration is stored in the repo, in `.teamcity` folder. All Teamcity entry points are in `tools/ci` folder.

It can also be easily copied in Teamcity along with forking this project on gitlab.

