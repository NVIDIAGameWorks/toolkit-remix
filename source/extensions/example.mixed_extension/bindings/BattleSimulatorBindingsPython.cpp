// Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#include "omni/example/IBattleSimulator.h"

#include <carb/BindingsPythonUtils.h>

CARB_BINDINGS("example.battle_simulator.python")

namespace omni
{
namespace example
{

struct Warrior
{
};

}
}

namespace
{

PYBIND11_MODULE(_battle_simulator, m)
{
    m.doc() = "pybind11 omni.example.IBattleSimulator bindings";

    using namespace omni::example;

    carb::defineInterfaceClass<IBattleSimulator>(
        m, "IBattleSimulator", "acquire_battle_simulator_interface", "release_battle_simulator_interface")
        .def("get_warrior_count", wrapInterfaceFunction(&IBattleSimulator::getWarriorCount));
}
}
