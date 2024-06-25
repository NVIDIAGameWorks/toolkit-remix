# Overview

Extension used to import required test dependencies in a centralized way.

Since this extension depends on `lightspeed.trex.tests.settings` it will also set all the required settings for tests.

To have all the required centralized dependencies, your extension must therefore simply add the following to its
`extension.toml` file:

```
[[test]]
dependencies = [
    "lightspeed.trex.tests.dependencies",
]
```
