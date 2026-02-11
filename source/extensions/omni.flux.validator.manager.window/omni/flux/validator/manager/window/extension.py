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
from omni.flux.validator.manager.widget import SCHEMA_PATH_SETTING as _SCHEMA_PATH_SETTING

from .setup_ui import ValidatorManagerWindow as _ValidatorManagerWindow


class FluxValidatorWindowExtension(omni.ext.IExt):
    """Create Final Configuration"""

    def on_startup(self, ext_id):
        carb.log_info("[omni.flux.validator.manager.window] Startup")
        example = f"""
        If you use the standalone app, here an example:

            bin/omni.flux.app.validator.bat --enable omni.flux.validator.plugin.check.usd --enable omni.flux.validator.plugin.context.usd_stage --enable omni.flux.validator.plugin.selector.usd --{_SCHEMA_PATH_SETTING}="your_schema.json"
        """
        print(example)
        self._window = _ValidatorManagerWindow()

    def on_shutdown(self):
        carb.log_info("[omni.flux.validator.manager.window] Shutdown")
        if self._window:
            self._window.destroy()
