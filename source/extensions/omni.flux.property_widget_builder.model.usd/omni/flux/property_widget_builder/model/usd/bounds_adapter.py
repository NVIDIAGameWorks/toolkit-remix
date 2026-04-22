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

from typing import Any, TypedDict, TypeAlias

from omni.flux.property_widget_builder.delegates.base import BoundsValue, RealNumber

RawBoundsStepData: TypeAlias = dict[str, Any] | Any


class NormalizedBoundsStepData(TypedDict):
    """Strict normalized payload contract for bounds adapters."""

    soft_min: BoundsValue | None
    soft_max: BoundsValue | None
    hard_min: BoundsValue | None
    hard_max: BoundsValue | None
    step: BoundsValue | None


class BoundsAdapter:
    """Base bounds adapter that normalizes raw bounds metadata once.

    Normalized values may be scalar (int/float) or scalar sequences; consumers
    that render per-channel drag widgets resolve sequence components later.
    """

    def __init__(
        self,
        raw_bounds_step_data: RawBoundsStepData | None = None,
        normalized_data: NormalizedBoundsStepData | None = None,
    ):
        """Initialize and cache normalized bounds/step data.

        Args:
            raw_bounds_step_data: Raw metadata payload from a producer (panel,
                USD customData mapping, or pre-built dict). Subclasses interpret
                and normalize this payload in ``_normalize_bounds_step_data``.
            normalized_data: Optional pre-normalized bounds payload. When
                provided, normalization is skipped and cached values are applied
                directly. If both arguments are provided, ``normalized_data``
                takes precedence.
        """
        normalized = normalized_data
        if normalized is None:
            normalized = self._normalize_bounds_step_data(raw_bounds_step_data)
        normalized = normalized or NormalizedBoundsStepData(
            soft_min=None,
            soft_max=None,
            hard_min=None,
            hard_max=None,
            step=None,
        )
        self._soft_min = normalized["soft_min"]
        self._soft_max = normalized["soft_max"]
        self._hard_min = normalized["hard_min"]
        self._hard_max = normalized["hard_max"]
        self._step = normalized["step"]

    @classmethod
    def merge_bounds_adapters(cls, adapters: list[BoundsAdapter]) -> BoundsAdapter:
        """Merge multiple adapters into one adapter instance.

        This method is intentionally post-normalization so pane producers can
        reuse one merge policy regardless of original metadata source.

        Merge policy is as follows. A single adapter input passes through
        unchanged. Multi-adapter inputs intersect numeric min/max values across
        payloads. Step values use the coarsest numeric step encountered.
        The soft channel is emitted only when all adapters provide soft bounds,
        or when the selection is mixed (soft and hard both present). The hard
        channel is emitted only when all adapters provide hard bounds, or when
        the selection is mixed (soft and hard both present). A channel is left
        unset when no selected adapter provides it.

        Additional behavior: single-item input returns the same adapter
        instance (alias) instead of constructing a new one. Callers should not
        assume a new object identity from merge and should avoid mutating
        adapter internals after merge. When the intersected runtime-safe range
        is empty, merged bounds are cleared on both channels and only the
        merged step is preserved.
        """
        if not adapters:
            return cls(normalized_data=None)
        if len(adapters) == 1:
            return adapters[0]

        effective_min_candidates: list[RealNumber] = []
        effective_max_candidates: list[RealNumber] = []
        step_candidates: list[RealNumber] = []
        soft_presence: list[bool] = []
        hard_presence: list[bool] = []

        for adapter in adapters:
            bounds_tuple = adapter.bounds
            effective_min = effective_max = hard_min = hard_max = None
            if bounds_tuple is not None:
                effective_min, effective_max, hard_min, hard_max = bounds_tuple
            if isinstance(effective_min, RealNumber):
                effective_min_candidates.append(effective_min)

            if isinstance(effective_max, RealNumber):
                effective_max_candidates.append(effective_max)

            step_value = adapter.step
            if isinstance(step_value, RealNumber):
                step_candidates.append(step_value)

            soft_presence.append(adapter.has_soft_bounds)
            hard_presence.append(adapter.has_hard_bounds)

        merged_effective_min = max(effective_min_candidates) if effective_min_candidates else None
        merged_effective_max = min(effective_max_candidates) if effective_max_candidates else None
        merged_step = max(step_candidates) if step_candidates else None

        # No shared runtime-safe overlap: expose no merged bounds.
        if (
            merged_effective_min is not None
            and merged_effective_max is not None
            and merged_effective_min > merged_effective_max
        ):
            return cls(
                normalized_data=NormalizedBoundsStepData(
                    soft_min=None,
                    soft_max=None,
                    hard_min=None,
                    hard_max=None,
                    step=merged_step,
                )
            )

        any_soft = any(soft_presence)
        all_soft = all(soft_presence)
        any_hard = any(hard_presence)
        all_hard = all(hard_presence)
        mixed_state = any_soft and any_hard

        set_soft = any_soft and (all_soft or mixed_state)
        set_hard = any_hard and (all_hard or mixed_state)

        merged_soft_min = merged_effective_min if set_soft else None
        merged_soft_max = merged_effective_max if set_soft else None
        merged_hard_min = merged_effective_min if set_hard else None
        merged_hard_max = merged_effective_max if set_hard else None

        if (
            merged_soft_min is None
            and merged_soft_max is None
            and merged_hard_min is None
            and merged_hard_max is None
            and merged_step is None
        ):
            return cls(normalized_data=None)
        return cls(
            normalized_data=NormalizedBoundsStepData(
                soft_min=merged_soft_min,
                soft_max=merged_soft_max,
                hard_min=merged_hard_min,
                hard_max=merged_hard_max,
                step=merged_step,
            )
        )

    def _normalize_bounds_step_data(
        self, raw_bounds_step_data: RawBoundsStepData | None
    ) -> NormalizedBoundsStepData | None:
        """Normalize legacy metadata to common bounds+step structure.

        Legacy behavior:
        - `range.min` / `range.max` -> soft bounds
        - `ui:step` -> step
        - hard bounds remain unset

        Args:
            raw_bounds_step_data: Raw metadata payload expected to be dict-like
                for the base legacy contract.

        Returns:
            Normalized dict with ``soft_min``, ``soft_max``, ``hard_min``,
            ``hard_max``, and ``step`` keys, or ``None`` when payload does not
            contain usable legacy bounds metadata.
        """
        if not isinstance(raw_bounds_step_data, dict):
            return None
        step_value = raw_bounds_step_data.get("ui:step")
        min_max_range = raw_bounds_step_data.get("range")
        soft_min = None
        soft_max = None
        if isinstance(min_max_range, dict):
            soft_min = min_max_range.get("min")
            soft_max = min_max_range.get("max")

        if soft_min is None and soft_max is None and step_value is None:
            return None
        return NormalizedBoundsStepData(
            soft_min=soft_min,
            soft_max=soft_max,
            hard_min=None,
            hard_max=None,
            step=step_value,
        )

    @property
    def has_soft_bounds(self) -> bool:
        """Return whether this adapter has any source soft-bound value."""
        return self._soft_min is not None or self._soft_max is not None

    @property
    def has_hard_bounds(self) -> bool:
        """Return whether this adapter has any source hard-bound value."""
        return self._hard_min is not None or self._hard_max is not None

    @property
    def step(self) -> BoundsValue | None:
        """Return the normalized step value, if present."""
        return self._step

    @property
    def bounds(self) -> tuple[BoundsValue | None, BoundsValue | None, BoundsValue | None, BoundsValue | None] | None:
        """Return normalized ``(min, max, hard_min, hard_max)`` tuple.

        ``min``/``max`` prefer soft bounds and fall back to hard bounds when
        soft bounds are absent.
        """
        min_val = self._soft_min if self._soft_min is not None else self._hard_min
        max_val = self._soft_max if self._soft_max is not None else self._hard_max
        if min_val is None and max_val is None:
            return None
        return min_val, max_val, self._hard_min, self._hard_max
