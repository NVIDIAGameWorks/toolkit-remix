# Handling Data Migrations

The RTX Remix Toolkit offers a data migration tool to ensure compatibility between older projects and the latest runtime
and toolkit versions. This tool is a batch script that allows users to run all available migrations using a consistent
method.

***

## Finding the Migration Tool

1) Open your
   [Toolkit installation directory](../remix-faq.md#how-can-i-locate-the-rtx-remix-toolkit-installation-folder) in
   File Explorer.
2) Locate the `lightspeed.app.trex.migration.cli.bat` script file.

## Executing the Migration Tool

1) Once in the installation directory, click on the address bar at the top and enter:
    ```bat
    cmd
    ```
   ![CLI Asset Ingestion Tool 3](../data/images/remix-clitool-003.png)
2) This command should open a command prompt window with the current working directory set to the installation directory.
3) Using the command prompt window, execute the `lightspeed.app.trex.migration.cli.bat` script using the following
   command:
    ```bat
    lightspeed.app.trex.migration.cli.bat -h
    ```
4) You should now see the available migrations. Follow the instructions given by the tool to execute the desired
   migrations.

## Performing a Migration

To perform a migration, follow the instruction given by the tool during the previous step.

For example, executing the following command:

```bat
lightspeed.app.trex.migration.cli.bat distant-lights-z-direction -h
```

Should give you instructions on how to migrate the distant lights in your existing project.

***

## Available Migrations

The migration tool is a central point where you can find all available migrations.

### Distant Lights Z Direction

If a mod was created before the following commit:
[Fix orientation of exported (USD captures) distant lights. Comply with the USD standard: -Z axis must point from the sun to the earth.](https://github.com/NVIDIAGameWorks/dxvk-remix/commit/cfa5273ef5d8dd4f7e98b1ef9e5d9cb2552042f4)

The distant lights in the mod were pointing in the wrong direction. This migration will need to be executed once to
invert the direction of the distant lights and fix the issue.

#### Migration Name

`distant-lights-z-direction`

#### Purpose

Migrate distant lights pointing in the wrong direction (Z towards the sun) to point in the correct direction (Z away
from the sun).

#### Arguments

| Argument                                   | Description                                                                                        |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| `--file FILE`<br/>`-f FILE`                | Path to the USD file to migrate to the updated standard                                            |
| `--directory DIRECTORY`<br/>`-d DIRECTORY` | Path to the directory of USD files to migrate to the updated standard                              |
| `--force`<br/>`-F`                         | Force execute the migration, regardless of if it was already executed or not.                      |
| `--recursive`<br/>`-r`                     | Recursively search for USD files in the given directory.<br/>Will be ignored if `--file` is given. |

#### Example Command

```bat
lightspeed.app.trex.migration.cli.bat distant-lights-z-direction -d "PROJECT_DIRECTORY_HERE" -r
```

Where `PROJECT_DIRECTORY_HERE` is replaced with the actual project directory where the migration should be applied.

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
