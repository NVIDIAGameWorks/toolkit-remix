-- Add new option to enable passing host platform for cross-compilation
newoption {
    trigger     = "platform-host",
    description = "(Optional) Specify host platform for cross-compilation"
}

-- Shared build scripts from repo_build package
repo_build = require("omni/repo/build")

-- Enable /sourcelink flag for VS
repo_build.enable_vstudio_sourcelink()

-- Remove /JMC parameter for visual studio
repo_build.remove_vstudio_jmc()

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

-- Repo root
root = repo_build.get_abs_path(".")

-- Folder to store solution in. _ACTION is compilation target, e.g.: vs2017, make etc.
workspace_dir = "%{root}/_compiler/".._ACTION

-- Target platform name, e.g. windows-x86_64
platform = "%{cfg.system}-%{cfg.platform}"

-- Target config, e.g. debug, release
config = "%{cfg.buildcfg}"

-- Constant with all configurations we build
ALL_CONFIGS = { "debug", "release" }

-- Target directory
target_dir = "%{root}/_build/%{platform}/%{config}"

-- Path to kit sdk
kit_sdk = "%{root}/_build/target-deps/kit_sdk_%{config}"

-- Common plugins settings
function define_plugin()
    kind "SharedLib"
    location (workspace_dir.."/%{prj.name}")
    filter {}
end


-- Common python bindings settings
function define_bindings_python(name)
    local python_folder = "%{kit_sdk}/_build/target-deps/python"

    -- Carbonite carb lib
    libdirs { "%{root}/_build/target-deps/carb_sdk_plugins/_build/%{platform}/%{config}" }
    links {"carb" }

    -- pybind11 defines macros like PYBIND11_HAS_OPTIONAL for C++17, which are undefined otherwise, ignore warning:
    removeflags { "UndefinedIdentifiers" }

    location (workspace_dir.."/%{prj.name}")

    repo_build.define_bindings_python(name, python_folder)
end

-- Write experience running .bat/.sh file, like _build\windows-x86_64\release\example.helloext.app.bat
function create_experience_runner(name, config_path, config, extra_args)
    if os.target() == "windows" then
        local bat_file_path = root.."/_build/windows-x86_64/"..config.."/"..name..".bat"
        f = io.open(bat_file_path, 'w')
        f:write(string.format([[
@echo off
setlocal
call "%%~dp0..\..\target-deps\kit_sdk_%s\_build\windows-x86_64\%s\omniverse-kit.exe" --config-path %%~dp0%s %s %%*
        ]], config, config, config_path, extra_args))
    else
        local sh_file_path = root.."/_build/linux-x86_64/"..config.."/"..name..".sh"
        f = io.open(sh_file_path, 'w')
        f:write(string.format([[
#!/bin/bash
set -e
SCRIPT_DIR=$(dirname ${BASH_SOURCE})
"$SCRIPT_DIR/../../target-deps/kit_sdk_%s/_build/linux-x86_64/%s/omniverse-kit" --config-path "$SCRIPT_DIR/%s" %s $@
        ]], config, config, config_path, extra_args))
        f:close()
        os.chmod(sh_file_path, 755)
    end
end


-- Define Kit experience. Different ways to run kit with particular config
function define_experience(name)
    local config_path = "/apps/"..name..".json"
    local extra_args = "--vulkan"

    -- Create a VS project on windows to make debugging and running from VS easier:
    if os.target() == "windows" then
        group "apps"
        project(name)
            kind "Utility"
            location ("%{root}/_compiler/".._ACTION.."/%{prj.name}")
            debugcommand ("%{kit_sdk}/_build/%{platform}/%{config}/omniverse-kit.exe")
            local config_abs_path = target_dir..config_path
            debugargs ("--config-path \""..config_abs_path.."\" "..extra_args)
            files { config_abs_path }
            vpaths { [""] = "**.json" }
    end

    -- Write bat and sh files as another way to run them:
    for _, config in ipairs(ALL_CONFIGS) do
        create_experience_runner(name, config_path, config, extra_args)
    end
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
        "_build/target-deps/carb_sdk_plugins/include",
        "%{kit_sdk}/include",
        "%{kit_sdk}/_build/target-deps/",
    }
    
    -- Location for intermediate  files
    objdir ("_build/intermediate/%{platform}/%{prj.name}")

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
    -- Application example. Only runs Kit with a config, doesn't build anything. Helper for debugging.
    define_experience("example.app")
    define_experience("example.app-mini")

-- Example of C++ only extension:
include ("source/extensions/example.cpp_extension")

-- Example of Python only extension:
include ("source/extensions/example.python_extension")

-- Example of Mixed (both python and C++) extension:
include ("source/extensions/example.mixed_extension")


