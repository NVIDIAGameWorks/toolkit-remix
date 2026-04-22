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

from typing import Any, TypeAlias

import carb

from omni.flux.property_widget_builder.model.usd import BoundsAdapter
from omni.flux.property_widget_builder.model.usd.bounds_adapter import NormalizedBoundsStepData, RawBoundsStepData

# NOTE:
# Keep ``typing.TypeAlias`` while this repo targets Python 3.10 (cp310).
# Migrate to PEP 695 ``type`` aliases when minimum Python >= 3.12.
_RealNumber: TypeAlias = float | int
_RealNumberSequence: TypeAlias = tuple[_RealNumber, ...] | list[_RealNumber]
_BoundsValue: TypeAlias = _RealNumber | _RealNumberSequence


class ParticleBoundsAdapter(BoundsAdapter):
    """Particle-specific adapter reading USD limits metadata."""

    @staticmethod
    def __extract_limits_step(limits: Any) -> _RealNumber | None:
        """Resolve particle step with backward-compatible precedence.

        Canonical metadata uses ``limits.step``. We still support nested
        ``limits.soft.step`` / ``limits.hard.step`` to preserve the behavior
        that existed on ``main`` where soft was visited before hard (so soft
        step wins when both are present).

        Args:
            limits: ``limits`` mapping payload from particle metadata.

        Returns:
            Resolved numeric step value, or ``None`` when no numeric step exists.
        """
        canonical_step = limits.get("step")
        if isinstance(canonical_step, (int, float)):
            return canonical_step

        soft_step = None
        hard_step = None
        soft_block = limits.get("soft")
        if soft_block:
            soft_step = soft_block.get("step")
        hard_block = limits.get("hard")
        if hard_block:
            hard_step = hard_block.get("step")

        if soft_step is not None and hard_step is not None and soft_step != hard_step:
            carb.log_warn("Found conflicting limits soft/hard step values; preferring soft step.")
        if isinstance(soft_step, (int, float)):
            return soft_step
        if isinstance(hard_step, (int, float)):
            return hard_step
        return None

    def _normalize_bounds_step_data(
        self, raw_bounds_step_data: RawBoundsStepData | None
    ) -> NormalizedBoundsStepData | None:
        """Normalize particle metadata payload into canonical bounds/step keys.

        Args:
            raw_bounds_step_data: Raw particle payload from panel-provided
                metadata source, typically a dict-like object containing
                ``limits`` or legacy range keys.

        Returns:
            Normalized bounds/step dict for the delegate contract, or ``None``
            when no supported particle or legacy bounds metadata is present.
        """
        if raw_bounds_step_data is None:
            return None
        get_value = getattr(raw_bounds_step_data, "get", None)
        if not callable(get_value):
            return super()._normalize_bounds_step_data(raw_bounds_step_data)

        limits = raw_bounds_step_data.get("limits")
        if limits is None and any(
            raw_bounds_step_data.get(key) is not None
            for key in ("soft_min", "soft_max", "hard_min", "hard_max", "ui_step")
        ):
            # Particle panel can pass pre-normalized UI metadata.
            limits = {
                "soft": {
                    "minimum": raw_bounds_step_data.get("soft_min"),
                    "maximum": raw_bounds_step_data.get("soft_max"),
                },
                "hard": {
                    "minimum": raw_bounds_step_data.get("hard_min"),
                    "maximum": raw_bounds_step_data.get("hard_max"),
                },
                "step": raw_bounds_step_data.get("ui_step"),
            }
        if limits is None:
            return super()._normalize_bounds_step_data(raw_bounds_step_data)

        soft_block = limits.get("soft")
        hard_block = limits.get("hard")
        soft_min = soft_block.get("minimum") if soft_block else None
        soft_max = soft_block.get("maximum") if soft_block else None
        hard_min = hard_block.get("minimum") if hard_block else None
        hard_max = hard_block.get("maximum") if hard_block else None

        step = self.__extract_limits_step(limits)

        if soft_min is None and soft_max is None and hard_min is None and hard_max is None and step is None:
            return super()._normalize_bounds_step_data(raw_bounds_step_data)

        return {
            "soft_min": soft_min,
            "soft_max": soft_max,
            "hard_min": hard_min,
            "hard_max": hard_max,
            "step": step,
        }
