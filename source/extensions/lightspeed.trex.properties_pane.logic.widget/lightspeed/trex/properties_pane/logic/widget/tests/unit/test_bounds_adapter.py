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
from lightspeed.trex.properties_pane.logic.widget.bounds_adapter import OgnBoundsAdapter
from pxr import Gf


class TestOgnBoundsAdapter(omni.kit.test.AsyncTestCase):
    """Unit tests for OGN adapter normalization contract."""

    async def test_extract_bounds_from_ogn_ui_metadata(self):
        # Arrange
        adapter = OgnBoundsAdapter(
            {
                "soft_min": 0.0,
                "soft_max": 1.0,
                "hard_min": Gf.Vec2f(-2.0, -1.0),
                "hard_max": Gf.Vec2f(4.0, 8.0),
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (0.0, 1.0, Gf.Vec2f(-2.0, -1.0), Gf.Vec2f(4.0, 8.0)))

    async def test_extract_step_from_ogn_ui_metadata(self):
        # Arrange
        adapter = OgnBoundsAdapter({"ui_step": 1.5})

        # Act
        step = adapter.step

        # Assert
        self.assertEqual(step, 1.5)
