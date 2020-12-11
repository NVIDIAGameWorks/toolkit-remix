// Copyright (c) 2019-2020, NVIDIA CORPORATION. All rights reserved.
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

#include <omni/ext/IExt.h>
#include <omni/kit/IApp.h>

#include <memory>


#define EXTENSION_NAME "omni.ext-example_cpp_ext.plugin"

using namespace carb;

const struct carb::PluginImplDesc kPluginImpl = { EXTENSION_NAME, "Example of a native plugin extension.", "NVIDIA",
                                                  carb::PluginHotReload::eEnabled, "dev" };

CARB_PLUGIN_IMPL_DEPS(omni::kit::IApp, carb::logging::ILogging)


class NativeExtensionExample : public omni::ext::IExt
{
public:
    void onStartup(const char* extId) override
    {
        // Get app interface using Carbonite Framework
        omni::kit::IApp* app = carb::getFramework()->acquireInterface<omni::kit::IApp>();

        // Subscribe to update events and count them
        m_holder =
            carb::events::createSubscriptionToPop(app->getUpdateEventStream(), [this](carb::events::IEvent* event) {
                if (m_counter % 1000 == 0)
                {
                    printf(EXTENSION_NAME ": %d updates passed.\n", m_counter);
                    CARB_LOG_INFO(EXTENSION_NAME ": %d updates passed.\n", m_counter);
                }
                m_counter++;
            });
    }

    void onShutdown() override
    {
        // That unsubscribes from event stream
        m_holder = nullptr;
    }

private:
    int m_counter = 0;
    carb::ObjectPtr<carb::events::ISubscription> m_holder;
};

CARB_PLUGIN_IMPL(kPluginImpl, NativeExtensionExample)

void fillInterface(NativeExtensionExample& iface)
{
}
