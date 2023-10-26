# Omniverse Development Tips

## Development

When you need to update extension versions, there's a quick way to handle all dependencies and .kit files. Simply run the command: `./build.bat -r -u`
This command automatically updates all dependencies to the latest available versions. However, be cautious, as other developers might add new versions of extensions, and this behavior may not always be desired.

This command will also most likely require cleaning the `.kit` files after the execution since empty lines will be added/removed before/after the generated sections.

### Linking local dependencies

Since you will most likely be modifying extensions from external repositories (IE: `kit-flux`) locally and testing them in different project (IE: `lightspeed-kit`), it is useful to be able to use a linked local repository instead of published extensions when developing a feature or fixing a bug.

To do so, simply create the following file in the parent project (IE: `lightspeed-kit`): `./deps/user.toml`.

The content of that file should be as follows:
```
[app.exts]
folders."++" = [
    "PATH\\TO\\kit-flux\\_build\\windows-x86_64\\release\\exts",
    "PATH\\TO\\kit-flux\\_build\\windows-x86_64\\debug\\exts",
]

```
**IMPORTANT:** Replace `PATH\\TO\\` with the correct path for your setup. You should end up with a valid path that points to your local external repository.

### Using a local build of the Kit SDK

Sometimes when a fix must be applied to the Kit SDK itself, it is required to run a local build of the SDK to be able to test your branch.

To do so, simply create the following file in the project you want to use the local build of kit for: `.deps/kit-sdk.packman.xml.user`

The content of that file should be as follows:
```
<project toolsVersion="5.6">
	<dependency name="kit_sdk_${config}" linkPath="../_build/${platform}/${config}/kit">
		<source path="PATH/TO/kit/kit/_build/${platform}/${config}" />
	</dependency>
</project>
```
**IMPORTANT:** Replace `PATH/TO/` with the correct path for your setup. You should end up with a valid path that points to your local `kit` repository.

## Documentation

The most efficient way to understand how something works is by searching within the kit extensions code: [kit extensions code](https://gitlab-master.nvidia.com/omniverse/kit/-/blob/master/kit/source/extensions). For instance, you can look for `ui_test.find(...)`, which utilizes `omni.ui_query(...)`. The relevant documentation for this can be accessed [here](https://gitlab-master.nvidia.com/omniverse/kit/-/blob/master/kit/source/extensions/omni.ui_query/docs/TUTORIAL.md).

While there are official Omniverse development documents available, it's essential to note that there is no guarantee that you'll find everything you're looking for. You can access the official documentation [here](http://omniverse-docs.s3-website-us-east-1.amazonaws.com/home/).

The recommended way to proceed when documentation cannot be found would be to have a clone of the [Omniverse Kit Repository](https://gitlab-master.nvidia.com/omniverse/kit/-/tree/master/kit) on your development machine to be able to search the codebase directly.
