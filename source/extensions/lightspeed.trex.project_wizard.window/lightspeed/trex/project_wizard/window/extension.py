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

from .setup_ui import ProjectWizardWindow

_INSTANCE = None


def get_instance(context_name: str = ""):
    """Expose the created instance of the project wizard"""
    global _INSTANCE
    if _INSTANCE is not None:
        _INSTANCE.destroy()

    _INSTANCE = ProjectWizardWindow(context_name=context_name)
    return _INSTANCE


class ProjectWizardWindowExtension(omni.ext.IExt):
    """Project Wizard Window global instance"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_attr = {}
        for attr, value in self.default_attr.items():
            setattr(self, attr, value)

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.project_wizard.window] Startup")

    def on_shutdown(self):
        global _INSTANCE
        carb.log_info("[lightspeed.trex.project_wizard.window] Shutdown")
        _reset_default_attrs(self)
        if _INSTANCE is not None:
            _INSTANCE.destroy()
        _INSTANCE = None
