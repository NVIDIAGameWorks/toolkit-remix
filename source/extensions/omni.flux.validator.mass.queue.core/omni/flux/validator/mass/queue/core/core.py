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

from collections.abc import Callable

from omni.flux.utils.common import Event as _Event
from omni.flux.utils.common import EventSubscription as _EventSubscription
from omni.flux.validator.manager.core import ValidationSchema as _ValidationSchema  # FastAPI needs the full import
from omni.flux.validator.mass.queue.core.data_models import UpdateSchemaRequestModel as _UpdateSchemaRequestModel


class ValidatorMassQueueCore:
    def __init__(self):
        self.__on_update_item = _Event()

    def subscribe_on_update_item(self, function: Callable[[_ValidationSchema, str | None], None]):
        """
        Subscribe to the *on_update_item* event.

        Args:
            function: the callback to execute when the event is triggered

        Returns:
            An object that will automatically unsubscribe when destroyed.
        """
        return _EventSubscription(self.__on_update_item, function)

    def update_schema(self, data: _UpdateSchemaRequestModel):
        self.__on_update_item(data.validation_schema, queue_id=data.queue_id)
