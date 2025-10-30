```{csv-table}
**Extension**: {{ extension_version }},**Documentation Generated**: {sub-ref}`today`,{ref}`changelog_lightspeed.trex.components.ogn`
```

(ext_lightspeed.trex.components.ogn)=

# Overview

This extension is based on the `omni.graph.template.python` template extension for creating a Kit extension that contains only Python OmniGraph nodes.

## The Files

The convention of having implementation details of a module in the ``_impl/`` subdirectory is to make it clear to the
user that they should not be directly accessing anything in that directory, only what is exposed in the ``__init__.py``.

## The Build File

Kit normally uses premake for building so this example shows how to use the template ``premake5.lua`` file to customize
your build. By default the build file is set up to correspond to the directory structure shown above. By using this
standard layout the utility functions can do most of the work for you.

`lightspeed.trex.logic.ogn/premake5.lua`

By convention the installed Python files are structured in a directory tree that matches a namespace corresponding to
the extension name, in this case `omni/graph/template/python/`, which corresponds to the extension name
the extension name, in this case `lightspeed/trex/logic/ogn/`, which corresponds to the extension name
*lightspeed.trex.logic.ogn*. You'll want to modify this to match your own extension's name. Changing the first
highlighted line is all you have to do to make that happen.

## The Configuration

Every extension requires a ``config/extension.toml`` file with metadata describing the extension to the extension
management system. Below is the annotated version of this file, where the highlighted lines are the ones you should
change to match your own extension.

Contained in this file are references to the icon file in ``data/icon.svg`` and the preview image in
``data/preview.png`` which control how your extension appears in the extension manager. You will want to customize
those.

## Documentation

Everything in the ``docs/`` subdirectory is considered documentation for the extension.

- **README.md** The contents of this file appear in the extension manager window so you will want to customize it.
  The location of this file is configured in the ``extension.toml`` file as the **readme** value.
- **CHANGELOG.md** It is good practice to keep track of changes to your extension so that users know what is available.
  The location of this file is configured in the ``extension.toml`` file as the **changelog** value, and as an entry
  in the *[documentation]* pages.
- **Overview.md** This contains the main documentation page for the extension. It can stand alone or reference an
  arbitrarily complex set of files, images, and videos that document use of the extension. The **toctree** reference
  at the bottom of the file contains at least *GeneratedNodeDocumentation/*, which creates links to all of the
  documentation that is automatically generated for your nodes.
  The location of this file is configured in the ``extension.toml`` file in the *[documentation]* pages section.
- **directory.txt** This file can be deleted as it is specific to these instructions.

## The Node Type Definitions

You define a new node type using two files, examples of which are in the ``nodes/`` subdirectory. Tailor the
definition of your node types for your computations. Start with the OmniGraph User Guide for information on how
to configure your own definitions.

## Tests

While completely optional it's always a good idea to add a few tests for your node to ensure that it works as you
intend it and continues to work when you make changes to it. Automated tests will be generated for each of your node
type definitions to exercise basic functionality. What you want to write here are more complex tests that use your
node types in more complex graphs.

The sample tests in the ``tests/`` subdirectory show you how you can integrate with the
[Kit testing framework](https://docs.omniverse.nvidia.com/kit/docs/kit-manual/latest/guide/testing_exts_python.html)
to easily run tests on nodes built from your node type definition.

That's all there is to creating a simple Python node type! You can now open your app, enable the new extension, and your
sample node type will be available to use within OmniGraph.
