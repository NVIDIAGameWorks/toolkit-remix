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

__all__ = ["SetComfyUIOutputFieldCommand"]

from typing import Literal

import omni.kit.commands

from .enums import OutputApplyBehavior
from .models import WorkflowOutput


class SetComfyUIOutputFieldCommand(omni.kit.commands.Command):
    """Change one workflow output setting with undo support."""

    def __init__(
        self,
        workflow_output: WorkflowOutput,
        field_name: Literal["apply_behavior", "texture_type"],
        value: OutputApplyBehavior | str | None,
    ):
        """Capture the output field value before the change."""
        self._workflow_output = workflow_output
        self._field_name = field_name
        self._value = value
        if field_name == "apply_behavior":
            self._previous_value = workflow_output.apply_behavior
        else:
            self._previous_value = workflow_output.texture_type

    def do(self) -> None:
        """Apply the selected output setting."""
        self._assign(self._value)

    def undo(self) -> None:
        """Restore the previous output setting."""
        self._assign(self._previous_value)

    def _assign(self, value: OutputApplyBehavior | str | None) -> None:
        """Write a value to the selected output field.

        Args:
            value: Value stored on the output field.
        """
        if self._field_name == "apply_behavior":
            self._workflow_output.apply_behavior = value
        else:
            self._workflow_output.texture_type = value
