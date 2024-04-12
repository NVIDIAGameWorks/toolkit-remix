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

import os

from lightspeed.common import constants
from pxr import Usd

from ..layer_types import LayerType
from .i_layer import ILayer


class CaptureLayer(ILayer):
    @property
    def layer_type(self) -> LayerType:
        return LayerType.capture

    def get_textures(self, texture_attribute):
        layer = self.get_sdf_layer()
        if not layer:
            return [], [], []
        capture_stage = Usd.Stage.Open(layer.realPath)
        collected_prim_paths = []
        collected_asset_absolute_paths = []
        collected_asset_relative_paths = []

        for prim in capture_stage.GetPrimAtPath(constants.ROOTNODE_LOOKS).GetChildren():
            if (
                not prim.GetChild(constants.SHADER)
                or not prim.GetChild(constants.SHADER).GetAttribute(texture_attribute)
                or not prim.GetChild(constants.SHADER).GetAttribute(texture_attribute).Get()
            ):
                continue
            absolute_asset_path = prim.GetChild(constants.SHADER).GetAttribute(texture_attribute).Get().resolvedPath
            rel_path = os.path.relpath(absolute_asset_path, os.path.dirname(layer.realPath))
            collected_prim_paths.append(prim.GetPath())
            collected_asset_absolute_paths.append(absolute_asset_path)
            collected_asset_relative_paths.append(rel_path)
        return collected_prim_paths, collected_asset_absolute_paths, collected_asset_relative_paths

    def get_textures_by_prim_paths(self, prim_paths, texture_attribute):
        layer = self.get_sdf_layer()
        capture_stage = Usd.Stage.Open(layer.realPath)
        collected_prim_paths = []
        collected_asset_absolute_paths = []
        collected_asset_relative_paths = []

        for prim_path in prim_paths:
            prim = capture_stage.GetPrimAtPath(prim_path)
            if (
                not prim.GetChild(constants.SHADER)
                or not prim.GetChild(constants.SHADER).GetAttribute(texture_attribute)
                or not prim.GetChild(constants.SHADER).GetAttribute(texture_attribute).Get()
            ):
                continue
            absolute_asset_path = prim.GetChild(constants.SHADER).GetAttribute(texture_attribute).Get().resolvedPath
            rel_path = os.path.relpath(absolute_asset_path, os.path.dirname(layer.realPath))
            collected_prim_paths.append(prim.GetPath())
            collected_asset_absolute_paths.append(absolute_asset_path)
            collected_asset_relative_paths.append(rel_path)
        return collected_asset_absolute_paths, collected_asset_relative_paths
