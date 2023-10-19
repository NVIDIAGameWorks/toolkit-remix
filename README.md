## Getting Started

### Overview
RTX Remix app is built using the Kit SDK: https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/kit_overview.html

You need to read what is the Kit SDK (what is an extension, what is USD, and so on).

You can learn Pixar USD with those websites:
- https://learnusd.github.io/index.html
- https://lucascheller.github.io/VFX-UsdSurvivalGuide/index.html
- https://remedy-entertainment.github.io/USDBook/index.html

RTX Remix app uses a "barebone" Kit that we extend with extensions that we code. Those extensions come from
different repos (this one, Flux, etc etc...)


### Repos
The RTX Remix App is mainly built using 2 repos:
- this one
- Flux: https://gitlab-master.nvidia.com/omniverse/kit-extensions/kit-flux

#### Flux
Flux is a set of extensions that are not specific to the RTX Remix app, that can also be used anywhere else.

Meaning that there is no specific implementation of any app into Flux.

Example: we want the RTX Remix app to show a list of USD prims. What we can do here is:
- create an extension in Flux that will show a list of things (with no implementation of USD)
- create an extension in the RTX Remix app repo that will set the extension from Flux as a dependency, and implement
the USD stuffs.

Flux is like an "interface". Sometime Flux can also have some implementation when we see that those implementations
are "common use/general".

When there is something that we want to add to the RTX Remix app, and this thing is really specific to the RTX Remix
app, we code the extension directly into this repo (like the layout of the app).

#### Building
1. Building the project for the first time:
   1. Clone this repo
   2. Build project: `build.bat -r`
   3. If required (recommended after switching branches) clean using: `build.bat -c`
2. Run:
   1. `_build\windows-x86_64\release\lightspeed.app.trex_dev.bat` for the dev version that has menus.
   2. `_build\windows-x86_64\release\lightspeed.app.trex.bat` for the end-user version.
   3. If you work on a specific sub-app (IngestCraft, TextureCraft...), you can run the sub-app directly like `_build\windows-x86_64\release\lightspeed.app.trex.ingestcraft.bat`

## Developer Guides

### Quick start
When you have to code something:
1. Create a branch (generally we do `dev/your_name/your_branch_name`)
2. Code
3. Commit and push
4. Create your MR
5. Advertise your MR into the RTX Remix channels

### More links

- **[Using Pycharm IDE + debug](PYCHARM_GUIDE.md)**: For an intro on developing with Pycharm + how to debug.
- **[How to profile](PROFILE_GUIDE.md)**: For an intro on how to profile.
- **[Review Checklist](REVIEW_CHECKLIST.md)**: What to do as an engineer submitting merge requests.
- **[Automated Testing](TESTING_GUIDELINES.md)**: Process for writing/deploying tests in lightspeed for kit applications.
- **[Omniverse Dev Tips](OMNIVERSE_TIPS.md)**: Tips and tricks for developing on Omniverse from engineers.

## Publishing a new App Version to the OV Launcher

To bump the RTX Remix app version number, there are 3 files that need to be updated.
***Attempts to publish to the OV launcher without first making sure that these***
***files are properly updated will result cause incorrect versions to be displayed,***
***or will cause the pipeline to outright fail.***

The files that need to be updated are outlined below:

```
  ./launcher.toml
    #displayed before application name in launcher
    productArea = "Omniverse"
    version = "2022.X.X"

  ./VERSION.md
    2022.X.X

  ./source/apps/omni.app.lightspeed.kit
    title = "Lightspeed Kit"
    description = "Used for lightspeed remastering."
    version = "2022.X.X"
```

Once these files have been updated and your merge request has been approved and merged
to master, a quick check/build/test pipeline will run.

After the check/build/test pipeline completes and you are ready to publish the new version,
click the play button for the manual job that was created after your MR was merged.

The publish process takes about ~20 minutes as Aug 2022.

Please make sure to test the new version by downloading it from the launcher.

# Kit Extensions & Apps Example :package:

This repo is the gold standard for building Kit extensions and applications.

The idea is that you fork it, trim down parts you don't need and use it to develop your extensions and applications. Which then can be packaged, shared, reused.

This README file provides a quick overview.  In-depth documentation can be found at:

&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;📖 http://omniverse-docs.s3-website-us-east-1.amazonaws.com/kit-template

[Teamcity Project](https://teamcity.nvidia.com/project/Omniverse_KitExtensions_KitTemplate?mode=builds)


## Using a Local Build of Kit SDK

By default packman downloads Kit SDK ([target-deps.packman.xml](deps/target-deps.packman.xml)). For developing purposes local build of Kit SDK can be used.

To use your local build of Kit SDK, assuming it is located say at `C:/projects/kit`.

Use `repo_source` tool to link:

> `repo source link kit-sdk c:/projects/kit/kit`

Or use GUI mode to do source linking:

> `repo source gui`

Or you can also do it manually: create a file: `deps/target-deps.packman.xml.user` containing the following lines:

```xml
<project toolsVersion="5.6">
	<dependency name="kit_sdk_${config}" linkPath="../_build/${platform}/${config}/kit">
		<source path="c:/projects/kit/kit/_build/$platform/$config" />
	</dependency>
</project>
```

To see current source links:

> `repo source list`

To remove source link:

> `repo source unlink kit-sdk`

To remove all source links:

> `repo source clear`


## Using a Local Build of another Extension

Other extensions can often come from the registry to be downloaded by kit at run-time or build-time (e.g. `omni.app.precache_exts_demo.kit` example). Developers often want to use local clone of their repo to develop across multiple repo simultaneously.

To do that additional extension search path needs to be passed into kit pointing to the local repo. There are many ways to do it. Recommended is using `deps/user.toml`. You can use that file to override any setting.

Create `deps/user.toml` file in this repo with the search to path to your repo added to `app/exts/folders` setting, e.g.:

```toml
[app.exts]
folders."++" = ["c:/projects/extensions/kit-converters/_build/windows-x86_64/release/exts"]
```

Other options:
* Pass CLI arg to any app like this: `--ext-folder c:/projects/extensions/kit-converters/_build/windows-x86_64/release/exts`.
* Use _Extension Manager UI (Gear button)_
* Use other `user.toml` files, refer to [Kit Documentation: Configuration](http://omnidocs-internal.nvidia.com/py/docs/guide/configuration.html#user-settings).

You can always find out where extension is coming from in _Extension Manager_ by selecting an extension and hovering over open button or in the log (search for e.g. `[ext: omni.kit.tool.asset_importer`).

## Tips for Adding to README

If you add a new MD file, please also add it to the `sphinx_exclude_patterns` in `repo.toml`.  Otherwise the doc builder will complain.

# Other Useful Links

+ See [Kit documentation](http://omnidocs-internal.nvidia.com/py/index.html)
+ See [Nathan Cournia's repo tools example](https://gitlab-master.nvidia.com/omniverse/repo/repo_example)
+ See [Anton's Video Tutorials](https://drive.google.com/drive/folders/1XAmdhYQkTQlLwDqHOlxJD7k6waUxYAo7?usp=sharing) for Anton’s videos about the build systems.
+ See [Carbonite documentation](https://nv/carb-docs/latest)

# Questions?
If you have any question, please use the channels and not try to ask in private message to some people.

Why?

- Because any answer can be useful for others
- You will have more help because multiple people are in those channels
