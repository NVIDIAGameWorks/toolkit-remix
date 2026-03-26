"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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


Flux Curve Editor Extension.

A general-purpose curve editor that works with CurveModel interface,
independent of any animation system.
"""

import omni.ext
import omni.kit.commands

from .model import commands

__all__ = ["CurveEditorExtension"]


class CurveEditorExtension(omni.ext.IExt):
    """
    Flux Curve Editor extension.

    The curve editor uses a CurveModel interface for data storage.
    Create a CurveEditorWidget with a CurveModel to use the editor.
    """

    def on_startup(self, ext_id) -> None:
        """Initialize the curve editor extension."""
        omni.kit.commands.register_all_commands_in_module(commands)

    def on_shutdown(self) -> None:
        """Clean up the curve editor extension."""
        omni.kit.commands.unregister_module_commands(commands)
