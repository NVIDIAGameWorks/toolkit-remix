"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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
from omni.flux.utils.common.prims import get_omni_prims, get_proto_from_prim, unique_prim_sequence
from pxr import Sdf, Usd


class TestPrims(omni.kit.test.AsyncTestCase):
    async def test_get_proto_from_prim_returns_input_without_composition(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/World/A")

        # Act
        prototype = get_proto_from_prim(prim)

        # Assert
        self.assertEqual(prototype, prim)

    async def test_get_proto_from_prim_returns_referenced_prim(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prototype = stage.DefinePrim("/World/Prototypes/A")
        instance = stage.DefinePrim("/World/Instances/A")
        instance.GetReferences().AddInternalReference("/World/Prototypes/A")

        # Act
        resolved_prototype = get_proto_from_prim(instance)

        # Assert
        self.assertEqual(resolved_prototype, prototype)

    async def test_get_omni_prims_returns_reserved_kit_paths(self):
        # Act
        omni_prims = get_omni_prims()

        # Assert
        self.assertIn(Sdf.Path("/OmniverseKit_Persp"), omni_prims)
        self.assertIn(Sdf.Path("/OmniKit_Viewport_LightRig"), omni_prims)
        self.assertTrue(all(isinstance(path, Sdf.Path) for path in omni_prims))

    async def test_unique_prim_sequence_keeps_last_occurrence(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim_a = stage.DefinePrim("/World/A")
        prim_b = stage.DefinePrim("/World/B")

        # Act
        deduped_prims = unique_prim_sequence([prim_a, prim_b, prim_a])

        # Assert
        self.assertEqual([str(prim.GetPath()) for prim in deduped_prims], ["/World/B", "/World/A"])

    async def test_unique_prim_sequence_can_normalize_to_prototypes(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prototype = stage.DefinePrim("/World/Prototypes/A")
        instance = stage.DefinePrim("/World/Instances/A")
        instance.GetReferences().AddInternalReference("/World/Prototypes/A")

        # Act
        deduped_prims = unique_prim_sequence([instance, prototype], prototypes_only=True)

        # Assert
        self.assertEqual([str(prim.GetPath()) for prim in deduped_prims], ["/World/Prototypes/A"])

    async def test_unique_prim_sequence_skips_invalid_prims(self):
        # Arrange
        stage = Usd.Stage.CreateInMemory()
        prim = stage.DefinePrim("/World/A")
        invalid_prim = stage.GetPrimAtPath("/World/Missing")

        # Act
        deduped_prims = unique_prim_sequence([invalid_prim, prim])

        # Assert
        self.assertEqual([str(prim.GetPath()) for prim in deduped_prims], ["/World/A"])
