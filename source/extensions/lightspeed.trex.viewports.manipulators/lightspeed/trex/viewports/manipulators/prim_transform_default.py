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

from typing import Any

from .custom_manipulator.prim_transform_manipulator import PrimTransformManipulator as _PrimTransformManipulator
from .custom_manipulator.prim_transform_model import PrimTransformModel as _ManipulatorPrimTransformModel
from .interface.i_manipulator import IManipulator


class PrimTransformDefault(IManipulator):
    def _create_manipulator(self):
        manipulator_prim_transform_model = _ManipulatorPrimTransformModel(
            usd_context_name=self.viewport_api.usd_context_name
        )
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


def prim_transform_default_factory(desc: dict[str, Any]):
    manip = PrimTransformDefault(desc.get("viewport_api"))
    return manip
