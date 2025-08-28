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

from functools import partial
from typing import TYPE_CHECKING, Callable

import omni.kit.commands
from lightspeed.common.constants import PARTICLE_SCHEMA_NAME as _PARTICLE_SCHEMA_NAME
from lightspeed.trex.utils.common.prim_utils import get_prototype as _get_prototype
from lightspeed.trex.utils.common.prim_utils import is_a_prototype as _is_a_prototype
from lightspeed.trex.utils.common.prim_utils import is_instance as _is_instance
from lightspeed.trex.utils.common.prim_utils import is_material_prototype as _is_material_prototype
from omni import ui
from omni.flux.stage_manager.factory.plugins import StageManagerMenuMixin as _StageManagerMenuMixin
from omni.flux.stage_manager.plugin.widget.usd.base import (
    StageManagerStateWidgetPlugin as _StageManagerStateWidgetPlugin,
)
from omni.flux.utils.common.menus import MenuGroup as _MenuGroup
from omni.flux.utils.common.menus import MenuItem as _MenuItem
from omni.flux.utils.widget.resources import get_icons as _get_icons
from pxr import UsdGeom

if TYPE_CHECKING:
    from omni.flux.stage_manager.factory.plugins.tree_plugin import StageManagerTreeItem, StageManagerTreeModel


class ParticleSystemsActionWidgetPlugin(_StageManagerStateWidgetPlugin, _StageManagerMenuMixin):
    """Action to create or remove Particle Systems"""

    def build_icon_ui(self, model: StageManagerTreeModel, item: StageManagerTreeItem, level: int, expanded: bool):
        if not item.data:
            ui.Spacer(width=self._icon_size, height=self._icon_size)
            return

        payload = {"context_name": self._context_name, "selected_paths": [item.data.GetPrimPath()]}
        enabled = self._modify_particle_system_show_fn(payload)
        has_particle_system = self._has_particle_system(payload)

        if enabled:
            icon = "DeleteParticle" if has_particle_system else "Particle"
            tooltip = "Remove the Particle System" if has_particle_system else "Create a Particle System"
            callback = (
                partial(self._build_callback, payload, self._remove_particle_system)
                if has_particle_system
                else partial(self._build_callback, payload, self._create_particle_system)
            )
        else:
            icon = "ParticleDisabled"
            tooltip = (
                "Select a material prim or mesh prim to create a particle system.\n\n"
                "NOTE: Instance prims are also supported but the particle system will be created on the associated "
                "mesh prim."
            )
            callback = None

        ui.Image(
            "",
            width=self._icon_size,
            height=self._icon_size - 3,  # Particle icons appear larger than the other icons
            name=icon,
            tooltip=tooltip,
            mouse_released_fn=callback,
        )

    def build_overview_ui(self, model: StageManagerTreeModel):
        pass

    def _build_callback(self, payload: dict, callback: Callable, x: int, y: int, button: int, modifiers: int):
        if button != 0 or not self._modify_particle_system_show_fn(payload):
            return
        callback(payload)

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
        if "selected_paths" not in payload or "context_name" not in payload:
            return False

        stage = omni.usd.get_context(payload["context_name"]).get_stage()
        if not stage:
            return False

        prims = [
            prim
            for path in payload["selected_paths"]
            if (prim := _get_prototype(stage.GetPrimAtPath(path))) and prim.IsValid()
        ]
        if not prims:
            return False

        # Check if the prims or any of their ancestors are material paths, or under mesh or instance paths
        for prim in prims:
            if _is_material_prototype(prim):
                return True

            current_prim = prim
            while current_prim and current_prim.IsValid():
                if _is_a_prototype(current_prim) or _is_instance(current_prim):
                    return prim.IsA(UsdGeom.Mesh)  # The selected prim itself must be a mesh
                current_prim = current_prim.GetParent()

        return False

    @classmethod
    def _has_particle_system(cls, payload: dict) -> bool:
        if "selected_paths" not in payload or "context_name" not in payload:
            return False

        stage = omni.usd.get_context(payload["context_name"]).get_stage()
        if not stage:
            return False

        prims = [
            prim
            for path in payload["selected_paths"]
            if (prim := _get_prototype(stage.GetPrimAtPath(path))) and prim.IsValid()
        ]
        if not prims:
            return False

        return any(prim.HasAPI(_PARTICLE_SCHEMA_NAME) for prim in prims)

    @classmethod
    def _create_particle_system(cls, payload: dict):
        if (
            "selected_paths" not in payload
            or "context_name" not in payload
            or not cls._modify_particle_system_show_fn(payload)
        ):
            return

        stage = omni.usd.get_context(payload["context_name"]).get_stage()
        if not stage:
            return

        if cls._has_particle_system(payload):
            return

        with omni.kit.undo.group():
            for path in payload["selected_paths"]:
                omni.kit.commands.execute("CreateParticleSystemCommand", prim=_get_prototype(stage.GetPrimAtPath(path)))

    @classmethod
    def _remove_particle_system(cls, payload: dict):
        if (
            "selected_paths" not in payload
            or "context_name" not in payload
            or not cls._modify_particle_system_show_fn(payload)
        ):
            return

        stage = omni.usd.get_context(payload["context_name"]).get_stage()
        if not stage:
            return

        if not cls._has_particle_system(payload):
            return

        with omni.kit.undo.group():
            for path in payload["selected_paths"]:
                omni.kit.commands.execute("RemoveParticleSystemCommand", prim=_get_prototype(stage.GetPrimAtPath(path)))
