# Developing with PyCharm

PyCharm is one of the Integrated Development Environment (IDE) of choice for the RTX Remix Toolkit team. This documentation
provides tips and tricks utilized by team members to enhance their development experience.

## Tips and Tricks

To get started with PyCharm and improve your development workflow, follow these steps:

### Set Up Auto Completion and Environment

Add the project-specific folder `_build\windows-x86_64\release\site` into the Python path. Launch PyCharm and run the
application.

### Run Project Profiles

Run Profiles are available in the repository in the `.run` folder at the root of the project.

NOTE: PyCharm professional will be required for the debug configuration to work because of the need for a remote
debugger setup.

### Add Templates for TreeView and More

Extend the template setup to add more templates, such as creating a TreeView + Model + Delegate.

### Use Project Python Interpreter

Configure PyCharm to use the Python interpreter of the project (File->Settings->Project->Interpreter).

### Ignore Specific Folders

Ignore unnecessary folders like the _build folder (File->Settings->Project->Structure). Avoid using the _ * wildcard, as
it may also ignore _init_.py files.

### Create Scope Specific to Kit Architecture

Define scopes specific to the Kit architecture, such as:

- Project extension (to look only inside the extensions folder of the project)
- Project Python extension
- Project C++ extensions

### Add Repo Tools as External Tools

Add repository tools as external tools in PyCharm (File->Settings->External Tools).

For example, set up hotkeys to run repo format_code or repo lint_code on the selected file, opened file, or selected
folder using the provided macros for directories (e.g., $ProjectFileDir$\format_code.bat).

By following these steps, you can harness the power of PyCharm and tailor it to your specific needs, making your
development experience more efficient and enjoyable.

## Debugging the Toolkit

Check out the [DEBUGGING_GUIDE](DEBUGGING_GUIDE.md) docs for more info on how to attach debuggers to the
toolkit.
