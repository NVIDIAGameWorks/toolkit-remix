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

import math
from typing import Any

import omni.kit.test
from lightspeed.ui_scene.light_manipulator import (
    compute_luminance,
    compute_threshold_distance,
)
from pxr import UsdLux


class _FakeAttr:
    def __init__(self, value: Any, *, raises: bool = False):
        self._value = value
        self._raises = raises

    def Get(self, _time):  # noqa: N802 - test stub mirrors the USD attribute API.
        if self._raises:
            raise RuntimeError("unreadable attr")
        return self._value


class _FakeLight:
    def __init__(
        self,
        *,
        intensity: Any = 1.0,
        exposure: Any = 0.0,
        color: Any = (1.0, 1.0, 1.0),
        enable_temperature: Any = False,
        temperature: Any = 6500.0,
    ):
        self._intensity = intensity
        self._exposure = exposure
        self._color = color
        self._enable_temperature = enable_temperature
        self._temperature = temperature

    def GetIntensityAttr(self):  # noqa: N802 - test stub mirrors the USD light API.
        return self._intensity

    def GetExposureAttr(self):  # noqa: N802 - test stub mirrors the USD light API.
        return self._exposure

    def GetColorAttr(self):  # noqa: N802 - test stub mirrors the USD light API.
        return self._color

    def GetEnableColorTemperatureAttr(self):  # noqa: N802 - test stub mirrors the USD light API.
        return self._enable_temperature

    def GetColorTemperatureAttr(self):  # noqa: N802 - test stub mirrors the USD light API.
        return self._temperature


class _FakeModel:
    def __init__(self, light):
        self.light = light
        self.time = None


class TestPhotometricHelpers(omni.kit.test.AsyncTestCase):
    """Pure-function tests for the photometric helper functions."""

    async def test_compute_luminance_with_no_model_returns_zero(self):
        """Missing light model collapses to zero brightness."""
        self.assertEqual(compute_luminance(None), 0.0)

    async def test_compute_luminance_uses_intensity_for_white_default_light(self):
        """White light at zero exposure has luminance equal to intensity."""
        light = _FakeLight(intensity=_FakeAttr(25.0))

        self.assertAlmostEqual(compute_luminance(_FakeModel(light)), 25.0, places=6)

    async def test_compute_luminance_applies_exposure_multiplier(self):
        """Exposure is a power-of-two multiplier."""
        light = _FakeLight(intensity=_FakeAttr(25.0), exposure=_FakeAttr(1.0))

        self.assertAlmostEqual(compute_luminance(_FakeModel(light)), 50.0, places=6)

    async def test_compute_luminance_uses_rec709_color_weights(self):
        """RGB values are projected to brightness with Rec.709 linear weights."""
        light = _FakeLight(intensity=_FakeAttr(10.0), color=_FakeAttr((0.25, 0.5, 1.0)))
        expected = (0.2126 * 0.25 + 0.7152 * 0.5 + 0.0722 * 1.0) * 10.0

        self.assertAlmostEqual(compute_luminance(_FakeModel(light)), expected, places=6)

    async def test_compute_luminance_applies_color_temperature_when_enabled(self):
        """Enabled color temperature multiplies the authored RGB before weighting."""
        light = _FakeLight(
            intensity=_FakeAttr(10.0),
            enable_temperature=_FakeAttr(True),
            temperature=_FakeAttr(3000.0),
        )
        temp_rgb = UsdLux.BlackbodyTemperatureAsRgb(3000.0)
        expected = (0.2126 * temp_rgb[0] + 0.7152 * temp_rgb[1] + 0.0722 * temp_rgb[2]) * 10.0

        self.assertAlmostEqual(compute_luminance(_FakeModel(light)), expected, places=6)

    async def test_compute_luminance_unreadable_attributes_use_safe_defaults(self):
        """Malformed or unreadable USD attributes do not crash cone sizing."""
        light = _FakeLight(
            intensity=_FakeAttr(None),
            exposure=_FakeAttr(None, raises=True),
            color=_FakeAttr(None),
            enable_temperature=_FakeAttr(True),
            temperature=_FakeAttr(None),
        )

        self.assertEqual(compute_luminance(_FakeModel(light)), 0.0)

        fallback_light = _FakeLight(
            intensity=_FakeAttr(2.0),
            exposure=_FakeAttr("bad"),
            color=_FakeAttr("bad"),
            enable_temperature=_FakeAttr(True),
            temperature=_FakeAttr(None),
        )
        self.assertAlmostEqual(compute_luminance(_FakeModel(fallback_light)), 2.0, places=6)

    async def test_sphere_distance_matches_closed_form(self):
        """Sphere on-axis: `d = R · sqrt(π·L / T)` exactly when d > R."""
        # Reference value from the closed-form sphere model for L=100, T=10, R=0.5.
        d = compute_threshold_distance(UsdLux.SphereLight, 0.5, 100.0, 10.0)
        self.assertAlmostEqual(d, 2.8024956081989645, places=6)

    async def test_disk_distance_matches_closed_form(self):
        """Disk on-axis: `d = R · sqrt(max(0, π·L/T - 1))`."""
        # Reference value from the closed-form disk model for L=500, T=10, R=0.5.
        d = compute_threshold_distance(UsdLux.DiskLight, 0.5, 500.0, 10.0)
        self.assertAlmostEqual(d, 6.2465917242823235, places=6)

    async def test_disk_degenerate_when_threshold_above_surface_illuminance(self):
        """Disk distance clamps to 0 (no NaN) when `π·L < T`."""
        d = compute_threshold_distance(UsdLux.DiskLight, 0.5, 1.0, 100.0)
        self.assertEqual(d, 0.0)

    async def test_zero_or_negative_inputs_collapse_to_zero(self):
        """Pathological inputs (zero radius/brightness/threshold, negative L) collapse to 0."""
        for brightness, threshold, radius in [
            (0.0, 10.0, 0.5),
            (100.0, 0.0, 0.5),
            (100.0, 10.0, 0.0),
            (-1.0, 10.0, 0.5),
        ]:
            self.assertEqual(compute_threshold_distance(UsdLux.SphereLight, radius, brightness, threshold), 0.0)
            self.assertEqual(compute_threshold_distance(UsdLux.DiskLight, radius, brightness, threshold), 0.0)

    async def test_unsupported_light_class_returns_zero(self):
        """Light classes without a cone formula (Rect, Cylinder, Distant) return 0."""
        self.assertEqual(compute_threshold_distance(UsdLux.RectLight, 0.5, 100.0, 10.0), 0.0)
        self.assertEqual(compute_threshold_distance(UsdLux.CylinderLight, 0.5, 100.0, 10.0), 0.0)
        self.assertEqual(compute_threshold_distance(UsdLux.DistantLight, 0.5, 100.0, 10.0), 0.0)

    async def test_threshold_inversely_scales_distance_for_sphere(self):
        """Halving the threshold grows the sphere distance by sqrt(2) (`d ∝ 1/sqrt(T)`)."""
        d_at_t10 = compute_threshold_distance(UsdLux.SphereLight, 0.5, 100.0, 10.0)
        d_at_t5 = compute_threshold_distance(UsdLux.SphereLight, 0.5, 100.0, 5.0)
        self.assertAlmostEqual(d_at_t5 / d_at_t10, math.sqrt(2.0), places=6)

    async def test_intensity_scales_distance_for_sphere(self):
        """Quadrupling brightness should double the sphere distance — `d ∝ sqrt(L)`."""
        d_at_l100 = compute_threshold_distance(UsdLux.SphereLight, 0.5, 100.0, 10.0)
        d_at_l400 = compute_threshold_distance(UsdLux.SphereLight, 0.5, 400.0, 10.0)
        self.assertAlmostEqual(d_at_l400 / d_at_l100, 2.0, places=6)
