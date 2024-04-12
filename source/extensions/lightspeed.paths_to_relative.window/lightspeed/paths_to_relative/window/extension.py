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
import carb
import omni.ext
from omni.flux.utils.common import reset_default_attrs as _reset_default_attrs

from .setup_ui import PathsToRelativeWindow

_INSTANCE = None


def get_instance():
    """Expose the created instance of the tool"""
    return _INSTANCE


class PathsToRelativesExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        global _INSTANCE
        carb.log_info("[lightspeed.paths_to_relative.window] startup")
        _INSTANCE = PathsToRelativeWindow()

    def on_shutdown(self):
        global _INSTANCE
        _reset_default_attrs(self)
        _INSTANCE.destroy()
        _INSTANCE = None
