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
from omni.flux.utils.common import lights as _lights
from pxr import Usd

__all__ = ["TestPrimLightClassification"]


class TestPrimLightClassification(omni.kit.test.AsyncTestCase):
    """Classify built-in light names and real USD prims."""

    async def test_classify_lights_returns_expected_types_for_builtin_schemas(self):
        """Preserve name mappings and classify supported and versioned light prims."""
        stage = Usd.Stage.CreateInMemory()

        cases = (
            ("CylinderLight", _lights.LightTypes.CylinderLight),
            ("DiskLight", _lights.LightTypes.DiskLight),
            ("DistantLight", _lights.LightTypes.DistantLight),
            ("DomeLight", _lights.LightTypes.DomeLight),
            ("DomeLight_1", _lights.LightTypes.DomeLight),
            ("PortalLight", _lights.LightTypes.PortalLight),
            ("RectLight", _lights.LightTypes.RectLight),
            ("SphereLight", _lights.LightTypes.SphereLight),
        )
        for name, expected in cases:
            with self.subTest(title=name):
                prim = stage.DefinePrim(f"/{name}", name)
                self.assertEqual(_lights.get_light_type(prim), expected)
                self.assertEqual(_lights.get_light_type_from_type_name(name), expected)
        self.assertEqual(_lights.LightTypes.RectLight.value, "Rect Light")

        self.assertIsNone(_lights.get_light_type_from_type_name("UnknownLight"))
        self.assertIsNone(_lights.get_light_type(stage.DefinePrim("/NonLight", "Xform")))
        self.assertIsNone(_lights.get_light_type(stage.GetPrimAtPath("/Missing")))
