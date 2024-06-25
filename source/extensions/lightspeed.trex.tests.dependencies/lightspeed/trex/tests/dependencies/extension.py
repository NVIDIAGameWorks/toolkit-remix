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

TEST_DEFERRED_DEPENDENCIES_SETTING = "/exts/lightspeed.trex.tests.dependencies/deferred_dependencies"


class LightspeedTestDependenciesExtension(omni.ext.IExt):
    def on_startup(self, _):
        carb.log_info("[lightspeed.trex.tests.dependencies] Lightspeed Test Dependencies Extension startup")

        # Set default values for tests
        settings = carb.settings.get_settings()

        # When importing `lightspeed.trex.app.resources`, we also need to set it as the default resource
        settings.set_default_string(
            "/exts/omni.flux.utils.widget/default_resources_ext", "lightspeed.trex.app.resources"
        )

        # Once we've set the settings, load the resources extensions
        exts = settings.get(TEST_DEFERRED_DEPENDENCIES_SETTING) or []
        manager = omni.kit.app.get_app().get_extension_manager()

        for ext in exts:
            if manager.is_extension_enabled(ext):
                continue
            manager.set_extension_enabled_immediate(ext, True)

    def on_shutdown(self):
        carb.log_info("[lightspeed.trex.tests.dependencies] Lightspeed Test Dependencies Extension shutdown")