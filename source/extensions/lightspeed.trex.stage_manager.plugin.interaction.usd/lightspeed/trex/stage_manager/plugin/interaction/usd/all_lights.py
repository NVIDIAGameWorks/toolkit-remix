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

__all__ = ["RemixAllLightsInteractionPlugin"]

from omni.flux.stage_manager.plugin.interaction.usd import AllLightsInteractionPlugin
from pydantic import Field

from .base import RemixStageManagerUSDInteractionPlugin


class RemixAllLightsInteractionPlugin(AllLightsInteractionPlugin, RemixStageManagerUSDInteractionPlugin):
    """
    Remix extension of the Flux AllLightsInteractionPlugin.

    Adds ComfyUI event subscription and Remix-specific widgets/filters to the base Flux interaction.
    """

    compatible_filters: list[str] = Field(
        default=[
            *AllLightsInteractionPlugin.model_fields["compatible_filters"].default,
            # Remix filters
            "IsCaptureFilterPlugin",
            "IsCategoryFilterPlugin",
        ],
        exclude=True,
    )

    compatible_widgets: list[str] = Field(
        default=[
            *AllLightsInteractionPlugin.model_fields["compatible_widgets"].default,
            # Remix widgets
            "AssignCategoryActionWidgetPlugin",
            "DeleteRestoreActionWidgetPlugin",
            "FocusInViewportActionWidgetPlugin",
            "IsCaptureStateWidgetPlugin",
            "IsCategoryHiddenStateWidgetPlugin",
            "NicknameToggleActionWidgetPlugin",
            "PrimRenameNameActionWidgetPlugin",
        ],
        exclude=True,
    )
