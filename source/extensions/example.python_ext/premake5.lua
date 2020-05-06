-- Use folder name to build extension name and tag. Version is specified explicitly.
local EXT_VERSION = "0.1.0"
local ext = get_current_extension_info(EXT_VERSION)

-- That will also link whole current "target" folder into as extension target folder:
project_ext (ext)
