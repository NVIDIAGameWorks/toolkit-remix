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

__all__ = ["get_test_workflow_pair"]

from copy import deepcopy

_API_WORKFLOW = {
    "10": {
        "inputs": {"strength": 0.5, "prompt": "restore material"},
        "class_type": "ExampleNode",
        "_meta": {
            "rtx-remix": {
                "inputs": {
                    "strength": {
                        "name": "Strength",
                        "type": "float",
                        "order": 1,
                        "additional_data": {"group": "Material", "tooltip": "Control processing strength"},
                    },
                    "prompt": {
                        "name": "Prompt",
                        "type": "str",
                        "order": 2,
                        "additional_data": {"group": "Material"},
                    },
                }
            }
        },
    },
    "177": {
        "inputs": {"image": "example.png"},
        "class_type": "LoadImage",
        "_meta": {
            "rtx-remix": {
                "inputs": {
                    "image": {
                        "name": "Texture",
                        "type": "str",
                        "remix_type": "texture_file_path",
                        "order": 0,
                        "additional_data": {"group": "Input", "tooltip": "Input texture file"},
                    }
                }
            }
        },
    },
    "181": {
        "inputs": {"texture_type": "albedo"},
        "class_type": "RTXRemixSaveTexture",
        "_meta": {
            "rtx-remix": {
                "output": {
                    "name": "albedo",
                    "type": "str",
                    "remix_type": "texture_file_path",
                    "order": 3,
                    "additional_data": {
                        "texture_type": "albedo",
                        "group": "",
                        "tooltip": "Upscaled albedo texture",
                    },
                }
            }
        },
    },
}

_FULL_WORKFLOW = {
    "extra": {
        "rtx-remix": {
            "presets": {
                "Strong": {
                    "description": "Increase processing strength",
                    "inputs": {"10.strength": {"value": 1.0}},
                },
                "Soft": {"inputs": {"10.strength": {"value": 0.25}}},
            },
            "groupOrder": ["Input", "Material"],
            "activePreset": "Strong",
        }
    }
}


def get_test_workflow_pair() -> tuple[dict, dict]:
    """Return fresh canonical API and full ComfyUI workflow fixtures.

    Returns:
        Independent API and full workflow dictionaries.
    """
    return deepcopy(_API_WORKFLOW), deepcopy(_FULL_WORKFLOW)
