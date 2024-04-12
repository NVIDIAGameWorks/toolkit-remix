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
from typing import List

from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from omni.kit.manipulator.prim.model import PrimTransformModel as _PrimTransformModel


class PrimTransformModel(_PrimTransformModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__usd_context_name = kwargs["usd_context_name"]
        self.__redirect_paths = []

    def set_path_redirect(self, paths: List[str]):
        self.__redirect_paths = paths

    def _on_ended_transform(
        self,
        paths,
        new_translations,
        new_rotation_eulers,
        new_rotation_orders,
        new_scales,
        old_translations,
        old_rotation_eulers,
        old_rotation_orders,
        old_scales,
    ):
        super()._on_ended_transform(
            self.__redirect_paths if self.__usd_context_name == _TrexContexts.STAGE_CRAFT.value else paths,
            new_translations,
            new_rotation_eulers,
            new_rotation_orders,
            new_scales,
            old_translations,
            old_rotation_eulers,
            old_rotation_orders,
            old_scales,
        )
        # self.__redirect_paths = []

    def _do_transform_selected_prims(
        self, paths, new_translations, new_rotation_eulers, new_rotation_orders, new_scales
    ):
        super()._do_transform_selected_prims(
            self.__redirect_paths if self.__usd_context_name == _TrexContexts.STAGE_CRAFT.value else paths,
            new_translations,
            new_rotation_eulers,
            new_rotation_orders,
            new_scales,
        )

    def _do_transform_all_selected_prims_to_manipulator_pivot(
        self, paths, new_translations, new_rotation_eulers, new_rotation_orders, new_scales
    ):
        super()._do_transform_all_selected_prims_to_manipulator_pivot(
            self.__redirect_paths if self.__usd_context_name == _TrexContexts.STAGE_CRAFT.value else paths,
            new_translations,
            new_rotation_eulers,
            new_rotation_orders,
            new_scales,
        )
