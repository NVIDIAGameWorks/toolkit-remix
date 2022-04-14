local ext = get_current_extension_info()

project_ext (ext)

repo_build.prebuild_link {
    {"lightspeed_example/", ext.target_dir.."/lightspeed_example"},
    { "docs", ext.target_dir.."/docs" },
    { "data", ext.target_dir.."/data" }
}
