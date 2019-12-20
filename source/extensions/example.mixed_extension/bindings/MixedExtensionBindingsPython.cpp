// Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#include "omni/example/IMixedExtension.h"

#include <carb/BindingsPythonUtils.h>

CARB_BINDINGS("example.mixed_extension.python")

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

PYBIND11_MODULE(_mixed_extension, m)
{
    m.doc() = "pybind11 omni.example.IMixedExtensions bindings";

    using namespace omni::example;

    carb::defineInterfaceClass<IMixedEventsion>(
        m, "IMixedEventsion", "acquire_mixed_extension_interface", "release_mixed_extension_interface")
        .def("get_warrior_count", wrapInterfaceFunction(&IMixedEventsion::getWarriorCount));
}
}
