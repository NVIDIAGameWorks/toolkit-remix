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

from typing import Any

from pydantic import Extra, PrivateAttr, validator

from ..extension import get_instance as _get_factory_instance
from .interface_base import IBase as _IBase
from .interface_base import IBaseSchema as _IBaseSchema


class BaseSchema(_IBaseSchema):
    name: str
    enabled: bool = True
    data: _IBase.Data
    _instance: Any = PrivateAttr()  # instance before data because data need the instance

    def __init__(self, **data):
        if "name" not in data:
            raise KeyError(f"The key 'name' is missing from the plugin {type(self)}")
        plugin = _get_factory_instance().get_plugin_from_name(data["name"])
        if not plugin:
            raise ValueError(
                f"Plugin {data['name']} was not registered! Please enable the extension that has the plugin"
            )  # noqa
        self._instance = plugin()
        # transform the dict data into a model data
        try:
            data["data"] = self._instance.data_type(**data["data"])
        except KeyError:
            raise ValueError(f"'data' key is missing for the plugin {data['name']}")  # noqa
        BaseSchema.__check_data_flow(data)
        # check the data flow compatibility
        super().__init__(**data)
        self._instance.set_parent_schema(self)

    @property
    def instance(self):
        return self._instance

    @staticmethod
    def __check_data_flow(data):
        data_flow_compatible_names = data["data"].data_flow_compatible_name
        for data_flow in data["data"].data_flows or []:
            if data_flow.name not in data_flow_compatible_names:
                raise ValueError(
                    f"'{data_flow.name}' DataFlow is not compatible with the plugin {data['name']}. Compatible data "
                    f"flows are {data_flow_compatible_names}"
                )  # noqa

    @validator("name", allow_reuse=True)
    def is_registered(cls, v):  # noqa
        result = _get_factory_instance().is_plugin_registered(v)
        if not result:
            raise ValueError(f"Plugin {v} is not registered")
        return v

    def destroy(self):
        self._instance.destroy()
        self._instance = None

    class Config:
        extra = Extra.forbid
