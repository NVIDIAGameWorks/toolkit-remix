-- Add new option to enable passing host platform for cross-compilation
newoption {
    trigger     = "platform-host",
    description = "(Optional) Specify host platform for cross-compilation"
}

-- Shared build scripts from repo_build package
repo_build = require("omni/repo/build")

-- Repo root
root = repo_build.get_abs_path(".")

-- Include Kit SDK public premake, it defines few global variables and helper functions. Look inside to get more info.
local _ = dofileopt("_build/kit/release/dev/premake5-public.lua") or dofileopt("_build/kit/debug/dev/premake5-public.lua")

-- Setup where to write generate prebuild.toml file
repo_build.set_prebuild_file('_build/generated/prebuild.toml')

--
function write_version_file(config)
    local cmd
    if os.target() == "windows" then
        local dir = root.."/_build/windows-x86_64/"..config
        cmd = "repo.bat build_number -o "..dir.."/VERSION"
    else
        local dir = root.."/_build/linux-x86_64/"..config
        cmd = "./repo.sh build_number -o "..dir.."/VERSION"
    end
    os.execute(get_current_lua_file_dir().."/"..cmd)
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


-- Include all extensions in premake (each has own premake5.lua file)
for _, ext in ipairs(os.matchdirs("source/extensions/*")) do
    include (ext)
end

group "apps"
    -- Direct shortcur to kit executable for convenience:
    for _, config in ipairs(ALL_CONFIGS) do
        create_experience_runner("kit", "", config, config, "")

        -- Put build version file into build directories
        write_version_file(config)
    end

    -- Application example. Only runs Kit with a config, doesn't build anything. Helper for debugging.
    define_app("omni.app.new_exts_demo.kit")
    define_app("omni.app.new_exts_demo_mini.kit")

    define_ext_test_experience("example.python_ext")
    

