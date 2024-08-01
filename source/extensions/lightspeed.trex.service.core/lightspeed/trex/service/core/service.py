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

__all__ = ["CoreService"]

import carb
from fast_version import init_fastapi_versioning
from omni.flux.service.factory import get_instance as _get_service_factory_instance
from omni.services.core import main


class CoreService:
    NAME = "name"
    CONTEXT_NAME = "context"
    TITLE = "title"
    DESCRIPTION = "description"

    def __init__(self):
        services = carb.settings.get_settings_interface().get("exts/lightspeed.trex.service.core/services") or []
        header = (
            carb.settings.get_settings_interface().get("exts/lightspeed.trex.service.core/header")
            or "application/lightspeed.remix.service+json"
        )

        # Get the desired services from the factory
        factory = _get_service_factory_instance()

        self._service_instances = []
        for service in services:
            service_instance = factory.get_plugin_from_name(service.get(self.NAME))(
                context_name=service.get(self.CONTEXT_NAME)
            )
            self._service_instances.append(service_instance)

            main.register_router(
                router=service_instance.router, prefix=service_instance.prefix, tags=[service.get(self.TITLE)]
            )

            if not main.get_app().openapi_tags:
                main.get_app().openapi_tags = []
            main.get_app().openapi_tags.append(
                {"name": service.get(self.TITLE), "description": service.get(self.DESCRIPTION)}
            )

        # Initialize FastAPI endpoint versioning
        init_fastapi_versioning(app=main.get_app(), vendor_media_type=header)

    def destroy(self):
        for service_instance in self._service_instances:
            main.deregister_router(router=service_instance.router)
        self._service_instances = None
