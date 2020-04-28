local ext_name = "example.mixed_extension"
local ext_version = ""
local ext_id = ext_name
local ext_folder = "%{root}/_build/$platform/$config/exts/"..ext_id
local ext_bin_folder = ext_folder.."/bin/$platform/$config"

group ("extensions/"..ext_id)

    -- Python code. Contains python sources, doesn't build or run, only for MSVS.
    if os.target() == "windows" then
        project "example.mixed_extension"
            kind "None"
            add_impl_folder("source/extensions/example.mixed_extension/python")
    end

    repo_build.prebuild_link {
        { "config", ext_folder.."/config" },
    }

    repo_build.prebuild_link {
        { "python/scripts", ext_folder.."/example/mixed_extension/scripts" },
    }

    repo_build.prebuild_copy {
        { "python/*.py", ext_folder.."/example/mixed_extension" },
    }

    -- C++ Carbonite plugin
    project "example.battle_simulator.plugin"
        define_plugin()
        add_impl_folder("plugins")
        add_iface_folder("%{root}/include/omni/example")
        targetdir (bin_dir.."/exts/"..ext_id.."/bin/%{platform}/%{cfg.buildcfg}")

    -- Python Bindings for Carobnite Plugin
    project "example.battle_simulator.python"
        define_bindings_python("_battle_simulator")
        add_impl_folder("bindings")
        targetdir (bin_dir.."/exts/"..ext_id.."/example/mixed_extension")
