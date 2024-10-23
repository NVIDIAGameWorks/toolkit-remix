local ext = get_current_extension_info()

project_ext (ext)
repo_build.prebuild_link {
    { "docs", ext.target_dir.."/docs" },
    { "data", ext.target_dir.."/data" },
    { "lightspeed", ext.target_dir.."/lightspeed" },
}
