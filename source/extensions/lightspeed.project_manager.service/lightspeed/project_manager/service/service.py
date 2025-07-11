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

from lightspeed.layer_manager.core import LayerManagerCore
from lightspeed.layer_manager.core.data_models import LayerResponseModel, OpenProjectPathParamModel
from omni.flux.service.factory import ServiceBase


class ProjectManagerService(ServiceBase):
    def __init__(self, context_name: str = ""):
        """
        A service class that provides access to project management functionality in a RestAPI.

        Args:
            context_name: The USD context name
        """

        self.__layer_core = LayerManagerCore(context_name=context_name)

        super().__init__()

    @classmethod
    @property
    def prefix(cls) -> str:
        return "/project"

    def register_endpoints(self):
        @self.router.get(
            path="/",
            operation_id="get_loaded_project",
            description="Get the currently loaded project if one is loaded.",
            response_model=LayerResponseModel,
        )
        async def get_loaded_project() -> LayerResponseModel:
            try:
                return self.__layer_core.get_loaded_project_with_data_models()
            except ValueError as e:
                raise ServiceBase.raise_error(404, e)

        @self.router.put(path="/{layer_id:path}", operation_id="open_project", description="Open a project.")
        async def open_project(
            layer_id: str = ServiceBase.validate_path_param(  # noqa B008
                OpenProjectPathParamModel, description="Project identifier for the project to open as project"
            )
        ) -> str:
            return self.__layer_core.open_project_with_data_models(layer_id) or "OK"

        @self.router.delete(path="/", operation_id="close_project", description="Close the currently open project.")
        async def close_project() -> str:
            return self.__layer_core.close_project_with_data_models() or "OK"
