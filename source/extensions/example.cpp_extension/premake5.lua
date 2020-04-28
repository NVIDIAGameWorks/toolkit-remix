local ext_name = "example.cpp_extension"
local ext_version = ""
local ext_id = ext_name
local ext_source = "source/extensions/"..ext_name
local ext_folder = "%{root}/_build/$platform/$config/exts/"..ext_id
local ext_bin_folder = ext_folder.."/bin/$platform/$config"

group ("extensions/"..ext_id)

    -- C++ Carbonite plugin
    project "example.cpp_extension.plugin"
        define_plugin()
        add_impl_folder ("plugins")
        targetdir (bin_dir.."/exts/"..ext_id.."/bin/%{platform}/%{cfg.buildcfg}")

    repo_build.prebuild_link {
        { "config", ext_folder.."/config" },
    }


