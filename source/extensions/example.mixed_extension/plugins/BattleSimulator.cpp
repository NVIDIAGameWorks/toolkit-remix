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

#include <omni/example/IBattleSimulator.h>
#include <omni/kit/IEditor.h>

#include <memory>
#include <set>

#define EXTENSION_NAME "example.mixed_extension.plugin"

using namespace carb;

const struct carb::PluginImplDesc kPluginImpl = { EXTENSION_NAME,
                                                  "Example of a plugin extension which has API available in python.",
                                                  "NVIDIA", carb::PluginHotReload::eEnabled, "dev" };


CARB_PLUGIN_IMPL(kPluginImpl, omni::example::IBattleSimulator)
CARB_PLUGIN_IMPL_DEPS(omni::kit::IEditor)


static omni::kit::IEditor* s_editor;

CARB_EXPORT void carbOnPluginStartup()
{
    // Get editor interface using Carbonite Framework
    s_editor = carb::getFramework()->acquireInterface<omni::kit::IEditor>();
}

CARB_EXPORT void carbOnPluginShutdown()
{
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

static Warrior* createWarrior(const WarriorDesc& desc)
{
    Warrior* w = new Warrior();

    w->hp = desc.hp;
    w->damage = desc.damage;
    s_warriors.insert(w);

    return w;
}

static void destroyWarrior(Warrior* warrior)
{
    s_warriors.erase(warrior);
    delete warrior;
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
    }
    if (hpB >= 0)
    {
        warriorA->hp -= warriorB->damage;
    }
}

}
}

void fillInterface(omni::example::IBattleSimulator& iface)
{
    using namespace omni::example;
    iface = {
        createWarrior, destroyWarrior, getWarriorCount, getWarrior, getWarriorHp, fight,
    };
}
