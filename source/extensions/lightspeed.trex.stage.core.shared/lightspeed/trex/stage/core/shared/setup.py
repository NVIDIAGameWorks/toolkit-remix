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

from typing import Callable

import omni.kit.undo
import omni.kit.window.file
import omni.usd
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs


class Setup:
    def __init__(self, context_name: str):
        self._default_attr = {}
        for attr, value in self._default_attr.items():
            setattr(self, attr, value)

    def undo(self):
        omni.kit.undo.undo()

    def redo(self):
        omni.kit.undo.redo()

    def save(self, on_save_done: Callable[[bool, str], None] = None):
        omni.kit.window.file.save(on_save_done=on_save_done)

    def save_as(self, on_save_done: Callable[[bool, str], None] = None):
        omni.kit.window.file.save_as(False, on_save_done=on_save_done)

    def destroy(self):
        _reset_default_attrs(self)
