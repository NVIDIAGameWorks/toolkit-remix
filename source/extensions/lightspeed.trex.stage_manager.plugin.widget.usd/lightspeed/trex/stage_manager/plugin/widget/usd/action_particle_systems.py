"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ["ParticleSystemsActionWidgetPlugin"]

from typing import TYPE_CHECKING

import carb
import omni.kit.commands
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME as _PARTICLE_SCHEMA_NAME
from lightspeed.trex.utils.common.prim_utils import get_prototype as _get_prototype
from lightspeed.trex.utils.common.prim_utils import is_a_prototype as _is_a_prototype
from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


class ParticleSystemsActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to create or remove Particle Systems"""

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        # TODO: Build a UI for the particle systems
        return

    def build_overview_ui(self, model: StageManagerTreeModel):
        pass

    @classmethod
    def _get_menu_items(cls):
        particle_icon_path = _get_icons("particle")
        plus_icon_path = _get_icons("add")
        minus_icon_path = _get_icons("subtract")

        return [
            (
                {
                    "name": {
                        _MenuItem.PARTICLE_SYSTEM.value: [
                            {
                                "name": _MenuItem.PARTICLE_SYSTEM_ADD.value,
                                "glyph": plus_icon_path,
                                "onclick_fn": cls._create_particle_system,
                                "show_fn": cls._modify_particle_system_show_fn,
                                # Enable if no particle system exists only
                                "enabled_fn": lambda payload: not cls._has_particle_system(payload),
                            },
                            {
                                "name": _MenuItem.PARTICLE_SYSTEM_REMOVE.value,
                                "glyph": minus_icon_path,
                                "onclick_fn": cls._remove_particle_system,
                                "show_fn": cls._modify_particle_system_show_fn,
                                # Enable if a particle system exists only
                                "enabled_fn": cls._has_particle_system,
                            },
                        ],
                    },
                    "glyph": particle_icon_path,
                    "appear_after": _MenuItem.ASSIGN_CATEGORY.value,
                },
                _MenuGroup.SELECTED_PRIMS.value,
                "",
            )
        ]

    @classmethod
    def _modify_particle_system_show_fn(cls, payload: dict) -> bool:
        if "right_clicked_item" not in payload:
            return False

        prim = payload["right_clicked_item"].data
        if not prim or not prim.IsValid():
            return False

        # Check if the prim or any of its ancestors is under mesh or instance paths
        current_prim = prim
        while current_prim and current_prim.IsValid():
            if _is_a_prototype(current_prim) or _is_instance(current_prim):
                return True
            current_prim = current_prim.GetParent()

        return False

    @classmethod
    def _has_particle_system(cls, payload: dict) -> bool:
        if "right_clicked_item" not in payload:
            return False

        prim = payload["right_clicked_item"].data
        if not prim or not prim.IsValid():
            return False

        return prim.HasAPI(_PARTICLE_SCHEMA_NAME)

    @classmethod
    def _create_particle_system(cls, payload: dict):
        if "right_clicked_item" not in payload:
            carb.log_warn("Particle Systems Context Menu didn't receive the right clicked item. Returning...")
            return

        if cls._has_particle_system(payload):
            carb.log_warn("The prim already has a particle system. Returning...")
            return

        omni.kit.commands.execute(
            "CreateParticleSystemCommand", prim=_get_prototype(payload["right_clicked_item"].data)
        )

    @classmethod
    def _remove_particle_system(cls, payload: dict):
        if "right_clicked_item" not in payload:
            carb.log_warn("Particle Systems Context Menu didn't receive the right clicked item. Returning...")
            return

        if not cls._has_particle_system(payload):
            carb.log_warn("The prim doesn't have a particle system. Returning...")
            return

        omni.kit.commands.execute(
            "RemoveParticleSystemCommand", prim=_get_prototype(payload["right_clicked_item"].data)
        )
