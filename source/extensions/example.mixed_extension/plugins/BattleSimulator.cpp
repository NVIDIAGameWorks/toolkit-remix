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
#include <carb/events/EventsUtils.h>
#include <carb/events/IEvents.h>
#include <carb/logging/Log.h>

#include <omni/example/IBattleSimulator.h>
#include <omni/kit/IEditor.h>

#include <memory>
#include <set>

#define EXTENSION_NAME "example.battle_simulator.plugin"

using namespace carb;

const struct carb::PluginImplDesc kPluginImpl = { EXTENSION_NAME,
                                                  "Example of a plugin extension which has API available in python.",
                                                  "NVIDIA", carb::PluginHotReload::eEnabled, "dev" };


CARB_PLUGIN_IMPL(kPluginImpl, omni::example::IBattleSimulator)
CARB_PLUGIN_IMPL_DEPS(carb::events::IEvents)


static carb::events::IEvents* s_events;
static carb::events::IEventStreamPtr s_stream;

CARB_EXPORT void carbOnPluginStartup()
{
    // Get editor interface using Carbonite Framework
    s_events = carb::getFramework()->acquireInterface<carb::events::IEvents>();
    s_stream = s_events->createEventStream();
}

CARB_EXPORT void carbOnPluginShutdown()
{
    s_stream = nullptr;
}

namespace omni
{
namespace example
{


struct Warrior
{
    int hp;
    int damage;
};


static std::set<Warrior*> s_warriors;

static void fireEvent(WarriorEventType type)
{
    s_stream->push(static_cast<carb::events::EventType>(type));
    s_stream->pump();
}

static Warrior* createWarrior(const WarriorDesc& desc)
{
    Warrior* w = new Warrior();

    w->hp = desc.hp;
    w->damage = desc.damage;
    s_warriors.insert(w);

    fireEvent(WarriorEventType::eCreate);

    return w;
}

static void destroyWarrior(Warrior* warrior)
{
    s_warriors.erase(warrior);
    delete warrior;

    s_stream->push(static_cast<carb::events::EventType>(WarriorEventType::eDestroy));
    s_stream->pump();
}

static size_t getWarriorCount()
{
    return s_warriors.size();
}

static Warrior* getWarrior(size_t index)
{
    return *std::next(s_warriors.begin(), index);
}

static int getWarriorHp(Warrior* warrior)
{
    return warrior->hp;
}

static void fight(Warrior* warriorA, Warrior* warriorB)
{
    int hpA = warriorA->hp;
    int hpB = warriorB->hp;
    if (hpA >= 0)
    {
        warriorB->hp -= warriorA->damage;

        if (warriorB->hp < 0)
        {
            fireEvent(WarriorEventType::eDie);
        }
    }
    if (hpB >= 0)
    {
        warriorA->hp -= warriorB->damage;

        if (warriorA->hp < 0)
        {
            fireEvent(WarriorEventType::eDie);
        }
    }
}

static carb::events::IEventStream* getWarriorsEventStream()
{
    return s_stream.get();
}

}
}

void fillInterface(omni::example::IBattleSimulator& iface)
{
    using namespace omni::example;
    iface = { createWarrior, destroyWarrior, getWarriorCount, getWarrior, getWarriorHp, fight, getWarriorsEventStream };
}
