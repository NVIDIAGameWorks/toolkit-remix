# Overview

Extension used to try to import optional dependencies when they are available. Extensions will be enabled in a deferred
way, which means that they will be downloaded and enabled when this extension is loaded.

To add dependencies to import, add the extension name in the `exts."lightspeed.dependencies".deferred_dependencies`
setting from the app configuration:

```
[settings]
exts."lightspeed.dependencies".deferred_dependencies = [
    "example.extension",
]
```
