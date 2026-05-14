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

from typing import Any

from omni.flux.property_widget_builder.model.usd import BoundsAdapter
from omni.flux.property_widget_builder.model.usd.bounds_adapter import NormalizedBoundsStepData, RawBoundsStepData
from pxr import Sdf, UsdShade

_HARD_RANGE_KEY = "hard_range"
_SOFT_RANGE_KEY = "soft_range"


class MaterialBoundsAdapter(BoundsAdapter):
    """Material-specific adapter reading MDL/Sdr range metadata from placeholders.

    Args:
        raw_bounds_step_data: Raw placeholder metadata supplied by the shared bounds adapter contract.
    """

    @staticmethod
    def _extract_range(range_data: Any) -> tuple[Any | None, Any | None]:
        """Return ``(min, max)`` from dict-shaped range metadata.

        Args:
            range_data: Raw range metadata expected to carry ``min`` and ``max`` keys.

        Returns:
            Tuple containing the minimum and maximum values, or ``None`` values when unavailable.
        """
        if not isinstance(range_data, dict):
            return None, None
        return range_data.get("min"), range_data.get("max")

    def _normalize_bounds_step_data(
        self, raw_bounds_step_data: RawBoundsStepData | None
    ) -> NormalizedBoundsStepData | None:
        """Normalize material placeholder metadata into shared bounds/step keys.

        MDL-authored ``sdrMetadata`` ranges win for bounds. Legacy ``customData``
        supplies fallback bounds when MDL ranges are absent, and can provide
        ``ui:step`` because MDL step metadata is not standardized for this
        workflow.

        Args:
            raw_bounds_step_data: Raw metadata dictionary from a material placeholder.

        Returns:
            Normalized bounds and step data, or ``None`` when no usable metadata exists.
        """
        if not isinstance(raw_bounds_step_data, dict):
            return None

        custom_data = raw_bounds_step_data.get(Sdf.AttributeSpec.CustomDataKey)
        custom_normalized = super()._normalize_bounds_step_data(custom_data) if isinstance(custom_data, dict) else None

        sdr_metadata = raw_bounds_step_data.get(UsdShade.Tokens.sdrMetadata)
        if not isinstance(sdr_metadata, dict):
            return custom_normalized or super()._normalize_bounds_step_data(raw_bounds_step_data)

        soft_min, soft_max = self._extract_range(sdr_metadata.get(_SOFT_RANGE_KEY))
        hard_min, hard_max = self._extract_range(sdr_metadata.get(_HARD_RANGE_KEY))

        has_mdl_bounds = any(value is not None for value in (soft_min, soft_max, hard_min, hard_max))
        if not has_mdl_bounds:
            return custom_normalized or super()._normalize_bounds_step_data(raw_bounds_step_data)

        top_level_normalized = super()._normalize_bounds_step_data(raw_bounds_step_data)
        step = None
        if custom_normalized is not None:
            step = custom_normalized["step"]
        if step is None and top_level_normalized is not None:
            step = top_level_normalized["step"]

        return {
            "soft_min": soft_min,
            "soft_max": soft_max,
            "hard_min": hard_min,
            "hard_max": hard_max,
            "step": step,
        }
