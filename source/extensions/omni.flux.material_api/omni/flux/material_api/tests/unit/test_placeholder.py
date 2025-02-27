"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
* SPDX-License-Identifier: Apache-2.0
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* https://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import omni.kit.test
from pxr import Sdf


class TestPlaceholderAttribute(omni.kit.test.AsyncTestCase):
    async def setUp(self):
        await omni.usd.get_context().new_stage_async()

    async def test_placeholder_attribute(self):
        from omni.flux.material_api.placeholder_attribute import PlaceholderAttribute

        omni.kit.commands.execute("CreatePrimWithDefaultXform", prim_type="Sphere")

        usd_context = omni.usd.get_context()
        stage = usd_context.get_stage()
        prim = stage.GetPrimAtPath("/Sphere")
        attr_dict = {Sdf.PrimSpec.TypeNameKey: "bool", "customData": {"default": True}}

        # verifty attribute doesn't exist
        self.assertFalse(prim.GetAttribute("primvars:doNotCastShadows"))

        #################################################################
        # test expected usage
        #################################################################
        attr = PlaceholderAttribute(name="primvars:doNotCastShadows", prim=prim, metadata=attr_dict)

        # test stubs
        self.assertFalse(attr.ValueMightBeTimeVarying())
        self.assertFalse(attr.HasAuthoredConnections())

        # test get functions
        self.assertTrue(attr.Get())
        self.assertEqual(attr.GetPath(), "/Sphere")
        self.assertEqual(attr.GetPrim(), prim)
        self.assertEqual(attr.GetMetadata("customData"), attr_dict["customData"])
        self.assertFalse(attr.GetMetadata("test"))
        self.assertEqual(attr.GetAllMetadata(), attr_dict)

        # test CreateAttribute
        attr.CreateAttribute()

        # verifty attribute does exist
        self.assertTrue(prim.GetAttribute("primvars:doNotCastShadows"))
        prim.RemoveProperty("primvars:doNotCastShadows")
        self.assertFalse(prim.GetAttribute("primvars:doNotCastShadows"))

        #################################################################
        # test no metadata usage
        #################################################################
        attr = PlaceholderAttribute(name="primvars:doNotCastShadows", prim=prim, metadata={})

        # test stubs
        self.assertFalse(attr.ValueMightBeTimeVarying())
        self.assertFalse(attr.HasAuthoredConnections())

        # test get functions
        self.assertEqual(attr.Get(), None)
        self.assertEqual(attr.GetPath(), "/Sphere")
        self.assertEqual(attr.GetPrim(), prim)
        self.assertEqual(attr.GetMetadata("customData"), False)
        self.assertFalse(attr.GetMetadata("test"))
        self.assertEqual(attr.GetAllMetadata(), {})

        # test CreateAttribute
        attr.CreateAttribute()

        # verifty attribute doesn't exist
        self.assertFalse(prim.GetAttribute("primvars:doNotCastShadows"))

        #################################################################
        # test no prim usage
        #################################################################
        attr = PlaceholderAttribute(name="primvars:doNotCastShadows", prim=None, metadata=attr_dict)

        # test stubs
        self.assertFalse(attr.ValueMightBeTimeVarying())
        self.assertFalse(attr.HasAuthoredConnections())

        # test get functions
        self.assertTrue(attr.Get())
        self.assertEqual(attr.GetPath(), None)
        self.assertEqual(attr.GetPrim(), None)
        self.assertEqual(attr.GetMetadata("customData"), attr_dict["customData"])
        self.assertFalse(attr.GetMetadata("test"))
        self.assertEqual(attr.GetAllMetadata(), attr_dict)

        # test CreateAttribute
        attr.CreateAttribute()

        # verifty attribute doesn't exist
        self.assertFalse(prim.GetAttribute("primvars:doNotCastShadows"))

        #################################################################
        # test no name
        #################################################################
        attr = PlaceholderAttribute(name="", prim=prim, metadata=attr_dict)

        # test stubs
        self.assertFalse(attr.ValueMightBeTimeVarying())
        self.assertFalse(attr.HasAuthoredConnections())

        # test get functions
        self.assertTrue(attr.Get())
        self.assertEqual(attr.GetPath(), "/Sphere")
        self.assertEqual(attr.GetPrim(), prim)
        self.assertEqual(attr.GetMetadata("customData"), attr_dict["customData"])
        self.assertFalse(attr.GetMetadata("test"))
        self.assertEqual(attr.GetAllMetadata(), attr_dict)

        # test CreateAttribute
        attr.CreateAttribute()

        # verifty attribute doesn't exist
        self.assertFalse(prim.GetAttribute("primvars:doNotCastShadows"))
