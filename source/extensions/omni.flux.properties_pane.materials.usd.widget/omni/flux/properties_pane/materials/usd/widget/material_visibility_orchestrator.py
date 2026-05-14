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

from omni.flux.property_widget_builder.model.usd import ConditionalVisibilityOrchestrator

_INPUT_PREFIX = "inputs:"
_OUTPUT_PREFIX = "outputs:"


class MaterialVisibilityOrchestrator(ConditionalVisibilityOrchestrator):
    """Material-specific orchestrator reading MDL enable-if metadata from placeholders."""

    def _normalize_attr_id(self, attr_id: str) -> str:
        """Normalize a material attribute identifier for condition matching.

        Args:
            attr_id: Raw material attribute identifier, optionally prefixed with ``inputs:`` or ``outputs:``.

        Returns:
            Input identifier without the ``inputs:`` prefix, or an empty string for empty/output identifiers.
        """
        if not attr_id:
            return ""
        if attr_id.startswith(_OUTPUT_PREFIX):
            return ""
        if attr_id.startswith(_INPUT_PREFIX):
            return attr_id[len(_INPUT_PREFIX) :]
        return attr_id

    def _get_attr_id(self, attribute_entry: Any) -> str | None:
        """Read and normalize the material input ID for an entry.

        Args:
            attribute_entry: Material visibility entry to inspect.

        Returns:
            Normalized input attribute ID, or ``None`` when the entry should not participate.
        """
        placeholder = attribute_entry.metadata_source
        raw_attr_id = placeholder.GetName() if placeholder is not None else attribute_entry.attr_id
        return self._normalize_attr_id(raw_attr_id) or None

    def _get_enable_if_condition(self, attribute_entry: Any) -> str | None:
        """Read the MDL enable-if condition from a material placeholder.

        Args:
            attribute_entry: Material visibility entry to inspect.

        Returns:
            Placeholder-provided enable-if condition, fallback entry condition, or ``None``.
        """
        placeholder = attribute_entry.metadata_source
        if placeholder is not None:
            return placeholder.GetEnableIfCondition()
        return super()._get_enable_if_condition(attribute_entry)
