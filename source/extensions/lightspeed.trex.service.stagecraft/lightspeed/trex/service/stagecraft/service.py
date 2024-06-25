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

__all__ = ["StageCraftService"]

from omni.flux.service.factory import ServiceBase
from omni.flux.service.factory import get_instance as _get_service_factory_instance


class StageCraftService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that group up all the functionality exposed in StageCraft in a RestAPI.

        Args:
            context_name: The USD context name
        """
        super().__init__()

        # Get the desired services from the factory
        factory = _get_service_factory_instance()

        project_manager = factory.get_service_from_name("ProjectManagerService")(context_name=context_name)
        layer_manager = factory.get_service_from_name("LayerManagerService")(context_name=context_name)
        asset_replacement = factory.get_service_from_name("AssetReplacementsService")(context_name=context_name)
        texture_replacement = factory.get_service_from_name("TextureReplacementsService")(context_name=context_name)

        # Include the desired services in the app-level service
        self.router.include_router(project_manager.router, prefix=project_manager.prefix)
        self.router.include_router(layer_manager.router, prefix=layer_manager.prefix)
        self.router.include_router(asset_replacement.router, prefix=asset_replacement.prefix)
        self.router.include_router(texture_replacement.router, prefix=texture_replacement.prefix)

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/stagecraft"

    def register_endpoints(self):
        pass
