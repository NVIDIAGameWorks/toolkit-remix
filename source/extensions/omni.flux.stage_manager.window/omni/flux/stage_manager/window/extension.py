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
import carb.settings
import omni.ext

from .window import StageManagerManagerWindow as _StageManagerManagerWindow


class FluxStageManagerWindowExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def __init__(self):
        super().__init__()
        self._window = None

    def on_startup(self, ext_id):
        carb.log_info("[omni.flux.stage_manager.window] Startup")
        self._window = _StageManagerManagerWindow()

    def on_shutdown(self):
        carb.log_info("[omni.flux.stage_manager.window] Shutdown")
        if self._window:
            self._window.destroy()
