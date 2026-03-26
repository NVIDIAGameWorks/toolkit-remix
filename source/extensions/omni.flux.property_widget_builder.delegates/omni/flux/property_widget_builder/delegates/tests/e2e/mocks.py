"""
* SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
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

__all__ = ("MockItem", "MockValueModel")

import omni.ui as ui

from ..unit.mocks import MockValueModel


class MockItem(ui.AbstractItem):
    """Minimal item with a configurable number of value models."""

    def __init__(self, values: list[float | int] | None = None, read_only: bool = False):
        super().__init__()
        if values is None:
            values = [0.0]
        self.value_models = [MockValueModel(v, read_only=read_only) for v in values]

    @property
    def element_count(self) -> int:
        return len(self.value_models)
