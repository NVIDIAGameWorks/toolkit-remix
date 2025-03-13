# Ingest Assets

The RTX Remix Toolkit is your go-to for refining game capture assets by removing specific elements like shaders and texture formats. Follow this step-by-step guide to streamline the process:

## How to Ingest an Asset

1. **Check File Format:** Ensure your asset is in an acceptable format (refer to the [Format Section](../remix-formats.md) for details) and load the asset into Remix.
2. **Access the Ingest Tab:** Open the Remix window and locate the **Ingest** tab on the top right.  Choose the _Asset(s) Tab_`*` from the vertical left tabs.
3. **Upload Source Asset:** Click the **Add** button under the **Input File Path** panel then upload your source asset file.
4. **Set Output Directory:** Paste a folder link into the output directory bar or browse to the directory using the folder icon.
5. **Specify Asset Format:** Choose the desired asset format (USD, USDA, or USDC).
6. **_[OPTIONAL]_** Set optional parameters such as the _asset scale factor_`**`.
7. **Add to Queue:** Press the "Add to Queue" button to initiate the cleanup process.
8. **Post-Ingestion Validation:** After the ingestion process, navigate to the validation tab then access a detailed report on your asset ingestion.

```{warning}
Issues with Ingestion will be highlighted in red with corresponding error messages.
```

```{note}
All Ingested files, even textures & Assets, will have Metadata files.
```

### Notes:

- `*` **Asset(s) Tab:** Texture can be ingested almost the same way other assets are ingested.
    The main difference is simply that every ingested texture must have an assigned texture type to ensure it is processed correctly.
- `**` **Asset Scale Factor**: Additional information about the asset scale factor can be found in the [Omniverse USD documentation](https://docs.omniverse.nvidia.com/usd/latest/learn-openusd/independent/units.html).

## CLI Asset Ingestion Tool (Advanced)

For advanced users there is a CLI tool that can be used to ingest large batches of assets.

### Finding Install Directory

In order to run the CLI Tool, you will need to know where RTX Remix is installed.

Please refer to the [Installation Guide](../remix-installation.md#locating-the-rtx-remix-toolkit-installation-directory)
for instructions on how to locate the RTX Remix install directory.

### Running CLI Asset Ingestion Tool

Follow these steps to run the CLI Asset Ingestion Tool for customizing your assets:

1. Copy Schema File:
    * Locate the schema file for Model Ingestion:
        `<INSTALL_DIRECTORY>\exts\lightspeed.trex.app.resources\data\validation_schema\model_ingestion.json`
    * For Texture Ingestion:
        `<INSTALL_DIRECTORY>\exts\lightspeed.trex.app.resources\data\validation_schema\material_ingestion.json`
    * Save the path to this file as SCHEMA_PATH for later reference.
2. Open Schema File in Text Editor:
    * Open the file in a text editor.
    * Update the list of files to ingest in the `context_plugin -> data -> input_files` (Tip: Use a script to save time).
    * Update the output directory in `context_plugin -> data -> output_directory`.
    * Save the schema file.
3. Execute Commands in CMD:
    * Open a cmd window.
    * Navigate to the installation location of the app.
    * Execute the following commands:
        ```bat
        lightspeed.app.trex.ingestcraft.cli.bat -s SCHEMA_PATH -ex 1
        ```
4. Note on Arguments:
    * `-s`: Points to the path of the modified schema file.
    * `-e`: It specifies extensions to enable.
    * `-x--/renderer/mdl/searchPaths/templates`: Can be ignored; it indicates where to look for MDLs.
    * `-ex`: Choose 0 for sequential ingestion (async) or 1 for more stable ingestion on separate threads.
    * `-t`: Sets a timeout for ingestion (default is 600 seconds).

***
<sub> Need to leave feedback about the RTX Remix Documentation?  [Click here](https://github.com/NVIDIAGameWorks/rtx-remix/issues/new?assignees=nvdamien&labels=documentation%2Cfeedback%2Ctriage&projects=&template=documentation_feedback.yml&title=%5BDocumentation+feedback%5D%3A+) </sub>
