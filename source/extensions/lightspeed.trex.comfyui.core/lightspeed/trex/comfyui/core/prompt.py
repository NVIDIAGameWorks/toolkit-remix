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

__all__ = ["set_prompt_value"]

from typing import Any


def set_prompt_value(prompt: dict[str, Any], port_id: str, value: Any) -> None:
    """Set a resolved prompt value or fail when the workflow port is invalid.

    Args:
        prompt: Mutable API prompt containing the target node input.
        port_id: Dot-separated node, section, and port identifier to update.
        value: Resolved value to store in the prompt.

    Raises:
        ValueError: If the port identifier or referenced prompt field is invalid.
    """
    parts = port_id.split(".")
    if len(parts) < 3:
        raise ValueError(f"Invalid workflow input port '{port_id}'")

    node_id, section = parts[:2]
    port_name = ".".join(parts[2:])
    node = prompt.get(node_id)
    if not isinstance(node, dict):
        raise ValueError(f"Workflow input port '{port_id}' references a missing node")
    section_data = node.get(section)
    if not isinstance(section_data, dict) or port_name not in section_data:
        raise ValueError(f"Workflow input port '{port_id}' references a missing prompt field")
    section_data[port_name] = value
