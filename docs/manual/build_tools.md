# Build Tools

## Packman

The basic package management tool used on OV, see [packman](https://gitlab-master.nvidia.com/hfannar/packman). A copy of the currently used packman lives in tools/packman in most repositories. It can be easily upgraded to newer versions

## Repo Tools "RepoMan"

These are a set of small utility libraries whose source lives in [https://gitlab-master.nvidia.com/omniverse/repo](https://gitlab-master.nvidia.com/omniverse/repo). They are dependencies of your project (you can set their versions by changing deps/repo-deps.packman.xml, or using `repo source`. The first time you build your project, the chosen versions will be downloaded into `_repo`.

They have a single entry point which is `./repo.sh[.bat]` in the root of your repo.  

Calling this on it's own will show a list of available tools. Each command can be explored with `--help` flag.


They are configured via a number of `*.toml` files in the root of your repository (mostly repo.toml)
 
What do they do? Many of them are used by Teamcity to execute various parts of the build pipeline (build/package/publish etc), but many of them can be executed locally also to perform various tasks

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
* In order to call your repo setup a success, I think you would have to be able to run your CI pipeline successfully, and successfully run at least build and test locally (ideally on multiple platforms)
* If you cannot work out why TC jobs are failing, it can be useful to log into the host after the job has completed. Ask on #ct-teamcity, they will allow you access to a host, where you can ssh in via [http://10.36.9.12:8080/guacamole-1.2.0/#/](http://10.36.9.12:8080/guacamole-1.2.0/#/)
* Not all TC jobs are equal - some stages of the pipeline are triggered by any commit to an MR, some (e.g publishing) might only happen on master
* Most build/packaging/testing etc is done separately for Windows/Linux (and now ARM) platforms, even for Python only

There are additional flags for most tools, all documented in the tool itself via --help e.g
```
repo.sh changelog --help
```

#### repo build

Basic Usage: `repo.bat build` or `build.bat` 

Simply, this will build your project. In more detail, it will:

1. pull and link dependencies (via packman),
2. setup vscode (generate python stub files and all of the other plumbing needed to get good intellisense/code completion for vscode in your project, as well as with Kit, USD etc)
3. Generate  license files
4. file copy and link
5. pip install
6. project generation
7. toolchain build call (which in the case of pure python is eally just creating some symlinks. This is equivalent to calling ./build.[.sh][.bat] from the root of the repo

**VSCode**
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

#### repo build_doc

Basic usage: `repo.bat build_docs` or `tools/build_docs.bat`

Builds documentation from the debug build of your project. Not sure if this is used in practice with extensions 

With the template project, results will be built in `_build/docs`.

Document your python code with [Google Docstring](https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html), more info in: (https://gitlab-master.nvidia.com/carbon/Carbonite/blob/master/docs/Documenting.md)


#### repo publish_ext

This will publish extensions to the test extension repository which is used by ETM (Extension Test manager)to test extensions when kit sdk versions and other apps are updated (see ##ct-omni-extensions-testing-matrix

_This will normally be called by TC_ rather than locally

#### repo package

Basic usage: `repo.bat package` or `tools/package.bat`

Prepares final package.

It will build zip/7z artefacts which can be published to packman (e.g http://packman.ov.nvidia.com/packages/omniverse-kit is where kit packages end up). With extension repos, that’s not usually how we publish our extensions anymore (we’re still transitioning though) so mostly this is just used by TC to pass to successive pipeline stages. Different platforms will be built normally on their respective machine types.

Normally the different artefacts per platform/configuration are stored in _build/packages or _build/builtpackages(this is of course configurable)

Example:

`./repo.sh package -a`


```bash
Creating 7z archive: '/home/eoinm/code/omniverse/kit-extensions/kit-usd/_build/packages/kit-usd-extensions@101.1.0+collection_1.0.ce3e9c61.gitlab.linux-x86_64.debug'...
Creating 7z archive: '/home/eoinm/code/omniverse/kit-extensions/kit-usd/_build/packages/kit-usd-extensions@101.1.0+collection_1.0.ce3e9c61.gitlab.linux-x86_64.release'...
```


An archive should be self contained, in the sense that if it doesn’t contain everything it needs to run the extensions, it should contain scripts to bootstrap itself or download dependencies(e.g there’s a “pull_kit_sdk.sh” script which downloads kit… this can be added to your build by including: \
`dofile("tools/autopull/premake5.lua")`..in your main premake5.lua file

#### repo publish

This will publish to packman. As above, should not generally be needed for extensions


#### repo test

Very simple entry point for running your tests (startup and unit?) locally, or on TC

This is what TC will run on the packaged build.

When you do a build, some magic in the build will generate some bat/sh scripts that will run your tests, e,g “tests-python-omni.kit.widget.collection.sh”. This is just starting up Kit, enabling the appropriate extensions, and running their test. “Repo test” is just running those scripts

As well as running tests, it will look for particular patterns in the output (stdout/stderr) to fail on, and others to ignore (configurable).

There’s an assumption that:
*   if you are running tests locally that you have a local kit build, which can be found by looking at depts/kit-sdk.packman.xml (you can update this to a local dev checkout or any kit by using repo source to modify the dependency, see below)
*   If you are running on TC, you don’t so a kit will have to be checked out

Note: `${test_root}` will be set if you run `--from-package`

Kit-template also provide examples of writing different tests. They all grouped into one test suite and defined in `repo.toml` file.

Example usage:

> `repo.bat test --config debug`


#### repo source

This allows you to link to local versions of packman dependencies

#### repo format

Basic usage: `repo.bat format` or `format_code.bat`
This will format C++ and Python code according to OV conventions (using black for Python).It can also verify formatting is correct

This is currently optional (ie run manually/locally)

#### repo update

This updates your dependencies by modifying the `deps/*xml` files to the latest versions (major/minor constraints can be specified)

This is a local only step

#### repo licensing

Will generate licence files for your extensions… most of this is actually handled at the build stage, so not sure where it's neede

#### repo changelog

Future work is to update this so it can automatically generate the changelogs for extensions from git commits - currently it works mostly for Kit-based applications

#### repo build_number

Used by TC only
