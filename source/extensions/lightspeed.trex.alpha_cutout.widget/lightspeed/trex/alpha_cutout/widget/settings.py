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

from __future__ import annotations

__all__ = ["ALPHA_THRESHOLD_RANGE", "DEFAULT_DISABLE_ALPHA_TEST", "TRACE_RESOLUTION_RANGE", "AlphaCutoutSettings"]

import omni.usd
from carb.settings import get_settings
from lightspeed.common import constants
from lightspeed.trex.alpha_cutout.core import CutoutParameters
from omni.flux.utils.common.omni_url import OmniUrl

ALPHA_THRESHOLD_RANGE = (0, 255)
TRACE_RESOLUTION_RANGE = (64, 1024)
DEFAULT_DISABLE_ALPHA_TEST = True
_SETTINGS_ROOT = "/persistent/exts/lightspeed.trex.alpha_cutout.widget"
_OUTPUT_SUBFOLDER = "alpha_cutout"
_AMOUNT_RANGE = (0.0, 1.0)
_DEFAULTS = CutoutParameters()


def _key(name: str) -> str:
    """Return the persistent settings key of a setting.

    Args:
        name: Short setting name.

    Returns:
        Absolute settings key.
    """
    return f"{_SETTINGS_ROOT}/{name}"


def _clamp(value: float, bounds: tuple[float, float]) -> float:
    """Clamp a value into inclusive bounds.

    Args:
        value: Value to clamp.
        bounds: ``(low, high)`` bounds.

    Returns:
        The clamped value.
    """
    return min(max(value, bounds[0]), bounds[1])


class AlphaCutoutSettings:
    """Read and write the persisted conversion settings."""

    @property
    def output_folder(self) -> str:
        """Return the output folder the user chose, or an empty string for the project default.

        Returns:
            Persisted output folder.
        """
        return get_settings().get_as_string(_key("output_folder"))

    def set_output_folder(self, value: str) -> None:
        """Persist the output folder.

        Args:
            value: Folder path, or an empty string for the project default.
        """
        get_settings().set(_key("output_folder"), value)

    @property
    def alpha_threshold(self) -> int:
        """Return the alpha value at or above which a texel counts as opaque.

        Returns:
            Threshold clamped to 0-255.
        """
        return int(_clamp(get_settings().get_as_int(_key("alpha_threshold")), ALPHA_THRESHOLD_RANGE))

    def set_alpha_threshold(self, value: int) -> None:
        """Persist the alpha threshold.

        Args:
            value: Threshold, clamped to 0-255.
        """
        get_settings().set(_key("alpha_threshold"), int(_clamp(value, ALPHA_THRESHOLD_RANGE)))

    @property
    def trace_resolution(self) -> int:
        """Return the longest side of the traced mask in texels.

        Returns:
            Resolution clamped to 64-1024.
        """
        return int(_clamp(get_settings().get_as_int(_key("trace_resolution")), TRACE_RESOLUTION_RANGE))

    def set_trace_resolution(self, value: int) -> None:
        """Persist the trace resolution.

        Args:
            value: Resolution, clamped to 64-1024.
        """
        get_settings().set(_key("trace_resolution"), int(_clamp(value, TRACE_RESOLUTION_RANGE)))

    @property
    def simplify_tolerance(self) -> float:
        """Return the outline simplification tolerance in texels.

        Returns:
            Non-negative tolerance.
        """
        return max(0.0, get_settings().get_as_float(_key("simplify_tolerance")))

    def set_simplify_tolerance(self, value: float) -> None:
        """Persist the simplification tolerance.

        Args:
            value: Tolerance in texels, negative values become zero.
        """
        get_settings().set(_key("simplify_tolerance"), max(0.0, float(value)))

    @property
    def edge_margin(self) -> float:
        """Return the distance the outline grows or shrinks in texels.

        Returns:
            Margin, negative to shrink.
        """
        return get_settings().get_as_float(_key("edge_margin"))

    def set_edge_margin(self, value: float) -> None:
        """Persist the edge margin.

        Args:
            value: Margin in texels.
        """
        get_settings().set(_key("edge_margin"), float(value))

    @property
    def min_island_area(self) -> float:
        """Return the smallest outline island that is kept, in texels.

        Returns:
            Non-negative area.
        """
        return max(0.0, get_settings().get_as_float(_key("min_island_area")))

    def set_min_island_area(self, value: float) -> None:
        """Persist the minimum island area.

        Args:
            value: Area in texels, negative values become zero.
        """
        get_settings().set(_key("min_island_area"), max(0.0, float(value)))

    @property
    def disable_alpha_test(self) -> bool:
        """Return whether the generated material disables alpha testing.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("disable_alpha_test"))

    def set_disable_alpha_test(self, value: bool) -> None:
        """Persist the alpha test flag.

        Args:
            value: Whether the generated material disables alpha testing.
        """
        get_settings().set(_key("disable_alpha_test"), bool(value))

    @property
    def minimal_outline(self) -> bool:
        """Return whether the outline uses the fewest vertices within the tolerance.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("minimal_outline"))

    def set_minimal_outline(self, value: bool) -> None:
        """Persist whether the outline uses the fewest vertices within the tolerance.

        Args:
            value: The flag.
        """
        get_settings().set(_key("minimal_outline"), bool(value))

    @property
    def thicken(self) -> bool:
        """Return whether the cut mesh is extruded backwards.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("thicken"))

    def set_thicken(self, value: bool) -> None:
        """Persist whether the cut mesh is extruded backwards.

        Args:
            value: The flag.
        """
        get_settings().set(_key("thicken"), bool(value))

    @property
    def thickness(self) -> float:
        """Return the extrusion distance in mesh units.

        Returns:
            Non-negative distance.
        """
        return max(0.0, get_settings().get_as_float(_key("thickness")))

    def set_thickness(self, value: float) -> None:
        """Persist the extrusion distance.

        Args:
            value: Distance in mesh units, negative values become zero.
        """
        get_settings().set(_key("thickness"), max(0.0, float(value)))

    @property
    def thicken_back_face(self) -> bool:
        """Return whether the extrusion is closed with a back face.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("thicken_back_face"))

    def set_thicken_back_face(self, value: bool) -> None:
        """Persist whether the extrusion is closed with a back face.

        Args:
            value: The flag.
        """
        get_settings().set(_key("thicken_back_face"), bool(value))

    @property
    def thicken_anti_stretch(self) -> bool:
        """Return whether the extruded sides sample a texture band instead of smearing the edge.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("thicken_anti_stretch"))

    def set_thicken_anti_stretch(self, value: bool) -> None:
        """Persist whether the extruded sides sample a texture band instead of smearing the edge.

        Args:
            value: The flag.
        """
        get_settings().set(_key("thicken_anti_stretch"), bool(value))

    @property
    def smooth_normals(self) -> bool:
        """Return whether the thickened mesh normals are smoothed.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("smooth_normals"))

    def set_smooth_normals(self, value: bool) -> None:
        """Persist whether the thickened mesh normals are smoothed.

        Args:
            value: The flag.
        """
        get_settings().set(_key("smooth_normals"), bool(value))

    @property
    def smoothing(self) -> float:
        """Return the normal smoothing strength.

        Returns:
            Value clamped to 0-1.
        """
        return _clamp(get_settings().get_as_float(_key("smoothing")), _AMOUNT_RANGE)

    def set_smoothing(self, value: float) -> None:
        """Persist the normal smoothing strength.

        Args:
            value: Value, clamped to 0-1.
        """
        get_settings().set(_key("smoothing"), _clamp(float(value), _AMOUNT_RANGE))

    @property
    def up_normals(self) -> bool:
        """Return whether the normals are blended towards the up axis.

        Returns:
            Persisted flag.
        """
        return get_settings().get_as_bool(_key("up_normals"))

    def set_up_normals(self, value: bool) -> None:
        """Persist whether the normals are blended towards the up axis.

        Args:
            value: The flag.
        """
        get_settings().set(_key("up_normals"), bool(value))

    @property
    def up_amount(self) -> float:
        """Return the up-facing blend strength.

        Returns:
            Value clamped to 0-1.
        """
        return _clamp(get_settings().get_as_float(_key("up_amount")), _AMOUNT_RANGE)

    def set_up_amount(self, value: float) -> None:
        """Persist the up-facing blend strength.

        Args:
            value: Value, clamped to 0-1.
        """
        get_settings().set(_key("up_amount"), _clamp(float(value), _AMOUNT_RANGE))

    @property
    def parameters(self) -> CutoutParameters:
        """Return the persisted settings as conversion parameters.

        Returns:
            Parameters for the converter.
        """
        return CutoutParameters(
            alpha_threshold=self.alpha_threshold,
            trace_resolution=self.trace_resolution,
            simplify_tolerance=self.simplify_tolerance,
            edge_margin=self.edge_margin,
            min_island_area=self.min_island_area,
            minimal_outline=self.minimal_outline,
            thicken=self.thicken,
            thickness=self.thickness,
            thicken_back_face=self.thicken_back_face,
            thicken_anti_stretch=self.thicken_anti_stretch,
            smooth_normals=self.smooth_normals,
            smoothing=self.smoothing,
            up_normals=self.up_normals,
            up_amount=self.up_amount,
        )

    @staticmethod
    def default_output_folder(context_name: str) -> str:
        """Return the project folder generated files go to when the user chose none.

        Args:
            context_name: USD context that holds the project.

        Returns:
            ``<project>/assets/ingested/alpha_cutout`` with forward slashes, or an empty string without a project.
        """
        context = omni.usd.get_context(context_name)
        stage = context.get_stage() if context else None
        if not stage or stage.GetRootLayer().anonymous:
            return ""
        project_url = OmniUrl(OmniUrl(stage.GetRootLayer().realPath).parent_url)
        return str(project_url / constants.REMIX_ASSETS_FOLDER / "ingested" / _OUTPUT_SUBFOLDER)

    @staticmethod
    def defaults() -> CutoutParameters:
        """Return the built-in parameter defaults.

        Returns:
            Default conversion parameters.
        """
        return _DEFAULTS
