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

__all__ = ("WORKFLOW_SOURCE_LABELS", "get_native_constant_label")

import pathlib

from lightspeed.trex.comfyui.core.enums import WorkflowSourceType

WORKFLOW_SOURCE_LABELS = {
    WorkflowSourceType.RTX_REMIX: "Built-in",
    WorkflowSourceType.USER: "User",
}

NATIVE_CONSTANT_LABELS = {
    bool: "Boolean Constant",
    int: "Integer Constant",
    float: "Number Constant",
    str: "Text Constant",
    pathlib.Path: "File Path Constant",
}


def get_native_constant_label(native_type: type) -> str:
    """Return a user-facing constant label for one native workflow type.

    Args:
        native_type: Native Python type declared by the workflow input.

    Returns:
        Exact known label, or a readable label derived from the type name.
    """
    label = NATIVE_CONSTANT_LABELS.get(native_type)
    if label is not None:
        return label
    type_name = native_type.__name__.replace("_", " ").strip().title()
    return f"{type_name} Constant" if type_name else "Constant"
