// Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#define _CRT_SECURE_NO_WARNINGS

// clang-format off
#include <cstdlib>
#include <cstdio>
#define TOML_HAVE_FAILWITH_REPLACEMENT
template <typename... Args>
void failwith(Args&&...)
{
    perror("OmniConfig Toml fail.");
    std::abort();
}
#include "omni-config-cpp/include/OmniConfig.h"
// clang-format on


#include <carb/ClientUtils.h>
#include <carb/StartupUtils.h>
#include <carb/dictionary/DictionaryUtils.h>
#include <carb/dictionary/IDictionary.h>
#include <carb/extras/WindowsPath.h>
#include <carb/filesystem/FileSystem.h>
#include <carb/graphics/Graphics.h>
#include <carb/multiprocess/MultiProcess.h>
#include <carb/profiler/GpuProfile.h>
#include <carb/profiler/Profile.h>
#include <carb/settings/ISettings.h>
#include <carb/extras/EnvironmentVariable.h>
#include <carb/extras/EnvironmentVariableParser.h>

#include <omni/kit/IEditor.h>

#if 0
#include <omni/kit/Version.h>
#else

#define BUILDVERSION "123"
#endif

#include <chrono>
#include <string>
#include <vector>

#ifdef _MSC_VER
#    pragma warning(disable : 4996)
#endif

CARB_GLOBALS("omni.kit")
CARB_GPU_PROFILER_GLOBALS()

std::vector<const char*> g_commandArguments;


static std::string getDocumentsPath()
{
#if defined(_WIN32)
    std::string userFolder;
    if (carb::extras::EnvironmentVariable::getValue("USERPROFILE", userFolder))
    {
        std::replace(userFolder.begin(), userFolder.end(), '\\', '/');
        return userFolder + "/Documents";
    }
#elif defined(__linux__)
    std::string userFolder;
    if (carb::extras::EnvironmentVariable::getValue("HOME", userFolder))
    {
        return userFolder + "/Documents";
    }
#else
#    error unsupported platform
#endif

    CARB_LOG_ERROR("Unable to get Documents folder.");
    return "";
}

static void loadPluginsFromPattern(const char* pluginNamePattern)
{
    carb::Framework* f = carb::getFramework();
    carb::PluginLoadingDesc desc = carb::PluginLoadingDesc::getDefault();
    const char* plugins[] = { pluginNamePattern };
    const char* searchPaths[] = { "plugins" };
    desc.loadedFileWildcards = plugins;
    desc.loadedFileWildcardCount = CARB_COUNTOF(plugins);
    desc.searchPaths = searchPaths;
    desc.searchPathCount = CARB_COUNTOF(searchPaths);
    f->loadPlugins(desc);
}

static std::string replaceAll(std::string subject, const std::string& search, const std::string& replace)
{
    size_t pos = 0;
    while ((pos = subject.find(search, pos)) != std::string::npos)
    {
        subject.replace(pos, search.length(), replace);
        pos += replace.length();
    }
    return subject;
}

struct ConfigOverride
{
    std::string alias;
    std::string value;
};

static std::string loadConfigAndPrepocess(carb::filesystem::FileSystem* fs,
                                          std::string path,
                                          const std::vector<ConfigOverride>& overrides)
{
    std::string configString;

    carb::filesystem::File* file = fs->openFileToRead(path.c_str());
    if (file)
    {
        size_t size = fs->getFileSize(file);
        if (size)
        {
            std::vector<char> content(size + 1);
            fs->readFileChunk(file, content.data(), size);
            content[content.size() - 1] = '\0';
            fs->closeFile(file);

            configString = content.data();
        }
    }

    for (const ConfigOverride& o : overrides)
    {
        configString = replaceAll(configString, o.alias, o.value);
    }

    return configString;
}

static std::string getKitDataVersion()
{
    // Trim only year.version part of build version (e.g. "2019.2") for data folder version
    std::string buildVersion = BUILDVERSION;
    size_t firstDot = buildVersion.find('.');
    size_t secondDot = buildVersion.find('.', firstDot + 1);
    return buildVersion.substr(0, secondDot);
}

static bool isPortableVersion(carb::filesystem::FileSystem* fs)
{
    // Check if Kit installation is portable by checking existence of [executable_name].portable file:
    carb::extras::Path execPathModified(fs->getExecutablePath());
    execPathModified.replaceExtension("portable");
    return fs->exists(execPathModified.getStringBuffer());
}

static void startupFramework(carb::Framework* f,
                             char** argv,
                             int argc,
                             const std::string& dataPath,
                             const std::string& cachePath,
                             const std::string& documentsPath)
{
    // This is where we could startup the crash reporter and profiler explicitly - but since omniverse-kit hasn't been
    // loading these so far this is not a good time to activate them. What is needed is to use the copy script
    // to put the desired plugins next to omniverse-kit.exe and then load them here, using carb::loadPluginsFromPattern.

    carb::filesystem::FileSystem* fs = f->acquireInterface<carb::filesystem::FileSystem>();

    // set the initial working directory to the executable directory.
    carb::extras::Path execFolder = carb::extras::getPathParent(fs->getExecutablePath());
    fs->setCurrentDirectoryPath(execFolder.getStringBuffer());
    fs->setAppDirectoryPath(execFolder.getStringBuffer());


    // Initialize new settings system from reading json via dictionary
    const char* dictionaryPlugin = "carb.dictionary.plugin";
    loadPluginsFromPattern(dictionaryPlugin);
    const char* jsonPlugin = "carb.dictionary.serializer-json.plugin";
    loadPluginsFromPattern(jsonPlugin);

    carb::dictionary::ISerializer* serial = f->acquireInterface<carb::dictionary::ISerializer>();

    const char* settingsPlugin = "carb.settings.plugin";
    loadPluginsFromPattern(settingsPlugin);
    carb::settings::ISettings* settings = f->acquireInterface<carb::settings::ISettings>();

    // Config overrides and dirs
    std::string processDataPath = dataPath;
    std::string processCachePath = cachePath;

    loadPluginsFromPattern("carb.multiprocess.plugin");
    carb::multiprocess::MultiProcess* multiProcess = f->acquireInterface<carb::multiprocess::MultiProcess>();

    // Load MPI here because we need to know our process index
    multiProcess->startup();

    if (multiProcess->getProcessIndex() > 0)
    {
        processDataPath += "/slave" + std::to_string(multiProcess->getProcessIndex());
        processCachePath += "/slave" + std::to_string(multiProcess->getProcessIndex());
    }

    fs->makeDirectories(processDataPath.c_str());
    fs->makeDirectories(processCachePath.c_str());
    fs->makeDirectories(documentsPath.c_str());

    std::vector<ConfigOverride> overrides;
    overrides.push_back({ "@data@", processDataPath });
    overrides.push_back({ "@cache@", processCachePath });
    overrides.push_back({ "@documents@", documentsPath });

    // Parse config file if present:
    // Strictly speaking, for the "omniverse-kit" the logic could be much simpler, but this code serves as an example,
    // so better have it right
    carb::extras::Path configPath = fs->getExecutablePath();
#if CARB_PLATFORM_WINDOWS
    configPath.replaceExtension("");
#endif
    configPath = configPath + ".config.json";

    carb::dictionary::Item* dict = nullptr;

    if (serial)
    {
        std::string configContent = loadConfigAndPrepocess(fs, configPath.getStringBuffer(), overrides);
        dict = serial->createDictionaryFromStringBuffer(configContent.c_str());
    }
    else
    {
        CARB_LOG_ERROR("Unable to acquire ISerializer interface from json plugin - cannot read settings from file!");
    }

    carb::dictionary::IDictionary* id = f->acquireInterface<carb::dictionary::IDictionary>();
    if (!dict)
    {
        dict = id->createItem(nullptr, "<config>", carb::dictionary::ItemType::eDictionary);
    }

    carb::dictionary::setDictionaryFromCmdLine(id, dict, argv, argc, "--carb/");
    settings->initializeFromDictionary(dict);
    id->destroyItem(dict);

    bool overrideSettingsWithEnvVars = true;
    if (overrideSettingsWithEnvVars)
    {
        carb::extras::EnvironmentVariableParser envVarsParser("OMNI_KIT_");
        envVarsParser.parse();
        const carb::extras::EnvironmentVariableParser::Options& envVarsOptions = envVarsParser.getOptions();

        carb::dictionary::Item* dictEnvVarOptions =
            id->createItem(nullptr, "<env var options>", carb::dictionary::ItemType::eDictionary);
        carb::dictionary::setDictionaryFromStringMapping(id, dictEnvVarOptions, envVarsOptions);
        for (auto it = envVarsOptions.begin(); it != envVarsOptions.end(); ++it)
        {
            CARB_LOG_INFO("Overriding setting from env variable: \"%s\" = \"%s\"", it->first.c_str(), it->second.c_str());
        }
        settings->update("", dictEnvVarOptions, "", carb::dictionary::kUpdateItemOverwriteOriginal, nullptr);
        id->destroyItem(dictEnvVarOptions);
    }

    // Using Settings plugin to configure subsystems
    multiProcess->loadSettings();

    // Startup the crash reporter
    loadPluginsFromPattern("carb.crashreporter-*");
    carb::crashreporter::registerCrashReporterForClient();

    // Configure logging plugin and its default logger
    if (multiProcess->getProcessIndex() > 0)
    {
        // Separate log file per slave process (in case log file is not placed in data dir)
        std::string slaveLogFilePath =
            settings->getStringBuffer("/log/file") + std::string(".") + std::to_string(multiProcess->getProcessIndex());
        settings->setString("/log/file", slaveLogFilePath.c_str());
    }

    carb::logging::configureLogging(settings);
    carb::logging::configureDefaultLogger(settings);

    // Load plugins using supplied configuration
    carb::loadPluginsFromConfig(settings);

    // Configure default plugins as present in the config
    carb::setDefaultPluginsFromConfig(settings);

    // Starting up profiling
    // This way of registering profiler allows to enable/disable profiling in the config file, by
    // allowing/denying to load profiler plugin.
    carb::profiler::registerProfilerForClient();
    CARB_PROFILE_STARTUP();
}

/**
 * Parses command line arguments, before we start the editor.
 * This function must be called once before acquiring interface of any plug-in.
 *
 * @param argc          Command line arguments count to parse.
 * @param argv          Command line arguments to parse.
 * @param cmdArgument   Returns the parsed command line arguments.
 *
 * @return true if parsing was successful.
 */
static bool parseCommandLineArguments(int argc, char** argv, omni::kit::CommandLineArguments* cmdArgument)
{
    carb::Framework* framework = carb::getFramework();
#if CARB_PLATFORM_WINDOWS
    bool isVulkan = false;
#else
    bool isVulkan = true;
#endif

    if (!g_commandArguments.empty())
    {
        CARB_LOG_WARN("overwriting existing CommandLineArguments strings.");
    }
    g_commandArguments.clear();

    for (int argIdx = 1; argIdx < argc; argIdx++)
    {
        if (strcmp(argv[argIdx], "--help") == 0 || strcmp(argv[argIdx], "-h") == 0 || strcmp(argv[argIdx], "-?") == 0)
        {
            puts("omniverse-kit Usage:");
            puts(" omniverse-kit [--no-window] [--vulkan] [--rtx] [--no-audio] [--exec console_command] [--carb</json/key>=<value>]");
            puts("");
            puts("--help, -h: this help message");
            puts("--verbose, -v: show info log output in console");
            puts("--no-window: run the graphics rendering offscreen without a window (scripting only, streaming TODO)");
            puts("--vulkan: run the graphics rendering with Vulkan");
            puts("--no-audio: don't initialize the audio system on launch.");
            puts("--exec, -e: execute a console command on startup");
            puts("--carb</json/key>=<value>: instruct to supersede json configuration key with given value.");
            puts("");
            puts("Usage hints:");
            puts("\tuse --carb/log/enabled=true to enable logging.");
            puts("\tuse --carb/app/livestream/enabled=true to enable Live Streaming.");
            puts("\tuse --carb/app/window/drawMouse=true to custom draw mouse pointer.");
            puts("\tuse --carb/app/remotecamera/enabled=true to enable the Remote Camera plugin.");
            puts("");
            printf("Version: %s\n", BUILDVERSION);
            return false;
        }
        else if (strcmp(argv[argIdx], "--no-window") == 0)
        {
            cmdArgument->windowAllowed = false;
        }
        else if (strcmp(argv[argIdx], "--vulkan") == 0)
        {
            isVulkan = true;
        }
        else if (strcmp(argv[argIdx], "--no-audio") == 0)
        {
            cmdArgument->audioAllowed = false;
        }
        else if (strcmp(argv[argIdx], "--exec") == 0 || strcmp(argv[argIdx], "-e") == 0)
        {
            if (argIdx + 1 < argc)
            {
                g_commandArguments.push_back(argv[argIdx + 1]);
                ++argIdx;
            }
            else
            {
                fprintf(stderr, "%s takes a parameter\n", argv[argIdx]);
                return false;
            }
        }
        else if (strcmp(argv[argIdx], "--verbose") == 0 || strcmp(argv[argIdx], "-v") == 0)
        {
            carb::settings::ISettings* settings = framework->acquireInterface<carb::settings::ISettings>();
            settings->setString("/log/outputStreamLevel", "Info");
            settings->setString("/log/debugConsoleLevel", "Info");
            carb::logging::configureDefaultLogger(settings);
        }
    }

    // update CommandLineArguments
    cmdArgument->graphicsMode = isVulkan ? omni::kit::GraphicsMode::eVulkan : omni::kit::GraphicsMode::eDirect3D12;
    cmdArgument->rendererMode = omni::kit::RendererMode::eRtx;
    cmdArgument->commandsCount = g_commandArguments.size();
    cmdArgument->commands = g_commandArguments.data();
    cmdArgument->commands = g_commandArguments.data();

    CARB_LOG_WARN("[Graphics API] %s\n", isVulkan ? "Vulkan" : "DX12");

    if (isVulkan)
    {
        // Vulkan currently does not support working threads, due to non-thread safe mesh updates.
        carb::settings::ISettings* settings = framework->acquireInterface<carb::settings::ISettings>();
        settings->setInt("/omni.kit.plugin/usdWorkConcurrencyLimit", 1);
        CARB_LOG_WARN("Setting usdWorkConcurrencyLimit to 1 for Vulkan.");
    }

    // Set the default graphics API
    const carb::InterfaceDesc graphicsDesc = carb::graphics::Graphics::getInterfaceDesc();
    const char* graphicsPluginName = isVulkan ? "carb.graphics-vulkan.plugin" : "carb.graphics-direct3d.plugin";

    framework->setDefaultPluginEx(g_carbClientName, graphicsDesc, graphicsPluginName);

    // Must acquire it here to lock our default plugin choice
    carb::graphics::Graphics* graphicsDefault = framework->acquireInterface<carb::graphics::Graphics>();
    carb::PluginDesc pluginDesc = framework->getInterfacePluginDesc(graphicsDefault);
    if (strcmp(pluginDesc.impl.name, graphicsPluginName) != 0)
    {
        // At this point, no one should have acquired graphics plugins.
        // defaultPlugins should also not be set from config.
        CARB_LOG_ERROR("Start up failed. The default graphics plugin cannot be set!");
        return false;
    }

    // register GPU profiler. We start it later at run-time if profiling is requested.
    // Note: this cannot be done in startupFramework(), no graphics dependency must be loaded prior to above steps.
    carb::profiler::registerGpuProfilerForClient();

    return true;
}


//
// Main entry point.
//
int main(int argc, char** argv)
{

    // Disable UsdImaging camera support until it plays nicely with Camera Gizmos.
#if CARB_PLATFORM_WINDOWS
    putenv("USDIMAGING_DISABLE_CAMERA_ADAPTER=1");
#else
    setenv("USDIMAGING_DISABLE_CAMERA_ADAPTER", "1", 1);
#endif

    // Loads carb.dll/.so and registers logging and filesystem from carb library
    carb::acquireFrameworkAndRegisterBuiltins();

    carb::Framework* framework = carb::getFramework();
    if (!framework)
        return EXIT_FAILURE;

#if CARB_PLATFORM_WINDOWS
    carb::extras::adjustWindowsDllSearchPaths();
#endif

    carb::filesystem::FileSystem* fs = framework->acquireInterface<carb::filesystem::FileSystem>();

    // Build Kit data and cache folder path. Use Omniverse Path Config (Omniverse File Location RFC) for installed
    // version. Portable version creates those folders near executable.
    std::string dataPath;
    std::string cachePath;
    if (isPortableVersion(fs))
    {
        const std::string exeDirPath = fs->getExecutableDirectoryPath();
        dataPath = exeDirPath + "/data";
        cachePath = exeDirPath + "/cache";
    }
    else
    {
        omniverse::GlobalConfig config;

        dataPath = config.getBaseDataPath();
        std::replace(dataPath.begin(), dataPath.end(), '\\', '/');

        cachePath = config.getBaseCachePath();
        std::replace(cachePath.begin(), cachePath.end(), '\\', '/');
    }

    // Documents folder is used for both portable and installed version
    std::string documentsPath = getDocumentsPath();
    if (documentsPath.empty())
        return EXIT_FAILURE;

    std::string kitPath = std::string("Kit/") + getKitDataVersion();
    std::string kitDataPath = dataPath + "/" + kitPath;
    std::string kitCachePath = cachePath + "/" + kitPath;
    std::string kitDocumentsPath = documentsPath + "/Kit";

    // Load all the plugins
    startupFramework(framework, argv, argc, kitDataPath, kitCachePath, kitDocumentsPath);

    // Parse command line arguments after loading all the settings, and prior to loading any other plug-in like Imgui
    omni::kit::CommandLineArguments cmdArguments = {};
    cmdArguments.windowAllowed = true; // By default, allow local window display
    cmdArguments.audioAllowed = true; // By default, allow audio initialization.
    if (!parseCommandLineArguments(argc, argv, &cmdArguments))
    {
        CARB_LOG_ERROR("Failed to parse command line arguments.");
        return EXIT_FAILURE;
    }

    omni::kit::IEditor* editor = framework->acquireInterface<omni::kit::IEditor>();
    int startupCode = editor->startup(&cmdArguments);
    if (startupCode)
    {
        CARB_LOG_ERROR("Omniverse Kit startup failed, with code %d", startupCode);
        return startupCode;
    }

    auto lastTime = std::chrono::high_resolution_clock::now();

    // (hacky) Set first update time ~1/60 sec to avoid dealing with 0 elapsed time
    lastTime -= std::chrono::milliseconds(16);

    // check the options to start with minial panels.
    // TODO: dfagnou: this logic will move away when Panel are managed in a more "abstract" maners
    carb::settings::ISettings* settings = framework->acquireInterface<carb::settings::ISettings>();
    bool mininalPanels = settings->getAsBool("/app/window/minimalPanelsOnStartup");

    if (mininalPanels)
    {
        editor->setWindowOpen("Console", false);
        editor->setWindowOpen("Content", false);
        editor->setWindowOpen("Layers", false);
        editor->setWindowOpen("Stage", false);
    }

    // Poll window state and input
    while (editor->isRunning())
    {
        {
            CARB_PROFILE_ZONE(0, "Omniverse Kit Main loop");
            auto currentTime = std::chrono::high_resolution_clock::now();
            float elapsedTime =
                std::chrono::duration_cast<std::chrono::microseconds>(currentTime - lastTime).count() / 1000000.0f;
            lastTime = currentTime;

            // Update general data
            editor->update(elapsedTime);
        }
        CARB_PROFILE_FRAME(0, "Frame");
    }

    // Shutdown editor
    editor->shutdown();

    // Shut down MPI
    framework->acquireInterface<carb::multiprocess::MultiProcess>()->shutdown();

    CARB_PROFILE_SHUTDOWN();
    carb::profiler::deregisterGpuProfilerForClient();

    // Cleanup framework plugins configured in startup
    carb::shutdownFramework();

    // Release framework
    carb::releaseFrameworkAndDeregisterBuiltins();

    // TODO: Christopher Dannemiller - Temporary GTC hack, address a problem with the refcounting of libvt.dll and how
    // it manages objects. The crux of the problem is libvt.dll is referencing a vtable in carb.scene.hydra.dll but
    // omni_usd_plugin.dll also references libvt.dll thereby keeping it open. This means that libvt.dll unloads after
    // carb.scene.hydra.dll but because libvt.dll has a pointer to a vtable that was in carb.scene.hydra.dll an access
    // violation occurs. After discussing the issue with Brian Harris we decided it was best to wait until after GTC to
    // seek a fix. Note this crash only occurs after loading certian USD files. JIRA Ticket: GRPHN-181
#ifdef _WIN32
    ::TerminateProcess(GetCurrentProcess(), EXIT_SUCCESS);
#else
    return EXIT_SUCCESS;
#endif
}
