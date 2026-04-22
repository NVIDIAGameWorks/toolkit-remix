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

from omni.flux.property_widget_builder.model.usd import BoundsAdapter
from omni.flux.property_widget_builder.model.usd.bounds_adapter import NormalizedBoundsStepData, RawBoundsStepData


class OgnBoundsAdapter(BoundsAdapter):
    """OGN-specific adapter using metadata pre-read by the logic panel."""

    def _normalize_bounds_step_data(
        self, raw_bounds_step_data: RawBoundsStepData | None
    ) -> NormalizedBoundsStepData | None:
        """Normalize logic-panel OGN metadata to shared bounds/step keys.

        Args:
            raw_bounds_step_data: OGN UI metadata dictionary produced by
                ``get_ogn_ui_metadata``.

        Returns:
            Normalized dict with ``soft_min``, ``soft_max``, ``hard_min``,
            ``hard_max``, and ``step`` keys, or ``None`` when payload is not
            dict-like.
        """
        if not isinstance(raw_bounds_step_data, dict):
            return None
        return {
            "soft_min": raw_bounds_step_data.get("soft_min"),
            "soft_max": raw_bounds_step_data.get("soft_max"),
            "hard_min": raw_bounds_step_data.get("hard_min"),
            "hard_max": raw_bounds_step_data.get("hard_max"),
            "step": raw_bounds_step_data.get("ui_step"),
        }
