// Copyright (c) 2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#pragma once

#include <carb/Interface.h>
#include <carb/events/IEvents.h>

namespace omni
{
namespace example
{

struct Warrior;

struct WarriorDesc
{
    int hp;
    int damage;
};

enum class WarriorEventType : uint32_t
{
    eCreate,
    eDestroy,
    eDie
};

struct IBattleSimulator
{
    CARB_PLUGIN_INTERFACE("omni::example::IBattleSimulator", 0, 1)

    /**
     * Create new warrior.
     */
    Warrior*(CARB_ABI* createWarrior)(const WarriorDesc& desc);

    void(CARB_ABI* destroyWarrior)(Warrior*);

    size_t(CARB_ABI* getWarriorCount)();

    Warrior*(CARB_ABI* getWarrior)(size_t index);

    int(CARB_ABI* getWarriorHp)(Warrior*);

    bool isWarriorDead(Warrior*);

    void(CARB_ABI* fight)(Warrior*, Warrior*);

    /**
     * Event stream of WarriorEventType
     */
    carb::events::IEventStream*(CARB_ABI* getWarriorsEventStream)();
};

inline bool IBattleSimulator::isWarriorDead(Warrior* warrior)
{
    return this->getWarriorHp(warrior) <= 0;
}

}
}
