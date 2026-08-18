# Overview

Widgets for selecting files and configuring imports handled by `omni.flux.asset_importer.core`.

## Widget Collection

- `file_import_list`: A list view with add/remove buttons to manage the list of files to import.
- `texture_import_list`: A list view for texture paths and their semantic texture types.
- `scan_folder`: The directory-selection dialog and result model. File discovery and selection validation remain in
  `omni.flux.asset_importer.core`; this extension owns only the user interface and failure dialogs.

Supported file extensions are matched case-insensitively, including USD formats.
