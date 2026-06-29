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

__all__ = [
    "TestCameraClippingOverride",
    "TestGetCameraClippingOverride",
    "TestSetCameraClippingOverride",
]

from unittest.mock import MagicMock, patch

from omni.kit.test import AsyncTestCase

from lightspeed.trex.project_settings.core import (
    CAMERA_CLIPPING_OVERRIDE_PATH,
    SETTINGS_ROOT_PATH,
    VIEWPORT_SETTINGS_PATH,
    CameraClippingOverride,
    get_camera_clipping_override,
    set_camera_clipping_override,
)


class TestCameraClippingOverride(AsyncTestCase):
    """REMIX-4628: tests for the CameraClippingOverride dataclass."""

    async def test_defaults_match_documented_values(self):
        """The dataclass defaults should be: disabled, near=0.01, far=100000.0."""
        # Arrange / Act
        override = CameraClippingOverride()

        # Assert
        self.assertFalse(override.enabled)
        self.assertEqual(override.near_clip, 0.01)
        self.assertEqual(override.far_clip, 100000.0)


class TestGetCameraClippingOverride(AsyncTestCase):
    """REMIX-4628: tests for reading the project-scoped clipping override from a stage."""

    async def test_returns_defaults_when_stage_is_none(self):
        """A None stage must not raise; returns defaults."""
        # Arrange / Act
        result = get_camera_clipping_override(None)

        # Assert
        self.assertEqual(result, CameraClippingOverride())

    async def test_returns_defaults_when_settings_prim_is_invalid(self):
        """A stage without the Settings prim returns defaults."""
        # Arrange
        prim = MagicMock()
        prim.IsValid.return_value = False
        stage = MagicMock()
        stage.GetPrimAtPath.return_value = prim

        # Act
        result = get_camera_clipping_override(stage)

        # Assert
        self.assertEqual(result, CameraClippingOverride())
        stage.GetPrimAtPath.assert_called_once_with(CAMERA_CLIPPING_OVERRIDE_PATH)

    async def test_reads_authored_values_when_prim_is_valid(self):
        """When all three attributes are authored, the dataclass reflects them."""
        # Arrange
        attrs = {"enabled": True, "nearClip": 0.5, "farClip": 12345.0}

        def make_attr(value):
            attr = MagicMock()
            attr.HasAuthoredValue.return_value = True
            attr.Get.return_value = value
            attr.__bool__ = lambda self_: True
            return attr

        prim = MagicMock()
        prim.IsValid.return_value = True
        prim.GetAttribute.side_effect = lambda name: make_attr(attrs[name])
        stage = MagicMock()
        stage.GetPrimAtPath.return_value = prim

        # Act
        result = get_camera_clipping_override(stage)

        # Assert
        self.assertTrue(result.enabled)
        self.assertEqual(result.near_clip, 0.5)
        self.assertEqual(result.far_clip, 12345.0)


class TestSetCameraClippingOverride(AsyncTestCase):
    """REMIX-4628: tests for authoring the project-scoped clipping override on a stage."""

    async def test_returns_silently_when_stage_is_none(self):
        """A None stage is a no-op (must not raise)."""
        # Arrange / Act / Assert (no exception)
        set_camera_clipping_override(None, CameraClippingOverride())

    async def test_authors_all_three_attributes_on_root_layer(self):
        """set() must create/update the three attribute specs under the override prim."""
        # Arrange
        override_spec = MagicMock()
        override_spec.attributes = {}

        def get_prim_at_path(path):
            # Return existing override spec only for the override path
            if path == CAMERA_CLIPPING_OVERRIDE_PATH:
                return override_spec
            return MagicMock()

        target_layer = MagicMock()
        target_layer.GetPrimAtPath.side_effect = get_prim_at_path
        stage = MagicMock()
        stage.GetRootLayer.return_value = target_layer

        new_override = CameraClippingOverride(enabled=True, near_clip=0.1, far_clip=999.0)

        # Act
        with patch("lightspeed.trex.project_settings.core.core.Sdf.AttributeSpec") as attr_spec_cls:
            # Each call to Sdf.AttributeSpec() returns a fresh MagicMock representing the new spec.
            attr_spec_cls.side_effect = lambda *args, **kwargs: MagicMock()
            set_camera_clipping_override(stage, new_override)

        # Assert
        self.assertEqual(attr_spec_cls.call_count, 3)
        spec_names = {call.args[1] for call in attr_spec_cls.call_args_list}
        self.assertEqual(spec_names, {"enabled", "nearClip", "farClip"})

    async def test_upgrades_intermediate_prim_specifiers_to_def(self):
        """The Settings / Viewport / CameraClippingOverride prims must be promoted to `def`."""
        # Arrange
        prim_specs_by_path = {}

        def get_prim_at_path(path):
            spec = prim_specs_by_path.setdefault(path, MagicMock())
            spec.attributes = {}
            return spec

        target_layer = MagicMock()
        target_layer.GetPrimAtPath.side_effect = get_prim_at_path
        stage = MagicMock()
        stage.GetRootLayer.return_value = target_layer

        # Act
        with patch("lightspeed.trex.project_settings.core.core.Sdf.AttributeSpec"):
            set_camera_clipping_override(stage, CameraClippingOverride(enabled=True))

        # Assert: all three intermediate specs had their specifier set
        for path in (SETTINGS_ROOT_PATH, VIEWPORT_SETTINGS_PATH, CAMERA_CLIPPING_OVERRIDE_PATH):
            self.assertIn(path, prim_specs_by_path, f"Missing prim spec lookup for {path}")
            self.assertTrue(
                hasattr(prim_specs_by_path[path], "specifier"),
                f"specifier attribute not set on prim spec at {path}",
            )
