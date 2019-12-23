-- Add new option to enable passing host platform for cross-compilation
newoption {
    trigger     = "platform-host",
    description = "(Optional) Specify host platform for cross-compilation"
}

-- Shared build scripts from repo_build package
local repo_build = require("omni/repo/build")

-- Enable /sourcelink flag for VS
repo_build.enable_vstudio_sourcelink()

-- Remove /JMC parameter for visual studio
repo_build.remove_vstudio_jmc()

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

-- Add folder with source files to solution under impl/ virtual group (helper)
function add_impl_folder(path)
    files { path.."/**" }
    vpaths {
        ["impl/*"] = path.."/*"
    }
end

-- Add folder with interface headers to solution under iface/ virtual group (helper)
function add_iface_folder(path)
    files { path.."/**" }
    vpaths {
        ["iface/*"] = path.."/*"
    }
end

-- Folder to store solution in. _ACTION is compilation target, e.g.: vs2017, make etc.
local workspace_dir = "_compiler/".._ACTION

-- Target platform name, e.g. windows-x86_64
local platform = "%{cfg.system}-%{cfg.platform}"

-- Target directory
local target_dir = "_build/"..platform.."/%{cfg.buildcfg}"

-- Common plugins settings
function define_plugin()
    kind "SharedLib"
    location (workspace_dir.."/%{prj.name}")
    filter {}
end


-- Common python bindings settings
function define_bindings_python(name)
    local kit_sdk_target_deps = "_build/target-deps/kit_sdk/_build/target-deps"
    local python_folder = kit_sdk_target_deps.."/python"

    -- Carbonite carb lib
    libdirs { kit_sdk_target_deps.."/carb_sdk_plugins/"..target_dir }
    links {"carb" }

    location (workspace_dir.."/%{prj.name}")

    repo_build.define_bindings_python(name, python_folder)
end


-- Starting from here we define a structure of actual solution to be generated. Starting with solution name.
workspace "kit-examples"
    configurations { "debug", "release" }

    -- Project selected by default to run
    startproject ""

    -- Set location for solution file
    location (workspace_dir)

    -- Set default target dir, later projects overwrite it
    targetdir (target_dir)

    -- Setup include paths. Add kit SDK include paths too.
    includedirs { 
            "include", 
            "_build/target-deps", 
            "_build/target-deps/kit_sdk/include",
            "_build/target-deps/kit_sdk/_build/target-deps/carb_sdk_plugins/include",
            "_build/target-deps/kit_sdk/_build/target-deps/",
    }
    
    -- Location for intermediate  files
    objdir ("_build/intermediate/"..platform.."/%{prj.name}")

    -- Default compilation settings
    symbols "On"
    exceptionhandling "Off"
    rtti "Off"
    staticruntime "On"
    flags { "FatalCompileWarnings", "MultiProcessorCompile", "NoPCH", "UndefinedIdentifiers", "NoIncrementalLink" }
    cppdialect "C++14"

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


group "apps"
    project "examples.only"
        kind "MakeFile"
        debugcommand ("_build/target-deps/kit_sdk/_build/"..platform.."/%{cfg.buildcfg}/omniverse-kit.exe" )

group "example.python_extension"
    project "example.python_extension"
        kind "None"
        add_impl_folder("source/extensions/example.python_extension")

group "example.cpp_extension"
    project "example.cpp_extension.plugin"
        define_plugin()
        add_impl_folder ("source/extensions/example.cpp_extension/plugins")
        targetdir (target_dir.."/extensions/omni/example/cpp_extension/bin/"..platform.."/%{cfg.buildcfg}")
        location (workspace_dir.."/%{prj.name}")

group "example.mixed_extension"
    project "example.mixed_extension"
        kind "None"
        add_impl_folder("source/extensions/example.mixed_extension/python")

    project "example.battle_simulator.plugin"
        define_plugin()
        add_impl_folder("source/extensions/example.mixed_extension/plugins")
        add_iface_folder("include/omni/example")
        targetdir (target_dir.."/extensions/omni/example/mixed_extension/bin/"..platform.."/%{cfg.buildcfg}")
        location (workspace_dir.."/%{prj.name}")

    project "example.battle_simulator.python"
        define_bindings_python("_battle_simulator")
        add_impl_folder("source/extensions/example.mixed_extension/bindings")
        targetdir (target_dir.."/extensions/omni/example/mixed_extension/bindings")
        
