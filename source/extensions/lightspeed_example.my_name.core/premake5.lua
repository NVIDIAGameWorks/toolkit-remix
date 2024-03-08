-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

-- Link the current "target" folders into the extension target folder:
project_ext (ext)
repo_build.prebuild_link {
    {"lightspeed_example/", ext.target_dir.."/lightspeed_example"},
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
}

