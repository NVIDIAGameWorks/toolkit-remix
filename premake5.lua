-- Add new option to enable passing host platform for cross-compilation
newoption {
    trigger     = "platform-host",
    description = "(Optional) Specify host platform for cross-compilation"
}

-- Shared build scripts from repo_build package
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Resolved path to kit SDK (without %{} tokens), for creating experiences
KIT_SDK_RESOLVED = {
    ["debug"] = root.."/_build/target-deps/kit_sdk_debug",
    ["release"] = root.."/_build/target-deps/kit_sdk_release",
}

-- Path to kit sdk
kit_sdk = "%{root}/_build/target-deps/kit_sdk_%{config}"

kit_sdk_bin_dir = "%{kit_sdk}/_build/%{platform}/%{config}"

-- Include Kit SDK public premake, it defines few global variables and helper functions. Look inside to get more info.
include("_build/target-deps/kit_sdk_release/premake5-public.lua")

-- Setup where to write generate prebuild.toml file
repo_build.set_prebuild_file('_build/generated/prebuild.toml')

-- Setup all msvc and winsdk paths. That later can be moved to actual msvc and sdk packages 
function setup_msvc_toolchain()
        systemversion "10.0.17763.0"

        local host_deps = "_build/host-deps"

        -- system include dirs:
        local msvcInclude = host_deps.."/msvc/VC/Tools/MSVC/14.16.27023/include"
        local sdkInclude = { 
            host_deps.."/winsdk/include/winrt", 
            host_deps.."/winsdk/include/um", 
            host_deps.."/winsdk/include/ucrt", 
            host_deps.."/winsdk/include/shared" 
        }
        sysincludedirs { msvcInclude, sdkInclude }

        -- system lib dirs:
        local msvcLibs = host_deps.."/msvc/VC/Tools/MSVC/14.16.27023/lib/onecore/x64"
        local sdkLibs = { host_deps.."/winsdk/lib/ucrt/x64", host_deps.."/winsdk/lib/um/x64" }
        syslibdirs { msvcLibs, sdkLibs }

        -- system binary dirs:
        bindirs { 
            host_deps.."/msvc/VC/Tools/MSVC/14.16.27023/bin/HostX64/x64", 
            host_deps.."/msvc/MSBuild/15.0/bin", host_deps.."/winsdk/bin/x64" 
        }
end

-- Starting from here we define a structure of actual solution to be generated. Starting with solution name.
workspace "kit-examples"
    configurations { "debug", "release" }

    -- Project selected by default to run
    startproject ""

    -- Set location for solution file
    location (workspace_dir)

    -- Set default target dir, later projects overwrite it
    targetdir (bin_dir)

    -- Setup include paths. Add kit SDK include paths too.
    includedirs { 
        "include", 
        "_build/target-deps", 
        "_build/target-deps/carb_sdk_plugins/include",
        "%{kit_sdk}/include",
        "%{kit_sdk}/_build/target-deps/",
    }
    
    -- Carbonite carb lib
    libdirs { "%{root}/_build/target-deps/carb_sdk_plugins/_build/%{platform}/%{config}" }

    -- Location for intermediate  files
    objdir ("_build/intermediate/%{platform}/%{prj.name}")

    -- Default compilation settings
    symbols "On"
    exceptionhandling "Off"
    rtti "Off"
    staticruntime "On"
    flags { "FatalCompileWarnings", "MultiProcessorCompile", "NoPCH", "UndefinedIdentifiers", "NoIncrementalLink" }
    cppdialect "C++14"

    -- Generic folder linking and file copy setup:
    repo_build.prebuild_link {
        -- Link app configs in target dir for easier edit
        { "source/apps", bin_dir.."/apps" },
    
        -- Link python app sources in target dir for easier edit
        { "source/pythonapps/target", bin_dir.."/pythonapps" },
    }
    repo_build.prebuild_copy {
        -- Copy python app running scripts in target dir
        {"source/pythonapps/runscripts/$config/*$shell_ext", bin_dir},
    }

    -- Windows platform settings
    filter { "system:windows" }
        platforms { "x86_64" }

        -- Add .editorconfig to all projects so that VS 2017 automatically picks it up
        files {".editorconfig"}
        editandcontinue "Off"

        -- Enable usage of brought up toolchain
        setup_msvc_toolchain()

        -- All of our source strings and executable strings are utf8
        buildoptions {"/utf-8", "/bigobj"}
        buildoptions {"/permissive-"}


    -- Linux platform settings
    filter { "system:linux" }
        platforms { "x86_64", "aarch64" }
        defaultplatform "x86_64"

        buildoptions { "-fvisibility=hidden -D_FILE_OFFSET_BITS=64" }

        -- Add library origin directory to dlopen() search path
        linkoptions { "-Wl,-rpath,'$$ORIGIN' -Wl,--export-dynamic" }
        
        enablewarnings { "all" }

    filter { "platforms:x86_64" }
        architecture "x86_64"

    -- Debug configuration settings
    filter { "configurations:debug" }
        defines { "DEBUG" }
        optimize "Off"

    -- Release configuration settings
    filter  { "configurations:release" }
        defines { "NDEBUG" }
        optimize "Speed"

    filter {}


-- Example of C++ only extension:
include ("source/extensions/example.cpp_ext")

-- Example of Python only extension:
include ("source/extensions/example.python_ext")

-- Example of Mixed (both python and C++) extension:
include ("source/extensions/example.mixed_ext")


group "apps"
    -- Direct shortcur to kit executable for convenience:
    for _, config in ipairs(ALL_CONFIGS) do
        create_experience_runner("kit", nil, config, "")
    end

    -- Application example. Only runs Kit with a config, doesn't build anything. Helper for debugging.
    define_experience("kit-new-exts", { config_path = "apps/kit-new-exts.json" })
    define_experience("kit-new-exts-mini", { config_path = "apps/kit-new-exts-mini.json" })

    define_ext_test_experience("example.python_ext")
    define_ext_test_experience("example.mixed_ext", "example.battle_simulator") -- Notice that python module name is different from extension name.

