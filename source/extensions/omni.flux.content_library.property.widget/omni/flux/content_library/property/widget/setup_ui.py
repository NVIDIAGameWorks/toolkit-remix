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

import omni.ui as ui

from .delegate import Delegate as _DelegateMetadata
from .model import Model as _ModelMetadata


class ContentLibraryPropertyWidget:
    def __init__(self, model: Optional[_ModelMetadata] = None, delegate: Optional[_DelegateMetadata] = None):
        """
        Tree property

        Args:
            model: the model of the tree metadata
            delegate: the delegate of the tree metadata
        """
        self._model = _ModelMetadata() if model is None else model
        self._delegate = _DelegateMetadata() if delegate is None else delegate

    @property
    def model(self):
        """Return the current model"""
        return self._model

    def create_ui(self, column_widths: List[ui.Length] = None):
        """
        Create the UI

        Args:
            column_widths: the width of each column (by default there is only 2 columns)
        """
        with ui.Frame():
            ui.TreeView(
                self._model,
                delegate=self._delegate,
                root_visible=False,
                header_visible=False,
                column_widths=[ui.Pixel(160)] if column_widths is None else column_widths,
                name="ContentLibraryChoose",
            )

    def destroy(self):
        if self._model:
            self._model.destroy()
        self._model = None
        if self._delegate:
            self._delegate.destroy()
        self._delegate = None
