# Omniverse Development Tips

## Development

When you need to update extension versions, there's a quick way to handle all dependencies and .kit files. Simply run the command: `./build.bat -r -u`
This command automatically updates all dependencies to the latest available versions. However, be cautious, as other developers might add new versions of extensions, and this behavior may not always be desired.

## Documentation

The most efficient way to understand how something works is by searching within the kit extensions code: [kit extensions code](https://gitlab-master.nvidia.com/omniverse/kit/-/blob/master/kit/source/extensions). For instance, you can look for `ui_test.find(...)`, which utilizes `omni.ui_query(...)`. The relevant documentation for this can be accessed [here](https://gitlab-master.nvidia.com/omniverse/kit/-/blob/master/kit/source/extensions/omni.ui_query/docs/TUTORIAL.md).

While there are official Omniverse development documents available, it's essential to note that there is no guarantee that you'll find everything you're looking for. You can access the official documentation [here](http://omniverse-docs.s3-website-us-east-1.amazonaws.com/home/).
