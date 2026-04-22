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
from lightspeed.trex.properties_pane.particle.widget.bounds_adapter import ParticleBoundsAdapter
from pxr import Gf
from unittest.mock import patch


class TestParticleBoundsAdapter(omni.kit.test.AsyncTestCase):
    """Unit tests for particle adapter normalization and compatibility."""

    async def test_extract_bounds_from_panel_ui_metadata(self):
        # Arrange
        adapter = ParticleBoundsAdapter(
            {
                "soft_min": Gf.Vec2f(1.0, 2.0),
                "soft_max": Gf.Vec2f(4.0, 8.0),
                "hard_min": -1.0,
                "hard_max": 10.0,
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (Gf.Vec2f(1.0, 2.0), Gf.Vec2f(4.0, 8.0), -1.0, 10.0))

    async def test_extract_step_from_panel_ui_metadata(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"ui_step": 0.25})

        # Act
        step = adapter.step

        # Assert
        self.assertEqual(step, 0.25)

    async def test_extract_bounds_from_limits_custom_data(self):
        # Arrange
        adapter = ParticleBoundsAdapter(
            {
                "limits": {
                    "soft": {"minimum": Gf.Vec2f(1.0, 2.0), "maximum": Gf.Vec2f(5.0, 9.0)},
                    "hard": {"minimum": 0.0, "maximum": 10.0},
                }
            }
        )

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (Gf.Vec2f(1.0, 2.0), Gf.Vec2f(5.0, 9.0), 0.0, 10.0))

    async def test_extract_step_from_limits_custom_data(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"limits": {"step": 0.1}})

        # Act
        step = adapter.step

        # Assert
        self.assertEqual(step, 0.1)

    async def test_extract_step_from_nested_soft_hard_limits(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"limits": {"soft": {"step": 0.2}, "hard": {"step": 1.0}}})

        # Act / Assert
        self.assertEqual(adapter.step, 0.2)

    async def test_conflicting_nested_soft_hard_step_logs_warning(self):
        # Arrange
        raw_metadata = {"limits": {"soft": {"step": 0.2}, "hard": {"step": 1.0}}}

        # Act
        with patch("lightspeed.trex.properties_pane.particle.widget.bounds_adapter.carb.log_warn") as mock_log_warn:
            adapter = ParticleBoundsAdapter(raw_metadata)

        # Assert
        self.assertEqual(adapter.step, 0.2)
        mock_log_warn.assert_called_once()

    async def test_extract_bounds_from_mapping_like_raw_payload(self):
        # Arrange
        class _MappingLike:
            def __init__(self, payload):
                self._payload = payload

            def get(self, key, default=None):
                return self._payload.get(key, default)

        adapter = ParticleBoundsAdapter(
            _MappingLike(
                {
                    "limits": {
                        "soft": {"minimum": 1.0, "maximum": 9.0},
                        "hard": {"minimum": 0.0, "maximum": 10.0},
                    }
                }
            )
        )

        # Act / Assert
        self.assertEqual(adapter.bounds, (1.0, 9.0, 0.0, 10.0))

    async def test_none_raw_payload_has_no_bounds_or_step(self):
        # Arrange
        adapter = ParticleBoundsAdapter(None)

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_empty_payload_has_no_bounds_or_step(self):
        # Arrange
        adapter = ParticleBoundsAdapter({})

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_missing_limits_payload_has_no_bounds_or_step(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"other": 1})

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_empty_limits_payload_has_no_bounds_or_step(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"limits": {}})

        # Act
        bounds = adapter.bounds
        step = adapter.step

        # Assert
        self.assertIsNone(bounds)
        self.assertIsNone(step)

    async def test_hard_min_only_limits_keep_lower_bound(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"limits": {"hard": {"minimum": 1.0}}})

        # Act
        bounds = adapter.bounds

        # Assert
        self.assertEqual(bounds, (1.0, None, 1.0, None))

    async def test_no_step_in_limits_returns_none_step(self):
        # Arrange
        adapter = ParticleBoundsAdapter(
            {
                "limits": {
                    "soft": {"minimum": 0.0, "maximum": 1.0},
                    "hard": {"minimum": -1.0, "maximum": 2.0},
                }
            }
        )

        # Act
        step = adapter.step

        # Assert
        self.assertIsNone(step)

    async def test_fallback_to_legacy_range_contract(self):
        # Arrange
        adapter = ParticleBoundsAdapter({"range": {"min": -2.0, "max": 12.0}, "ui:step": 0.5})

        # Act / Assert
        self.assertEqual(adapter.bounds, (-2.0, 12.0, None, None))
        self.assertEqual(adapter.step, 0.5)
