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

import carb
import omni.ext

from .core import ValidatorMassQueueCore as _ValidatorMassQueueCore

_VALIDATOR_MASS_QUEUE_CORE_INSTANCE = None


def get_mass_validation_queue_instance() -> _ValidatorMassQueueCore | None:
    return _VALIDATOR_MASS_QUEUE_CORE_INSTANCE


class ValidatorMassQueueCoreExtension(omni.ext.IExt):
    """Standard extension support class, necessary for extension management"""

    def on_startup(self, _):
        global _VALIDATOR_MASS_QUEUE_CORE_INSTANCE
        carb.log_info("[omni.flux.validator.mass.queue.core] Startup")

        _VALIDATOR_MASS_QUEUE_CORE_INSTANCE = _ValidatorMassQueueCore()

    def on_shutdown(self):
        global _VALIDATOR_MASS_QUEUE_CORE_INSTANCE
        carb.log_info("[omni.flux.validator.mass.queue.core] Shutdown")

        _VALIDATOR_MASS_QUEUE_CORE_INSTANCE = None
