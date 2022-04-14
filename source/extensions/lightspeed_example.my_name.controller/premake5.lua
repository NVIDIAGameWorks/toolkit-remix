local ext = get_current_extension_info()

project_ext (ext)

repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    {"lightspeed_example/", ext.target_dir.."/lightspeed_example"},
}
