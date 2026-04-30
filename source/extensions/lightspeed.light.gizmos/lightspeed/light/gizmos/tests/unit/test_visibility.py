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

__all__ = ["TestParentResolvesInComposition"]

import omni.kit.test
from lightspeed.light.gizmos.model import _parent_resolves_in_composition
from pxr import Sdf, Usd


class TestParentResolvesInComposition(omni.kit.test.AsyncTestCase):
    """REMIX-3969: light gizmos must hide when their parent prim is not really
    present in the active stage's composition (e.g., a mod-authored light whose
    parent captured-mesh is not in the currently loaded capture).

    The predicate distinguishes a real parent (`def` or `class` spec on any
    layer in the stack) from a phantom parent (only `over` opinions). USD's
    `UsdPrim.HasDefiningSpecifier()` is the precise check.
    """

    async def test_parent_with_def_in_capture_layer_returns_true(self):
        """Mod-authored light under a captured-mesh path: capture sublayer
        contributes a `def Mesh`, mod sublayer contributes the `def DistantLight`
        beneath an `over`. The parent has a defining specifier → predicate True.
        """
        capture_layer = Sdf.Layer.CreateAnonymous("capture")
        capture_layer.ImportFromString(
            """#sdf 1
            (
                defaultPrim = "RootNode"
            )

            def Xform "RootNode"
            {
                def Mesh "mesh_A"
                {
                }
            }
            """
        )
        mod_layer = Sdf.Layer.CreateAnonymous("mod")
        mod_layer.ImportFromString(
            """#sdf 1

            over "RootNode"
            {
                over "mesh_A"
                {
                    def DistantLight "light_LT"
                    {
                    }
                }
            }
            """
        )
        root_layer = Sdf.Layer.CreateAnonymous("root")
        # Mod is the strongest sublayer (typical Remix authoring), capture beneath.
        root_layer.subLayerPaths.append(mod_layer.identifier)
        root_layer.subLayerPaths.append(capture_layer.identifier)
        stage = Usd.Stage.Open(root_layer)

        light = stage.GetPrimAtPath("/RootNode/mesh_A/light_LT")
        self.assertTrue(light.IsValid(), "light prim should compose")
        self.assertTrue(
            _parent_resolves_in_composition(light),
            "parent has `def` from capture sublayer; predicate must return True",
        )

    async def test_parent_with_only_over_in_mod_layer_returns_false(self):
        """Mod-authored light under a captured-mesh path that is NOT in the
        active capture: the mod layer's `over` is the only spec for the parent
        path. No `def` anywhere in the stack → predicate False (orphan light).
        This is the REMIX-3969 bug case.
        """
        mod_layer = Sdf.Layer.CreateAnonymous("mod")
        mod_layer.ImportFromString(
            """#sdf 1

            over "RootNode"
            {
                over "phantom_mesh"
                {
                    def DistantLight "light_LT"
                    {
                    }
                }
            }
            """
        )
        root_layer = Sdf.Layer.CreateAnonymous("root")
        root_layer.subLayerPaths.append(mod_layer.identifier)
        stage = Usd.Stage.Open(root_layer)

        light = stage.GetPrimAtPath("/RootNode/phantom_mesh/light_LT")
        self.assertTrue(light.IsValid(), "light prim itself composes via its `def` spec")
        self.assertFalse(
            _parent_resolves_in_composition(light),
            "parent is over-only with no defining spec; predicate must return False",
        )

    async def test_light_under_pseudo_root_returns_true(self):
        """A light authored at the scene root has no real parent prim.
        Predicate must short-circuit and return True so user-added scene lights
        are not falsely hidden.
        """
        root_layer = Sdf.Layer.CreateAnonymous("root")
        root_layer.ImportFromString(
            """#sdf 1

            def DistantLight "scene_root_light"
            {
            }
            """
        )
        stage = Usd.Stage.Open(root_layer)

        light = stage.GetPrimAtPath("/scene_root_light")
        self.assertTrue(light.IsValid())
        self.assertTrue(light.GetParent().IsPseudoRoot())
        self.assertTrue(
            _parent_resolves_in_composition(light),
            "light at scene root must be visible",
        )

    async def test_parent_defined_via_class_returns_true(self):
        """If the parent is defined via `class` (not `def` or `over`), USD's
        `HasDefiningSpecifier` still returns True — class is a defining
        specifier. The light's gizmo must remain visible.
        """
        layer = Sdf.Layer.CreateAnonymous("class_root")
        layer.ImportFromString(
            """#sdf 1

            class "ClassMesh"
            {
                def DistantLight "light_LT"
                {
                }
            }
            """
        )
        stage = Usd.Stage.Open(layer)

        light = stage.GetPrimAtPath("/ClassMesh/light_LT")
        self.assertTrue(light.IsValid())
        self.assertTrue(
            _parent_resolves_in_composition(light),
            "class specifier is a defining specifier; predicate must return True",
        )
