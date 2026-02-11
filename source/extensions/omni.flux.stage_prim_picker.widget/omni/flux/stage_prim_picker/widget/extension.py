"""
* SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("StagePrimPickerExtension", "get_instance")

import carb
import omni.ext

_INSTANCE = None


def get_instance():
    """Get the current instance of the extension."""
    return _INSTANCE


class StagePrimPickerExtension(omni.ext.IExt):
    """Extension for Stage Prim Picker Widget"""

    def on_startup(self, ext_id):
        """Called when the extension is starting up."""
        global _INSTANCE
        carb.log_info("[omni.flux.stage_prim_picker.widget] Extension startup")
        _INSTANCE = self

    def on_shutdown(self):
        """Called when the extension is shutting down."""
        global _INSTANCE
        carb.log_info("[omni.flux.stage_prim_picker.widget] Extension shutdown")
        _INSTANCE = None
