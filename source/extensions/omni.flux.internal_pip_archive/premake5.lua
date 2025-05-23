local ext = get_current_extension_info()

project_ext (ext)
    repo_build.prebuild_link {
        { "docs", ext.target_dir.."/docs" },
        { "data", ext.target_dir.."/data" },
        { "omni", ext.target_dir.."/omni" },
        { "${target_deps}/internal_pip_prebundle", ext.target_dir.."/pip_prebundle" },
}
