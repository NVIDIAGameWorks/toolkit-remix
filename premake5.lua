newoption {
    trigger     = "platform-host",
    description = "(Optional) Specify host platform for cross-compilation"
}

-- remove /JMC parameter for visual studio
require('vstudio')
premake.override(premake.vstudio.vc2010.elements, "clCompile", function(oldfn, cfg)
    local calls = oldfn(cfg)
    table.insert(calls, function(cfg)
        premake.vstudio.vc2010.element("SupportJustMyCode", nil, "false")
    end)
    return calls
end)

-- Support for /sourcelink for visual studio
require('sourcelink')

function split(instr, sep)
    local substrings = {}; i = 1
    for str in string.gmatch(instr, "([^"..sep.."]+)") do
        substrings[i] = str
        i = i + 1
    end
    return substrings
end


-- local currentAbsPath = get_abs_path(".");

-- premake5.lua
workspace "kit-examples"
    configurations { "debug", "release" }
    startproject ""

    local targetName = _ACTION
    local workspaceDir = "_compiler/"..targetName

    -- common dir name to store platform specific files
    local platform = "%{cfg.system}-%{cfg.platform}"

    local targetDependencyPlatform = "%{cfg.system}-%{cfg.platform}";
    local hostDependencyPlatform = _OPTIONS["platform-host"] or targetDependencyPlatform;

    local targetDir = "_build/"..platform.."/%{cfg.buildcfg}"

    local hostDepsDir = "_build/host-deps"
    local targetDepsDir = "_build/target-deps"
    local kitSdkDir = targetDepsDir.."/kit_sdk"
    local kitSdkTargetDepsDir = kitSdkDir.."/"..targetDepsDir
    
    local carbSDKPath = kitSdkTargetDepsDir.."/carb_sdk_plugins"
    local carbSDKInclude = carbSDKPath.."/include"
    local carbSDKLibs = carbSDKPath.."/"..targetDir
    

    -- defining anything related to the VS or SDK version here because they will most likely be changed in the future..
    local msvcInclude = hostDepsDir.."/msvc/VC/Tools/MSVC/14.16.27023/include"
    local msvcLibs = hostDepsDir.."/msvc/VC/Tools/MSVC/14.16.27023/lib/onecore/x64"
    local sdkInclude = { hostDepsDir.."/winsdk/include/winrt", hostDepsDir.."/winsdk/include/um", hostDepsDir.."/winsdk/include/ucrt", hostDepsDir.."/winsdk/include/shared" }
    local sdkLibs = { hostDepsDir.."/winsdk/lib/ucrt/x64", hostDepsDir.."/winsdk/lib/um/x64" }

    location (workspaceDir)
    targetdir (targetDir)
    -- symbolspath ("_build/"..targetName.."/symbols/%{cfg_buildcfg}/%{prj.name}.pdb")
    objdir ("_build/tmp/%{cfg.system}/%{prj.name}")
    symbols "On"
    exceptionhandling "Off"
    rtti "Off"
    staticruntime "On"
    flags { "FatalCompileWarnings", "MultiProcessorCompile", "NoPCH", "UndefinedIdentifiers", "NoIncrementalLink" }
    cppdialect "C++14"

    includedirs { targetDepsDir, hostDepsDir, "include", 
        kitSdkDir.."/include",
        kitSdkDir.."/_build/target-deps/carb_sdk_plugins/include",
        kitSdkDir.."/_build/target-deps/",
    }

    --define_buildinfo()

    filter { "system:windows" }
        platforms { "x86_64" }
        -- add .editorconfig to all projects so that VS 2017 automatically picks it up
        files {".editorconfig"}
        editandcontinue "Off"
        bindirs { hostDepsDir.."/msvc/VC/Tools/MSVC/14.16.27023/bin/HostX64/x64", hostDepsDir.."/msvc/MSBuild/15.0/bin", hostDepsDir.."/winsdk/bin/x64" }
        systemversion "10.0.17763.0"
        -- this is for the include and libs from the SDK.
        syslibdirs { msvcLibs, sdkLibs }
        sysincludedirs { msvcInclude, sdkInclude }
        -- all of our source strings and executable strings are utf8
        buildoptions {"/utf-8", "/bigobj"}
        buildoptions {"/permissive-"}

    filter { "system:linux" }
        platforms { "x86_64", "aarch64" }
        defaultplatform "x86_64"
        buildoptions { "-fvisibility=hidden -D_FILE_OFFSET_BITS=64" }
        -- add library origin directory to dlopen() search path
        linkoptions { "-Wl,-rpath,'$$ORIGIN' -Wl,--export-dynamic" }
        enablewarnings { "all" }
        disablewarnings {
            "undef",
            "unused-function", -- FrameworkImpl.cpp: makeNormalizedPath, stringToLevel
            "error=unused-variable" -- target-deps/gli: core/load_dds.inl
        }

    filter { "platforms:x86_64" }
        architecture "x86_64"

    filter { "configurations:debug" }
        defines { "DEBUG", "CARB_DEBUG=1" }
        optimize "Off"

    filter  { "configurations:release", "system:windows" }
        defines { "NDEBUG" }
        optimize "Speed"

    -- Linux/GCC has some issues on thread exit when the "Speed" optimizations are enabled.
    -- We'll leave those off on Linux for the moment.
    filter { "configurations:release", "system:linux" }
        defines { "NDEBUG" }
        optimize "On"

    filter {}

    -- common plugins settings (this function is called in every plugin project
    function define_plugin(args)
        kind "SharedLib"
        dependson { "carb" }
        location (workspaceDir.."/%{prj.name}")
        if type(args.ifaces) == "string" and type(args.impl) == "string" then
            filesTable = {}
            vpathsTable = {}

            -- split up the project filters using the named subdirectories.
            if type(args.subImpl) == "string" then
                -- add all files directly in the 'impl' directory to the top level filter.
                table.insert(filesTable, args.impl.."/*.*")
                vpathsTable["impl"] = args.impl.."/*.*"

                -- go through each named subdirectory and add all of its direct files to the
                -- project filter of the same name.
                impls_str = args.subImpl..";"
                impls = split(impls_str, ";")

                for idx, subDir in ipairs(impls) do
                    table.insert(filesTable, args.impl.."/"..subDir.."/*.*")
                    vpathsTable["impl/"..subDir] = args.impl.."/"..subDir.."/*.*"
                end

            -- recursively include all files in the 'impl' directory in one flat project filter.
            else
                table.insert(filesTable, args.impl.."/**.*")
                vpathsTable["impl"] = args.impl.."/**.*"
            end

            ifaces_str = args.ifaces .. ";"
            ifaces = split(ifaces_str, ";")
            for idx, ifacePath in ipairs(ifaces) do
                interfaceHeader = string.find(ifacePath, "%.h$")
                if interfaceHeader == nil then
                    -- Interface folder specified
                    table.insert(filesTable, ifacePath.."/*.h")
                    lastSlash = string.find(ifacePath, "/[^/]*$")
                    if lastSlash == nil then
                        vpathsTable[ifacePath] = ifacePath.."/*.h"
                    else
                        vpathsTable[string.sub(ifacePath, lastSlash + 1)] = ifacePath.."/*.h"
                    end
                else
                    -- Interface header specified
                    table.insert(filesTable, ifacePath)
                    lastSlash = string.find(ifacePath, "/[^/]*$")
                    ifacePathOnly = string.sub(ifacePath, 0, lastSlash - 1)
                    lastSlash = string.find(ifacePathOnly, "/[^/]*$")
                    if lastSlash == nil then
                        vpathsTable[ifacePath] = ifacePath
                    else
                        currentIfacePath = string.sub(ifacePathOnly, lastSlash + 1)
                        vpathsTable[currentIfacePath] = vpathsTable[currentIfacePath] or {}
                        table.insert(vpathsTable[currentIfacePath], ifacePath)
                    end
                end
            end

            files { filesTable }
            vpaths { vpathsTable }
        end
        filter {}
    end

    function define_bindings_python(args)
        local name = args.name
        local namespace = "carb"
        if type(args.namespace) == "string" then
            namespace = args.namespace
        end
        local folder = "source/bindings/python/"..namespace.."."..name
        if type(args.folder) == "string" then
            folder = args.folder
        end
        kind "SharedLib"
        targetname(name)
        targetdir (targetDir.."/bindings-python/"..namespace)
        files { folder.."/*.*", "source/bindings/python/*.*" }
        vpaths { [''] = folder.."/*.*", ['common'] = "source/bindings/python/*.*" }
        dependson { "carb" }
        links {"carb" }
        libdirs { carbSDKLibs }
        location (workspaceDir.."/%{prj.name}")
        exceptionhandling "On"
        rtti "On"
        -- Python bindings use dynamic runtime because of pybind internal design. It is important to use the same runtime
        -- for all bindings. We use release/debug runtime depending on configuration, which is default behavior.
        -- carb.scrpting-python.plugin should do the same.
        staticruntime "Off"
        filter { "configurations:debug" }
            runtime "Debug"
        filter { "system:windows" }
            targetextension(".pyd")
            libdirs { kitSdkTargetDepsDir.."/python/libs" }
            includedirs { kitSdkTargetDepsDir.."/python/include" }
        filter { "system:linux" }
            targetprefix("")
            includedirs { kitSdkTargetDepsDir.."/python/include/python3.6m" }
            links { kitSdkTargetDepsDir.."/python/lib/python3.6m" }
            -- show undefined symbols as linker errors
            linkoptions { "-Wl,--no-undefined" }
        filter {}
    end

group "experiences"
    project "examples.only"
        kind "MakeFile"
        debugcommand ("_build/target-deps/kit_sdk/_build/"..platform.."/%{cfg.buildcfg}/omniverse-kit.exe" )

group "example.python_extension"
    project "example.python_extension"
        kind "None"
        files { "source/extensions/example.python_extension/**.py" }

group "example.cpp_extension"
    project "example.cpp_extension.plugin"
            define_plugin { ifaces = "", impl = "source/extensions/example.cpp_extension/plugins" }
            targetdir (targetDir.."/extensions/omni/example/cpp_extension/bin/"..platform.."/%{cfg.buildcfg}")
            location (workspaceDir.."/%{prj.name}")

group "example.mixed_extension"
    project "example.mixed_extension.plugin"
            define_plugin { ifaces = "include/omni/example", impl = "source/extensions/example.mixed_extension/plugins" }
            targetdir (targetDir.."/extensions/omni/example/mixed_extension/bin/"..platform.."/%{cfg.buildcfg}")
            location (workspaceDir.."/%{prj.name}")

    project "example.mixed_extension.python"
            define_bindings_python {
                name = "_mixed_extension",
                folder = "source/extensions/example.mixed_extension/bindings",
                namespace = "omni" }
            targetdir (targetDir.."/extensions/omni/example/mixed_extension/bindings")
        
