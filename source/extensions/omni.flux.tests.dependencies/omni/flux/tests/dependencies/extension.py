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
import carb.eventdispatcher
import omni.ext
from pxr import Ar

TEST_DEFERRED_DEPENDENCIES_SETTING = "/exts/omni.flux.tests.dependencies/deferred_dependencies"


class FluxTestDependenciesExtension(omni.ext.IExt):
    def on_startup(self, _):
        carb.log_info("[omni.flux.tests.dependencies] Flux Test Dependencies Extension startup")

        self._app_started_sub = carb.eventdispatcher.get_eventdispatcher().observe_event(
            observer_name="omni.flux.tests.dependencies create USD resolver",
            event_name=omni.kit.app.GLOBAL_EVENT_APP_STARTED,
            on_event=self._create_resolver,
        )

        settings = carb.settings.get_settings()

        # Once we've got the settings, load the deferred dependencies
        exts = settings.get(TEST_DEFERRED_DEPENDENCIES_SETTING) or []
        manager = omni.kit.app.get_app().get_extension_manager()

        for ext in exts:
            if manager.is_extension_enabled(ext):
                continue
            try:
                # "set_extension_enabled_immediate" mode was trying to load other extensions.
                manager.set_extension_enabled(ext, True)
            except Exception as e:  # noqa: BLE001
                carb.log_warn(f"Failed to enable deferred extension {ext}: {e}")

    def _create_resolver(self, _):
        # Create the USD asset resolver on the main thread before the first app update.
        # After app ready, omni.kit.material.library loads MDL modules on worker threads. If a worker creates the
        # resolver first, it imports Python modules and waits for the GIL. A main-thread USD call that holds the GIL
        # then waits for that resolver, and the test process deadlocks. The product apps avoid this because they
        # create the resolver during extension startup.
        # Not in on_startup: the HdRemix extension expects to be the first code that queries the USD plugin registry.
        # Not in an update task: a main-thread Ar.GetResolver() during the first update hung the validator window
        # test apps at startup (main thread waiting on carb.tasking, probably the same kind of deadlock).
        self._app_started_sub = None
        Ar.GetResolver()

    def on_shutdown(self):
        carb.log_info("[omni.flux.tests.dependencies] Flux Test Dependencies Extension shutdown")
        self._app_started_sub = None
