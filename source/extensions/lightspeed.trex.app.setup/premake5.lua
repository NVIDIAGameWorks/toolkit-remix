-- Use folder name to build extension name and tag.
local ext = get_current_extension_info()

project_ext (ext)

-- Link only those files and folders into the extension target directory
repo_build.prebuild_link { "lightspeed", ext.target_dir.."/lightspeed" }
repo_build.prebuild_link { "apps", ext.target_dir.."/apps" }
