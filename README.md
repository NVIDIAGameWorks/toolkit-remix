## Getting Started

1. Building the project for the first time:
   1. Build project: `build.bat -r`
   2. If required (recommended after switching branches) clean using: `build.bat -c`
2. Run:
   1. `_build\windows-x86_64\release\lightspeed.app.trex_dev.bat` for the dev version that has menus.
   2. `_build\windows-x86_64\release\lightspeed.app.trex.bat` for the end-user version.
   3. If you work on a specific sub-app (IngestCraft, TextureCraft...), you can run the sub-app directly like `_build\windows-x86_64\release\lightspeed.app.trex.ingestcraft.bat`

## Developer Guides

- **[Using Pycharm IDE](PYCHARM_GUIDE.md)**: For an intro on developing with Pycharm.
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
