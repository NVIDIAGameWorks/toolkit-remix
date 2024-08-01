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

__all__ = ["IngestCraftService"]

import carb
from lightspeed.common.constants import INGESTION_SCHEMAS
from omni.flux.service.factory import ServiceBase
from omni.flux.service.factory import get_instance as _get_service_factory_instance
from omni.flux.validator.manager.core import EXTS_MASS_VALIDATOR_SERVICE_PREFIX


class IngestCraftService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that group up all the functionality exposed in IngestCraft in a RestAPI.

        Args:
            context_name: The USD context name
        """

        super().__init__()

        # Update the settings to set the MassValidatorService prefix
        carb.settings.get_settings().set(EXTS_MASS_VALIDATOR_SERVICE_PREFIX, self.prefix)

        # Get the desired services from the factory
        factory = _get_service_factory_instance()

        mass_queue = factory.get_plugin_from_name("MassValidatorService")(INGESTION_SCHEMAS)

        # Include the desired services in the app-level service
        self.router.include_router(mass_queue.router, prefix=mass_queue.prefix)

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/ingestcraft"

    def register_endpoints(self):
        pass
