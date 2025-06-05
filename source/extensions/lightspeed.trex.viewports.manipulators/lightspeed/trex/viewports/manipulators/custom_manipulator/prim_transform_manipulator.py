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

from typing import List, Optional

from lightspeed.trex.asset_replacements.core.shared import Setup as _AssetReplacementsCore
from lightspeed.trex.contexts.setup import Contexts as _TrexContexts
from omni.kit.manipulator.prim.core.prim_transform_manipulator import (
    PrimTransformManipulator as _PrimTransformManipulator,
)
from pxr import Sdf, Usd


class PrimTransformManipulator(_PrimTransformManipulator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.__context_name = kwargs["usd_context_name"]
        self._core = _AssetReplacementsCore(self.__context_name)

    def destroy(self):
        if self._core:
            self._core.destroy()
            self._core = None
        super().destroy()

    def on_selection_changed(self, stage: Usd.Stage, selection: Optional[List[Sdf.Path]], *args, **kwargs) -> bool:
        """
        Be default when the user click, it can't move anything. It will need to click on the reference on the
        selection panel to enable the manipulator
        """
        base_result = super().on_selection_changed(stage, selection, *args, **kwargs)
        if self.__context_name == _TrexContexts.STAGE_CRAFT.value:
            transformable = self._core.filter_transformable_prims(selection)
            self._model.set_path_redirect(transformable)
            return bool(transformable)
        return base_result
