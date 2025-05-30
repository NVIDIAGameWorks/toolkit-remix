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

from pydantic import BaseModel, ConfigDict


class BaseServiceModel(BaseModel):
    """
    Base Model used for all service models. It adds the ability for injected fields to be hidden from the OpenAPI
    documentation and serialization.

    Fields should be injected dynamically in the service using `ServiceBase.inject_hidden_field`.

    Notes:
        - Models requiring injected fields should use model_validator as the field will be added at the end of the
          fields list and will therefore not be accessible if using a regular field validator.
        - The first field of any PathParamModel will be used to validate the Path Parameter.
    """

    model_config = ConfigDict(extra="ignore")
