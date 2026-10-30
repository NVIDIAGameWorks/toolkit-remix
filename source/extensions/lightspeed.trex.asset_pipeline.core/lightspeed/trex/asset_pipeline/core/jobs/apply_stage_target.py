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

__all__ = ["ApplyStageTarget"]

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class ApplyStageTarget:
    """Identify the project and edit layer for one Apply operation, and validate them.

    A target extends this class with its own fields. Its `__post_init__()` calls `ApplyStageTarget.__post_init__(self)`
    because `super()` without arguments fails in a dataclass with slots.
    """

    context_name: str
    project_path: str
    edit_target_layer: str

    def __post_init__(self) -> None:
        """Validate the USD context, project, and edit layer."""
        if type(self.context_name) is not str:
            raise TypeError("context_name must be a str")
        for field_name in ("project_path", "edit_target_layer"):
            value = getattr(self, field_name)
            if type(value) is not str:
                raise TypeError(f"{field_name} must be a str")
            if not value.strip():
                raise ValueError(f"{field_name} must not be blank")
