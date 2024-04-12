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
import omni.usd
from pxr import Usd


class ReferenceEdit:
    """Utility class to allow editing the source USD of a referenced object.
    The source USD will be saved when the `with` block exits.

    Args:
        prim (Usd.Prim): The highest level prim being edited

    Example:
        >>> with ReferenceEdit(stage, prim):
        >>>     # edit prim, including any descendents of the prim.
    """

    def __init__(self, prim):
        self._prim = prim
        self._stage = omni.usd.get_context().get_stage()
        self._default_edit_target = self._stage.GetEditTarget()
        self._refNode = None

    def __enter__(self):
        if self._prim.GetPrimIndex().rootNode.children:
            self._refNode = self._prim.GetPrimIndex().rootNode.children[0]
            # if a prim's nested under several references, chase it all the way to the bottom.
            while self._refNode.children:
                self._refNode = self._refNode.children[0]

            self._stage.SetEditTarget(Usd.EditTarget(self._refNode.layerStack.layers[0], self._refNode))
        else:
            self._stage.SetEditTarget(self._default_edit_target)

    def __exit__(self, e_type, value, traceback):
        if self._refNode:
            self._refNode.layerStack.layers[0].Save()
        self._stage.SetEditTarget(self._default_edit_target)
