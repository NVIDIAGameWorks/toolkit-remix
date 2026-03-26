-- Setup the extension
local ext = get_current_extension_info()

project_ext(ext)

-- Link necessary libraries
repo_build.prebuild_link {
    { "omni/flux/fcurve/widget", ext.target_dir.."/omni/flux/fcurve/widget" },
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
}
