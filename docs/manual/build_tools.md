# Build Tools

## Packman

The basic package management tool used on OV, see [packman](https://gitlab-master.nvidia.com/hfannar/packman). A copy of the currently used packman lives in tools/packman in most repositories. It can be easily upgraded to newer versions

## Repo Tools "RepoMan"

These are a set of small utility libraries whose source lives in [https://gitlab-master.nvidia.com/omniverse/repo](https://gitlab-master.nvidia.com/omniverse/repo). They are dependencies of your project (you can set their versions by changing `deps/repo-deps.packman.xml`, or using `repo update`. The first time you build your project, the chosen versions will be downloaded and linkd into `_repo`.

They have a single entry point which is `./repo.sh[.bat]` in the root of your repo.  

Call `repo.bat` to see a list of all available tools. Each command can be explored with `--help` flag.

Each tool defines default settings in their `repo_tools.toml` file. E.g. look at `_repo/deps/repo_format/repo_tools.toml` for format tool settings. `repo_tools.toml` is a tool definition file.

Repo can override those settings using `repo.toml` file. When any tool runs this config is applied on top of tools `repo_tools.toml`. Notice that `repo.toml` supports applying extra configuration using `repo.import_configs` settings. It is used to share many settings between extension repos in common package.

### repo build

Example Usage: `repo.bat build -r` or `build.bat -r` 

Simply, this will build your project. In more detail, it will:

1. pull and link dependencies (via packman),
2. setup vscode (generate python stub files and all of the other plumbing needed to get good intellisense/code completion for vscode in your project, as well as with Kit, USD etc)
3. Generate  license files
4. file copy and link
5. pip install
6. project generation
7. toolchain build call (which in the case of pure python is eally just creating some symlinks. This is equivalent to calling ./build.[.sh][.bat] from the root of the repo

### repo docs

Example usage: `repo.bat docs`

Builds documentation from the release build of your project.

Document your python code with [Google Docstring](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html), more info in: (http://nv/repo_docs)


### repo publish_ext

Example usage: `repo.bat publish_ext -c release -n`

This will publish extensions to the registry.

_This will normally be called by TC_ rather than locally. 

### repo package

Example usage: `repo.bat package -a`

Prepares final package in `_build/packages`.

It will build zip/7z artifacts which are passed between CI jobs. We don't package kit inside to save space, instead we prepare special bat file `pull_kit_sdk.bat` to pull it from packman before running tests.

### repo test

Example usage: `repo.bat test --config debug`

Very simple entry point for running your tests locally or on TC.

When you do a build, premake will generate bat/sh scripts that will run your tests, e,g `tests-python-omni.kit.widget.collection.sh`. This is just starting up Kit, enabling the appropriate extensions, and running their test. `repo test` is running those scripts, as defined in `repo.toml`.

As well as running tests, it will look for particular patterns in the output (stdout/stderr) to fail on, and others to ignore (configurable).

To run tests on TC it uses `--from-package` flag to unpack package and run tests in it. You can do that locally, by downloading TC artifact into `_build/packages` and running with `--from-package`.

### repo source

This allows you to link to local versions of packman dependencies.

### repo format

This will format C++ and Python code according to OV conventions (using black for Python). It can also verify formatting is correct.

### repo update

This updates your dependencies by modifying the `deps/*xml` files to the latest versions (major/minor constraints can be specified).

This is a local only step. E.g. to update all tools run `repo update repo_`.

### repo changelog

Future work is to update this so it can automatically generate the changelogs for extensions from git commits - currently it works mostly for Kit-based applications

### repo build_number

Used by TC only to generate full build number.

## Tools and CI

Many of them are used by Teamcity to execute various parts of the build pipeline (build/package/publish etc), but many of them can be executed locally also to perform various tasks

A simplified build pipeline as used by most tools is: 
```
build->package->test->publish
```

CI: Normally the repo tools are called via a batch file (.bat/.sh) in teamcity. As a general principle, we should be able to run the same thing locally by just calling the batch script.. Below in yellow is an example script. 

![alt_text](../../data/readme_images/TC_build_step.png "TC pipeline")

They live in the ./tools folder of your repo

There are many repo tools, the version of each to use is defined in deps/repo-deps.packman.xml in each repository, and the code for these is downloaded to the `_repo` folder

General notes:
* Some of these tools work with your local source, some of them work with packaged artefacts, some give you the option of either. Normally TC jobs will be working with packaged artefacts
* Some of them require you to specify a "config" e.g release or debug, via -c/--config usually. Some default to debug if nothing is passed
* If you cannot work out why TC jobs are failing, it can be useful to log into the host after the job has completed. Ask on #ct-teamcity, they will allow you access to a host, where you can ssh in via [http://10.36.9.12:8080/guacamole-1.2.0/#/](http://10.36.9.12:8080/guacamole-1.2.0/#/)
* Not all TC jobs are equal - some stages of the pipeline are triggered by any commit to an MR, some (e.g publishing) might only happen on master
* Most build/packaging/testing etc is done separately for Windows/Linux (and now ARM) platforms, even for Python only


## VSCode

Kit and OV projects in general are set up to use VSCode. You’ll usually find the following in a .vscode folder in your repo (Note: Work out when these files are generated/updated.. At build time?)

*   c_cpp_properties.json
*   extensions.json
*   global-snippets.code-snippets
*   json.code-snippets
*   launch.json
*   settings.json
*   settings.template.json
*   tasks.json

to get going, Install VsCode python extension, close VsCode, run `build.bat` first time (`-s` flag is enough), open project again. Python intellisense, linter, formatting should work (we bring our own version of python).
