"""
* SPDX-FileCopyrightText: Copyright (c) 2024 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["RemixAllMaterialsInteractionPlugin"]

from lightspeed.trex.utils.common.prim_utils import get_extended_selection
from omni.flux.stage_manager.plugin.interaction.usd import AllMaterialsInteractionPlugin
from pydantic import Field

from .base import RemixStageManagerUSDInteractionPlugin


class RemixAllMaterialsInteractionPlugin(AllMaterialsInteractionPlugin, RemixStageManagerUSDInteractionPlugin):
    """
    Remix extension of the Flux AllMaterialsInteractionPlugin.

    Adds ComfyUI event subscription, Remix-specific widgets/filters, and extended selection behavior.
    """

    compatible_filters: list[str] = Field(
        default=[
            *AllMaterialsInteractionPlugin.model_fields["compatible_filters"].default,
            # Remix filters
            "IsCaptureFilterPlugin",
        ],
        exclude=True,
    )

    compatible_widgets: list[str] = Field(
        default=[
            *AllMaterialsInteractionPlugin.model_fields["compatible_widgets"].default,
            # Remix widgets
            "AssignCategoryActionWidgetPlugin",
            "FocusInViewportActionWidgetPlugin",
            "IsCaptureStateWidgetPlugin",
            "IsCategoryHiddenStateWidgetPlugin",
            "NicknameToggleActionWidgetPlugin",
            "ParticleSystemsActionWidgetPlugin",
            "PrimRenameNameActionWidgetPlugin",
            "SubmitAIJobActionWidgetPlugin",
        ],
        exclude=True,
    )

    def _get_selection(self):
        return get_extended_selection(self._context_name)
