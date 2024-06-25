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

from pydantic import BaseModel, Extra


class BaseServiceModel(BaseModel):
    """
    Base Model used for all service models. It adds the ability for fields with the `hidden=True` attribute to be hidden
    from the OpenAPI documentation.

    Fields should be injected dynamically in the service using `ServiceBase.inject_hidden_field`.

    Notes:
        - Models requiring injected fields should use root_validators as the field will be added at the end of the
          fields list and will therefore not be accessible if using a regular field validator.
        - The first field of any PathParamModel will be used to validate the Path Parameter.
    """

    class Config:
        extra = Extra.allow

        @staticmethod
        def schema_extra(schema: dict, _):
            props = {}
            for k, v in schema.get("properties", {}).items():
                if not v.get("hidden", False):
                    props[k] = v
            schema["properties"] = props
