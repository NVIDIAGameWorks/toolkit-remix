"""
* Copyright (c) 2022, NVIDIA CORPORATION.  All rights reserved.
*
* NVIDIA CORPORATION and its licensors retain all intellectual property
* and proprietary rights in and to this software, related documentation
* and any modifications thereto.  Any use, reproduction, disclosure or
* distribution of this software and related documentation without an express
* license agreement from NVIDIA CORPORATION is strictly prohibited.
"""
from typing import Any, Dict

from .custom_manipulator.prim_transform_manipulator import PrimTransformManipulator as _PrimTransformManipulator
from .custom_manipulator.prim_transform_model import PrimTransformModel as _ManipulatorPrimTransformModel
from .interface.i_manipulator import IManipulator


class PrimTransformDefault(IManipulator):
    def _create_manipulator(self):
        manipulator_prim_transform_model = _ManipulatorPrimTransformModel(self.viewport_api.usd_context_name)
        return _PrimTransformManipulator(
            usd_context_name=self.viewport_api.usd_context_name,
            viewport_api=self.viewport_api,
            model=manipulator_prim_transform_model,
        )

    def _model_changed(self, model, item):
        pass

    @property
    def categories(self):
        return ["manipulator"]

    @property
    def name(self):
        return "Prim Transform"

    @property
    def visible(self):
        return True

    @visible.setter
    def visible(self, value):
        pass


def prim_transform_default_factory(desc: Dict[str, Any]):
    manip = PrimTransformDefault(desc.get("viewport_api"))
    return manip
