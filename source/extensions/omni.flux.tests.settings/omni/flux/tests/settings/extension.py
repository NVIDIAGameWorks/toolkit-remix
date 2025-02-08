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


class FluxTestSettingsExtension(omni.ext.IExt):
    def on_startup(self, _):
        carb.log_info("[omni.flux.tests.settings] Flux Test Settings Extension startup")

        # Set default values for tests
        settings = carb.settings.get_settings()
        settings.set_default_bool("/app/fastShutdown", True)
        settings.set_default_bool("/app/file/ignoreUnsavedOnExit", True)
        settings.set_default_bool("/app/hangDetector/enabled", False)
        settings.set_default_bool("/app/extensions/registryEnabled", True)
        settings.set_default_bool("/rtx/verifyDriverVersion/enabled", False)
        settings.set_default_string("/exts/omni.services.transport.server.http/host", "127.0.0.1")
        settings.set_default_int("/exts/omni.services.transport.server.http/port", 8011)

    def on_shutdown(self):
        carb.log_info("[omni.flux.tests.settings] Flux Test Settings Extension shutdown")
