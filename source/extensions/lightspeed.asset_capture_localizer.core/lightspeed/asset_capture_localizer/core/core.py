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

import glob
import os
import re
from typing import List, Tuple

import omni.usd
from lightspeed.common.constants import CAPTURE_FILE_PREFIX, INSTANCE_PATH, MESHES_FILE_PREFIX
from lightspeed.layer_manager.core import LayerManagerCore, LayerType
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs
from pxr import Sdf, Usd


class AssetCaptureLocalizerCore:
    def __init__(self, context: omni.usd.UsdContext):
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

        self._context = context
        self._layer_manager = LayerManagerCore()

    def __traverse_instanced_children(self, prim):
        for child in prim.GetFilteredChildren(Usd.PrimAllPrimsPredicate):
            yield child
            yield from self.__traverse_instanced_children(child)

    def get_capture_usd_files(self):
        layer = self._layer_manager.get_layer(LayerType.capture)
        capture_usd_files = []
        if layer:
            # we generate a list of hashes from the list of mesh usd files
            capture_folder = os.path.dirname(layer.identifier)
            for capture_usd in glob.glob(os.path.join(capture_folder, "*.usd")):
                match = re.match(f"^{CAPTURE_FILE_PREFIX}(.*).usd$", os.path.basename(capture_usd))
                if match:
                    capture_usd_files.append(capture_usd)
        return capture_usd_files

    def get_capture_mesh_dict(self):
        capture_files = self.get_capture_usd_files()
        result = {}
        for layer_path in capture_files:
            sub_stage = Usd.Stage.Open(layer_path)
            all_prims = list(self.__traverse_instanced_children(sub_stage.GetPseudoRoot()))
            if not all_prims:
                continue
            for prim in all_prims:
                result[prim.GetName()] = layer_path
        return result

    def get_all_user_references(self) -> List[Tuple[Usd.Prim, Sdf.Reference, Sdf.Layer, str]]:
        stage = self._context.get_stage()
        result = []
        all_prims = list(self.__traverse_instanced_children(stage.GetPseudoRoot()))
        if not all_prims:
            return []
        capture_prims_dict = self.get_capture_mesh_dict()
        regex_pattern = re.compile("^.*\/([a-zA-Z]+)_([A-Z0-9]{16})(_[0-9]+)*$")  # noqa
        for prim in all_prims:
            if not regex_pattern.match(prim.GetPath().pathString):
                continue
            if INSTANCE_PATH in prim.GetPath().pathString:
                continue
            refs_and_layers = omni.usd.get_composed_references_from_prim(prim)
            capture_layer_path = "Not found"
            if refs_and_layers:
                for ref, layer in refs_and_layers:
                    if ref.assetPath:
                        match = re.match(f"^{MESHES_FILE_PREFIX}(.*).usd$", os.path.basename(ref.assetPath))
                        if match:
                            continue
                        if capture_prims_dict.get(prim.GetName()):
                            capture_layer_path = capture_prims_dict[prim.GetName()]
                        result.append((prim, ref, layer, capture_layer_path))
            else:
                if capture_prims_dict.get(prim.GetName()):
                    capture_layer_path = capture_prims_dict[prim.GetName()]
                result.append((prim, None, None, capture_layer_path))
        return result

    def destroy(self):
        _reset_default_attrs(self)
