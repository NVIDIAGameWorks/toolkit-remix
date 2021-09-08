local ext = get_current_extension_info()

project_ext (ext, {define_test = false })

-- C++ Carbonite plugin
project_ext_plugin(ext, "example.battle_simulator.plugin")
    local plugin_name = "example.battle_simulator"

    add_files("impl", "plugins/"..plugin_name)
    add_files("iface", "%{root}/include/omni/ext", "IExt.h")
    includedirs { "plugins/"..plugin_name }
    
-- Python Bindings for Carobnite Plugin
project_ext_bindings {
    ext = ext,
    project_name = "example.battle_simulator.python",
    module = "_example_battle_simulator",
    src = "bindings/python/example.battle_simulator",
    target_subdir = "example/battle_simulator"
}
    repo_build.prebuild_link {
        { "python/impl", ext.target_dir.."/example/battle_simulator/impl" },
        { "python/tests", ext.target_dir.."/example/battle_simulator/tests" },
    }

-- Include pip packages installed at build time
repo_build.prebuild_link {
    { "%{root}/_build/target-deps/pip_prebundle", ext.target_dir.."/pip_prebundle" },
}
    
define_ext_test_experience("example.mixed_ext", { python_module= "example.battle_simulator" }) -- Notice that python module name is different from extension name.