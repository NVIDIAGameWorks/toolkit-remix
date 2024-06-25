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

from pxr import Usd

_DISABLE_SWITCHES = False


def should_disable_switch():
    return _DISABLE_SWITCHES


class ForceEditContext(Usd.EditContext):
    def __enter__(self):
        global _DISABLE_SWITCHES
        _DISABLE_SWITCHES = True
        return super().__enter__()

    def __exit__(self, *args, **kwargs):
        result = super().__exit__(*args, **kwargs)
        global _DISABLE_SWITCHES
        _DISABLE_SWITCHES = False
        return result


def monkey_patch():
    Usd.EditContext = ForceEditContext
