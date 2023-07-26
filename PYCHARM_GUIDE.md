# Developing with PyCharm
## Live Debugging

### Overview

This guide provides instructions on how to use PyCharm Pro for Python live code debugging. PyCharm Pro is a powerful Integrated Development Environment (IDE) for Python development that offers comprehensive debugging features to streamline the debugging process.

### Prerequisites

-   PyCharm Pro installed on your system (won't work with community edition).
-   Basic knowledge of Python programming.

### Debugging Steps

#### Step 1: Configuring the Debug Server

1.  Launch PyCharm Pro.
2.  On the left-hand side, click on "Edit Configurations."
3.  Create a new Python debug server configuration.
4.  Change the port number to 33100 and save the configuration.

#### Step 2: Starting the Debugger

1.  Choose the newly created debug configuration and click "Debug."
2.  The debugger will be activated, and you will see the debugging interface.

#### Step 3: Running Kit

1.  Run the following command in your terminal or command prompt: `omni.app.lightspeed.bat --enable omni.kit.debug.pycharm --/exts/omni.kit.debug.pycharm/pycharm_location="C:/Program Files/JetBrains/PyCharm 2023.1.3"`

In this command, replace `C:/Program Files/JetBrains/PyCharm 2023.1.3` with the actual path where your PyCharm is installed.

Please note that starting the PyCharm server before using the additional options is essential for proper functionality.

#### Step 4: Enjoy Debugging

You can now enjoy debugging your Python code using the powerful features of PyCharm Pro.

## Tips and Tricks
To get started with PyCharm and improve your development workflow, follow these steps:

### Tip 1: Set Up Auto Completion and Environment
Add the project specific folder \_build\windows-x86_64\release\site into the Python path.
Launch PyCharm and run the application.

### Tip 2: Run Project Profiles
Create launch configurations to run your project directly from PyCharm.
e.g. To enable the profile extension automatically to connect with Tracy using the following command
`--enable omni.kit.profile_python --enable omni.kit.profiler.tracy --enable omni.kit.profiler.window --/app/profilerBackend="tracy" --/app/profileFromStart=true`

### Tip 3: Add Templates for TreeView and More
Extend the template setup to add more templates, such as creating a TreeView + Model + Delegate.

### Tip 4: Use Project Python Interpreter
Configure PyCharm to use the Python interpreter of the project (File->Settings->Project->Interpreter).

### Tip 5: Ignore Specific Folders
Ignore unnecessary folders like the _build folder (File->Settings->Project->Structure). Avoid using the _* wildcard, as it may also ignore _init_.py files.

### Tip 6: Create Scope Specific to Kit Architecture
Define scopes specific to the Kit architecture, such as:
- Project extension (to look only inside the extensions folder of the project)
- Project Python extension
- Project C++ extensions

### Tip 7: Add Repo Tools as External Tools
Add repository tools as external tools in PyCharm. (File->Settings->External Tools).
For example, set up hotkeys to run repo format_code or repo lint_code on the selected file, opened file, or selected folder, use the provided macros for directories (e.g. `$ProjectFileDir$\format_code.bat`)

By following these steps, you can harness the power of PyCharm and tailor it to your specific needs, making your development experience more efficient and enjoyable. Happy coding!

## Conclusion

With PyCharm Pro and the provided instructions, you can effectively debug your Python code and improve your development workflow. Enjoy the benefits of PyCharm's powerful debugging features and make your Python development experience smoother and more efficient! Happy coding!
