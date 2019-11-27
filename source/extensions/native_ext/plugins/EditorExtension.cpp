// Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//

#define CARB_EXPORTS

#include <carb/PluginUtils.h>
#include <carb/logging/Log.h>

#include <omni/kit/IEditor.h>
#include <omni/kit/IMinimal.h>

#include <memory>


#define EXTENSION_NAME "example.cppext.plugin"

using namespace carb;

const struct carb::PluginImplDesc kPluginImpl = { EXTENSION_NAME, "Example of a native plugin extension.", "NVIDIA",
                                                  carb::PluginHotReload::eEnabled, "dev" };

// This extension implements minimal (IMinimal) interface. Empty one, just to allow python code to load and unload this
// plugin using Carbonite. Loading and unloading will give 2 entry points: carbOnPluginStartup()/carbOnPluginShutdown()
// which is already enough to hook up into Editor and extend it.
CARB_PLUGIN_IMPL(kPluginImpl, omni::kit::IMinimal)
CARB_PLUGIN_IMPL_DEPS(omni::kit::IEditor, carb::logging::Logging)

void fillInterface(omni::kit::IMinimal& iface)
{
    iface = {};
}

static omni::kit::IEditor* s_editor;
static omni::kit::SubscriptionId s_updateSub;
static float s_time = 0;

CARB_EXPORT void carbOnPluginStartup()
{
    // Get editor interface using Carbonite Framework
    s_editor = carb::getFramework()->acquireInterface<omni::kit::IEditor>();

    // We can now fully use IEditor. Let's subscribe to update events as an example:
    s_updateSub = s_editor->subscribeToUpdateEvents(
        [](float elapsedTime, void* userData) {
            s_time += elapsedTime;
            if (s_time > 5.0f)
            {
                CARB_LOG_INFO("5 seconds passed");
                s_time = 0;
            }
        },
        nullptr);
}

CARB_EXPORT void carbOnPluginShutdown()
{
    // Plugin is being unloaded, hence unsubscribe from update events
    s_editor->unsubscribeToUpdateEvents(s_updateSub);
}
