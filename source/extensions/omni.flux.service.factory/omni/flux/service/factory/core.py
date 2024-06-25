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

import typing
from typing import Dict, List, Optional, Type

if typing.TYPE_CHECKING:
    from .services.base import ServiceBase as _ServiceBase


class TrexServiceFactoryCore:
    def __init__(self):
        self._services = {}

    def is_service_registered(self, name: str) -> bool:
        """
        Check if the service is registered into the factory

        Args:
            name: the name of the service to check

        Returns:
            True if registered, else False
        """
        if name not in self._services:
            return False
        return True

    def get_service_from_name(self, service_name: str) -> Optional[Type["_ServiceBase"]]:
        """
        Get the service from its name

        Args:
            service_name: the name of the service to get

        Returns:
            The service
        """
        return self._services.get(service_name, None)

    def get_all_services(self) -> Dict[str, "_ServiceBase"]:
        """Return all registered services"""
        return self._services

    def register_services(self, services: List[Type["_ServiceBase"]]):
        """
        Register a service into the factory

        Args:
            services: the list of services to register
        """
        for service in services:
            self._services[service.name] = service

    def unregister_services(self, services: List[Type["_ServiceBase"]]):
        """
        Unregister a service into the factory

        Args:
            services: the list of services to unregister
        """
        for service in services:
            if service.name in self._services:
                del self._services[service.name]

    def destroy(self):
        self._services = {}
