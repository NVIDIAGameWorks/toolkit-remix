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

import types

import omni.kit.undo
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from omni.kit.manipulator.prim.core.model import PrimTransformModel as _PrimTransformModel


def on_ended_transform(self):
    """Ends the transform operation."""
    with omni.kit.undo.group():
        for tag, data in self._transform_data_map.items():
            self.get_data_accessor(tag).on_ended_transform(
                (
                    self._model.get_path_redirect()
                    if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
                    else data.paths
                ),
                [],
                data.new_translations,
                data.new_rotation_eulers,
                data.new_rotation_orders,
                data.new_scales,
                data.old_translations,
                data.old_rotation_eulers,
                data.old_rotation_orders,
                data.old_scales,
            )


def do_transform_selected_prims(self):
    for tag, data in self._transform_data_map.items():
        self.get_data_accessor(tag).do_transform_selected_prims(
            (
                self._model.get_path_redirect()
                if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
                else data.paths
            ),
            [],
            data.new_translations,
            data.new_rotation_eulers,
            data.new_rotation_orders,
            data.new_scales,
        )


def do_transform_all_selected_prims_to_manipulator_pivot(
    self,
    paths: list,
    new_translations: list[float],
    new_rotation_eulers: list[float],
    new_rotation_orders: list[int],
    new_scales: list[float],
):
    self.do_transform_all_selected_prims_to_manipulator_pivot_original(
        (
            self._model.get_path_redirect()
            if self._model.get_usd_context_name() == _TrexContexts.STAGE_CRAFT.value
            else paths
        ),
        new_translations,
        new_rotation_eulers,
        new_rotation_orders,
        new_scales,
    )


class PrimTransformModel(_PrimTransformModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__usd_context_name = kwargs["usd_context_name"]
        self.__redirect_paths = []

        self._data_accessor_selector.on_ended_transform = types.MethodType(
            on_ended_transform, self._data_accessor_selector
        )
        self._data_accessor_selector.do_transform_selected_prims = types.MethodType(
            do_transform_selected_prims, self._data_accessor_selector
        )
        self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot_original = (
            self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot
        )
        self._data_accessor_selector.do_transform_all_selected_prims_to_manipulator_pivot = types.MethodType(
            do_transform_all_selected_prims_to_manipulator_pivot, self._data_accessor_selector
        )

    def set_path_redirect(self, paths: list[str]):
        self.__redirect_paths = paths

    def get_path_redirect(self):
        return self.__redirect_paths

    def get_usd_context_name(self):
        return self.__usd_context_name
