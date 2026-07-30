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

from types import SimpleNamespace
from unittest.mock import patch

from omni.kit.test import AsyncTestCase
from omni.ui import scene as sc

from lightspeed.light.gizmos.manipulator import ClickedGesture


class _ViewportApi:
    def map_ndc_to_texture_pixel(self, ndc_location):
        return (10, 20), self


class _Sender:
    def __init__(self):
        self.gesture_payload = SimpleNamespace(ray_distance=999.0)

    def transform_space(self, from_space, to_space, point):
        assert from_space == sc.Space.WORLD
        assert to_space == sc.Space.NDC
        assert point == (1.0, 2.0, 3.0)
        return (0.1, 0.2, 0.3)


class TestClickedGesture(AsyncTestCase):
    async def test_on_ended_uses_click_payload_for_distance(self):
        viewport_api = _ViewportApi()
        gesture = SimpleNamespace(
            _viewport_api=viewport_api,
            _prim_path="/World/Light",
            sender=_Sender(),
            gesture_payload=SimpleNamespace(ray_closest_point=(1.0, 2.0, 3.0), ray_distance=42.0),
        )

        with patch("lightspeed.light.gizmos.manipulator.GlobalSelection") as mock_global_selection:
            ClickedGesture.on_ended(gesture)

        mock_global_selection.get_instance.return_value.add_manipulator_selection.assert_called_once_with(
            viewport_api, (10, 20), 42.0, "/World/Light"
        )
