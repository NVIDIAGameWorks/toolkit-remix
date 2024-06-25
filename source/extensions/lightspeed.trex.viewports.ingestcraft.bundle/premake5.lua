-- Use folder name to build extension name and tag. 
local ext = get_current_extension_info()

-- Link the current "target" folders into the extension target folder:
project_ext (ext)
    repo_build.prebuild_link { "data", ext.target_dir.."/data" }
    repo_build.prebuild_link { "docs", ext.target_dir.."/docs" }
