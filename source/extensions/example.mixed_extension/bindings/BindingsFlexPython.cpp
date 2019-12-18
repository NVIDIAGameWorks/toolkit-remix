// Copyright (c) 2018-2019, NVIDIA CORPORATION.  All rights reserved.
//
// NVIDIA CORPORATION and its licensors retain all intellectual property
// and proprietary rights in and to this software, related documentation
// and any modifications thereto.  Any use, reproduction, disclosure or
// distribution of this software and related documentation without an express
// license agreement from NVIDIA CORPORATION is strictly prohibited.
//
#include "carb/flex/Flex.h"

#include <carb/BindingsPythonUtils.h>

CARB_BINDINGS("carb.flex.python")

namespace carb
{
namespace flex
{

}
}

namespace
{

PYBIND11_MODULE(_flex, m)
{
    using namespace carb;
    using namespace carb::flex;

    m.doc() = "pybind11 carb.flex bindings";

    defineInterfaceClass<Flex>(m, "Flex", "acquire_flex_interface", "release_flex_interface")
        .def("get_particle_count", wrapInterfaceFunction(&Flex::getParticleCount));
}
}
