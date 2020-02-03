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
#include <carb/events/IEvents.h>

CARB_BINDINGS("example.battle_simulator.python")

DISABLE_PYBIND11_DYNAMIC_CAST(carb::events::IEventStream);

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

    py::class_<Warrior>(m, "Warrior");

    py::enum_<WarriorEventType>(m, "WarriorEventType", R"(
        WarriorEvent types.
        )")
        .value("CREATE", WarriorEventType::eCreate)
        .value("DESTROY", WarriorEventType::eDestroy)
        .value("DIE", WarriorEventType::eDie);

    carb::defineInterfaceClass<IBattleSimulator>(
        m, "IBattleSimulator", "acquire_battle_simulator_interface", "release_battle_simulator_interface")
        .def("get_warrior_count", wrapInterfaceFunction(&IBattleSimulator::getWarriorCount))
        .def("get_warriors",
             [](IBattleSimulator* self) {
                 std::vector<Warrior*> warriors(self->getWarriorCount());
                 for (size_t i = 0; i < warriors.size(); i++)
                 {
                     warriors[i] = self->getWarrior(i);
                 }
                 return warriors;
             })

        .def("create_warrior",
             [](IBattleSimulator* self, int hp, int damage) -> Warrior* {
                 return self->createWarrior({ hp, damage });
             },
             py::arg("hp"), py::arg("damage"), py::return_value_policy::reference)
        .def("create_warrior", wrapInterfaceFunction(&IBattleSimulator::createWarrior), py::return_value_policy::reference)
        .def("destroy_warrior", wrapInterfaceFunction(&IBattleSimulator::destroyWarrior))
        .def("get_warrior_hp", wrapInterfaceFunction(&IBattleSimulator::getWarriorHp))
        .def("fight", wrapInterfaceFunction(&IBattleSimulator::fight))
        .def("get_warrior_event_stream", wrapInterfaceFunction(&IBattleSimulator::getWarriorsEventStream),
             py::return_value_policy::reference);
}
}
