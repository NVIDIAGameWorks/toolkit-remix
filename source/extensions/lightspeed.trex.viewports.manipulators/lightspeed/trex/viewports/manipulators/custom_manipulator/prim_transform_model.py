"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import List

from omni.kit.manipulator.prim.model import PrimTransformModel as _PrimTransformModel


class PrimTransformModel(_PrimTransformModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
            self.__redirect_paths,
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
            self.__redirect_paths, new_translations, new_rotation_eulers, new_rotation_orders, new_scales
        )

    def _do_transform_all_selected_prims_to_manipulator_pivot(
        self, paths, new_translations, new_rotation_eulers, new_rotation_orders, new_scales
    ):
        super()._do_transform_all_selected_prims_to_manipulator_pivot(
            self.__redirect_paths, new_translations, new_rotation_eulers, new_rotation_orders, new_scales
        )
