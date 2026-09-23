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

from __future__ import annotations

__all__ = ["CoreService"]

import carb
from fast_version import init_fastapi_versioning
from omni.flux.factory.base import FactoryBase
from omni.flux.service.factory import ServiceBase
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
        for service, service_instance in self._instantiate_services(factory, services):
            self._service_instances.append(service_instance)

            main.register_router(
                router=service_instance.router, prefix=service_instance.prefix, tags=[service.get(self.TITLE)]
            )

            if not main.get_app().openapi_tags:
                main.get_app().openapi_tags = []
            main.get_app().openapi_tags.append(
                {
                    "name": service.get(self.TITLE),
                    "description": service.get(self.DESCRIPTION),
                }
            )

        # Initialize FastAPI endpoint versioning
        init_fastapi_versioning(app=main.get_app(), vendor_media_type=header)

    def destroy(self):
        for service_instance in self._service_instances:
            main.deregister_router(router=service_instance.router)
        self._service_instances = None

    @classmethod
    def _instantiate_services(
        cls, factory: FactoryBase[ServiceBase], services: list[dict]
    ) -> list[tuple[dict, ServiceBase]]:
        """Instantiate every configured service the factory knows about.

        Args:
            factory: The service factory holding the registered service classes.
            services: The raw entries from the `services` setting.

        Returns:
            One `(setting entry, service instance)` pair per service that resolved, in
            configuration order.
        """
        resolved = []
        for service in services:
            name = service.get(cls.NAME)
            service_class = factory.get_plugin_from_name(name)
            if service_class is None:
                # Skipping beats instantiating the `None` the factory returns, which would take the
                # extension down with every service that did resolve. At error because nothing in
                # `services` is gated today: a silent skip serves an empty REST surface, healthily.
                carb.log_error(f"Service '{name}' is configured but not registered with the factory; skipping it.")
                continue
            resolved.append((service, service_class(context_name=service.get(cls.CONTEXT_NAME))))
        return resolved
