-- Use folder name to build extension name and tag. Version is specified explicitly.
local ext = get_current_extension_info()

project_ext (ext)
repo_build.prebuild_link {
    { "data", ext.target_dir.."/data" },
    { "docs", ext.target_dir.."/docs" },
}

-- Build Carbonite plugin to be loaded by extension. This plugin implements omni::ext::IExt interface to be automatically
-- started by extension system.
project_ext_plugin(ext, "omni.ext-example_cpp_ext.plugin")
    local plugin_name = "omni.ext-example_cpp_ext"
    add_files("iface", "%{root}/include/omni/ext", "IExt.h")
    add_files("impl", "plugins/"..plugin_name)
    includedirs { "plugins/"..plugin_name }
    