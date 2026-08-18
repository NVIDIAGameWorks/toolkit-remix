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

__all__ = ["Preset"]

from dataclasses import dataclass, field
from typing import Any

import carb


@dataclass
class Preset:
    """A named set of workflow input overrides.

    Keys in ``inputs`` use the ``"node_id.port_name"`` format
    (e.g., ``"68.metallic_strength"``). Inputs not mentioned in the preset
    keep their workflow defaults.
    """

    name: str
    description: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "Preset | None":
        """Parse a preset from LiteGraph metadata.

        Args:
            name: The preset display name.
            data: A dict with ``"inputs"`` (mapping ``"node_id.port_name"`` to
                  override dicts) and optional ``"description"``.

        Returns:
            Parsed preset, or ``None`` when the metadata is malformed.
        """
        if not isinstance(name, str) or not name:
            carb.log_warn("Skipping malformed preset: name must be a non-empty string")
            return None
        if not isinstance(data, dict):
            carb.log_warn(f"Skipping malformed preset '{name}': expected dict")
            return None

        description = data.get("description", "")
        if not isinstance(description, str):
            carb.log_warn(f"Skipping malformed preset '{name}': description must be a string")
            return None
        if "inputs" not in data:
            carb.log_warn(f"Skipping malformed preset '{name}': inputs is required")
            return None
        raw_inputs = data["inputs"]
        if not isinstance(raw_inputs, dict):
            carb.log_warn(f"Skipping malformed preset '{name}': inputs must be a dict")
            return None
        inputs = {}
        for key, override in raw_inputs.items():
            if not isinstance(key, str) or not key:
                carb.log_warn(f"Skipping malformed input key in preset '{name}': expected non-empty string")
                continue
            node_id, separator, port_name = key.partition(".")
            if not separator or not node_id or not port_name:
                carb.log_warn(f"Skipping malformed input key '{key}' in preset '{name}': expected node.port")
                continue
            if not isinstance(override, dict) or "value" not in override:
                carb.log_warn(f"Skipping malformed input '{key}' in preset '{name}': value is required")
                continue
            inputs[key] = override["value"]
        return cls(name=name, description=description, inputs=inputs)
