## Publishing Extensions

Extensions are published to the registry to be used by downstream apps and extensions.

[Kit documentation: Publishing](http://omnidocs-internal.nvidia.com/py/docs/guide/extensions.html#publishing-extensions) covers how to do it manually with command line or UI. However we suggest to automate that process in CI. 

Extensions are published using `repo publish_exts` tool that comes with Kit. `[repo_publish_exts]` section of `repo.toml` lists which extensions to publish. On every green commit to master TC runs `repo publish_exts -c release` and any new extension version is published. 

For versions that already were published nothing happens. So version needs to be incremented for publishing.

You can test publishing locally with `repo publish_exts -c release -n`, where `-n` enabled "dry" run.

It is important to remember that some extensions (typically C++, native) have separate package per platform, so we run publishing separtely on each platform and publish for each configuration (`debug` and `release`).

