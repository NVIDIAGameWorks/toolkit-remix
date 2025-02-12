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

from .setup_ui import WIZARD_MAP as _WIZARD_MAP
from .setup_ui import ProjectWizardBase as _ProjectWizardBase
from .setup_ui import WizardTypes as _WizardTypes

_INSTANCE: _ProjectWizardBase | None = None


def get_instance(
    wizard_type: _WizardTypes, context_name: str = "", width: int = 650, height: int = 400
) -> _ProjectWizardBase:
    """Expose the created instance of the project wizard"""
    global _INSTANCE

    if _INSTANCE is not None:
        _INSTANCE.destroy()

    _INSTANCE = _WIZARD_MAP[wizard_type](context_name=context_name, width=width, height=height)
    return _INSTANCE


class ProjectWizardWindowExtension(omni.ext.IExt):
    """Project Wizard Window global instance"""

    def on_startup(self, ext_id):
        carb.log_info("[lightspeed.trex.project_wizard.window] Startup")

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.project_wizard.window] Shutdown")

        global _INSTANCE
        if _INSTANCE is not None:
            _INSTANCE.destroy()
        _INSTANCE = None
