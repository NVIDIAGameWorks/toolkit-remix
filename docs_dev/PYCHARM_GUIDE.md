# Developing with PyCharm

PyCharm is the Integrated Development Environment (IDE) of choice for the RTX Remix Toolkit team. This documentation
provides tips and tricks utilized by team members to enhance their development experience.

## Live Debugging

### Prerequisites

- PyCharm Professional installed on your system (the community edition will not suffice).
- Basic knowledge of Python programming.

### Debugging Steps

#### Step 1: Configuring the Debug Server

1. Launch PyCharm Professional.
2. On the right-hand side, click on "Edit Configurations."
3. Create a new Python debug server configuration.
4. Change the port number to 33100 and save the configuration.

#### [OPTIONAL STEP] Workaround for PyCharm 2024.3

1. Disable `python.debug.use.single.port` in **Help | Find Action | Registry**.
2. Restart PyCharm.

#### Step 2: Starting the Debugger

1. Choose the newly created debug configuration and click "Debug."
2. The debugger will be activated, displaying the debugging interface.

#### Step 3: Running Kit

1. Execute the following command in your terminal or command prompt:

    ```
    lightspeed.app.trex.bat --enable omni.flux.debug.pycharm --/exts/omni.flux.debug.pycharm/pycharm_location="%APPDATA%\Local\Programs\PyCharm Professional"
    ```

   In this command, replace `%APPDATA%\Local\Programs\PyCharm Professional` with the actual path where your PyCharm is
   installed.

Please note that starting the PyCharm server before using the additional options is essential for proper functionality.

#### Step 4: Enjoy Debugging

You can now enjoy debugging your Python code using the powerful features of PyCharm Pro.

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
