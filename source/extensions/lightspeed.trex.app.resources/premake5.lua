local ext = get_current_extension_info()

project_ext (ext)

repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
    { "${target_deps}/ai_tools", ext.target_dir.."/deps/ai_tools" },
    { "${target_deps}/content", ext.target_dir.."/deps/content" },
    { "${target_deps}/omni_core_materials", ext.target_dir.."/deps/omni_core_materials" },
    { "${target_deps}/remix_runtime", ext.target_dir.."/deps/remix_runtime" },
    { "${target_deps}/tools", ext.target_dir.."/deps/tools" },
}
